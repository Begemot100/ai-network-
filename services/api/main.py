from fastapi import (
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
)
from pydantic import BaseModel
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
import psycopg2
import csv
import json
import time
import uuid
import os
import asyncio
from typing import Optional
from collections import Counter
# =========================================================
# APP
# =========================================================

app = FastAPI()

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")

# =========================================================
# DB
# =========================================================

def get_conn():
    while True:
        try:
            conn = psycopg2.connect(
                dbname=os.getenv("POSTGRES_DB", "ainetwork"),
                user=os.getenv("POSTGRES_USER", "ai"),
                password=os.getenv("POSTGRES_PASSWORD", "ai_secure_password"),
                host=os.getenv("POSTGRES_HOST", "postgres"),
            )
            conn.autocommit = True
            return conn
        except psycopg2.OperationalError:
            time.sleep(1)

# =========================================================
# KAFKA (LAZY INIT)
# =========================================================

producer: Optional[KafkaProducer] = None

def get_producer() -> KafkaProducer:
    global producer

    if producer is not None:
        return producer

    for i in range(30):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                retries=5,
                retry_backoff_ms=2000,
            )
            print("[Kafka] producer ready")
            return producer
        except NoBrokersAvailable:
            print(f"[Kafka] not ready, retry {i + 1}/30")
            time.sleep(2)

    raise RuntimeError("Kafka is not available")

@app.on_event("startup")
def startup_event():
    try:
        get_producer()
    except Exception as e:
        print(f"[Startup] Kafka unavailable: {e}")

@app.on_event("shutdown")
def shutdown_event():
    global producer
    if producer:
        producer.flush()
        producer.close()
        producer = None

# =========================================================
# SCHEMA (универсальный)
# =========================================================

class JobRequest(BaseModel):
    task_type: str
    payload: dict
    chunk_size: int = 10

# =========================================================
# API
# =========================================================

@app.post("/jobs")
def create_job(req: JobRequest):
    """
    Универсальный endpoint (на будущее).
    Сейчас используется только для простых задач.
    """
    job_id = str(uuid.uuid4())

    items = req.payload.get("items")
    if not isinstance(items, list) or not items:
        raise HTTPException(400, "payload.items must be a non-empty list")

    chunks = [
        items[i:i + req.chunk_size]
        for i in range(0, len(items), req.chunk_size)
    ]

    total_chunks = len(chunks)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO ai_jobs (job_id, total_chunks, completed_chunks, status)
        VALUES (%s, %s, 0, 'running')
        """,
        (job_id, total_chunks),
    )

    cur.execute(
        """
        INSERT INTO ai_job_events (job_id, event_type)
        VALUES (%s, 'job_created')
        """,
        (job_id,),
    )

    conn.close()

    producer = get_producer()

    for cid, chunk in enumerate(chunks):
        producer.send(
            "ai.tasks.v2",
            {
                "job_id": job_id,
                "chunk_id": cid,
                "payload": {
                    "type": req.task_type,
                    "items": chunk,
                },
            },
        )

    producer.flush()

    return {
        "job_id": job_id,
        "total_chunks": total_chunks,
        "status": "running",
    }

# ---------------------------------------------------------
# CSV SENTIMENT JOB (БИЗНЕС)
# ---------------------------------------------------------

@app.post("/jobs/sentiment/csv")
def create_sentiment_job_csv(
    file: UploadFile = File(...),
    chunk_size: int = 5,
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "CSV required")

    content = file.file.read().decode("utf-8").splitlines()
    reader = csv.DictReader(content)

    texts = []
    for row in reader:
        if "text" not in row:
            raise HTTPException(
                400, "CSV must contain 'text' column"
            )
        texts.append(row["text"])

    if not texts:
        raise HTTPException(400, "empty CSV")

    chunks = [
        texts[i:i + chunk_size]
        for i in range(0, len(texts), chunk_size)
    ]

    job_id = str(uuid.uuid4())
    total_chunks = len(chunks)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO ai_jobs (job_id, total_chunks, completed_chunks, status)
        VALUES (%s, %s, 0, 'running')
        """,
        (job_id, total_chunks),
    )

    cur.execute(
        """
        INSERT INTO ai_job_events (job_id, event_type)
        VALUES (%s, 'job_created')
        """,
        (job_id,),
    )

    conn.close()

    producer = get_producer()

    for cid, texts_chunk in enumerate(chunks):
        producer.send(
            "ai.tasks.v2",
            {
                "job_id": job_id,
                "chunk_id": cid,
                "payload": {
                    "type": "sentiment_analysis",
                    "texts": texts_chunk,
                },
            },
        )

    producer.flush()

    return {
        "job_id": job_id,
        "total_chunks": total_chunks,
        "status": "running",
    }

# =========================================================
# STATUS / RESULTS
# =========================================================

@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT job_id, total_chunks, completed_chunks, status
        FROM ai_jobs
        WHERE job_id = %s
        """,
        (job_id,),
    )

    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "job not found")

    return {
        "job_id": row[0],
        "total_chunks": row[1],
        "completed_chunks": row[2],
        "status": row[3],
    }

@app.get("/jobs/{job_id}/results")
def job_results(job_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT chunk_id, result
        FROM ai_results
        WHERE job_id = %s
        ORDER BY chunk_id
        """,
        (job_id,),
    )

    rows = cur.fetchall()
    conn.close()

    return {
        "job_id": job_id,
        "results": [
            {"chunk_id": r[0], "result": r[1]}
            for r in rows
        ],
    }

# =========================================================
# WEBSOCKET
# =========================================================

@app.websocket("/ws/jobs/{job_id}")
async def job_progress_ws(websocket: WebSocket, job_id: str):
    await websocket.accept()
    last_event_id = 0

    try:
        while True:
            conn = get_conn()
            cur = conn.cursor()

            cur.execute(
                """
                SELECT id, event_type, chunk_id, created_at
                FROM ai_job_events
                WHERE job_id = %s AND id > %s
                ORDER BY id
                """,
                (job_id, last_event_id),
            )

            rows = cur.fetchall()
            conn.close()

            for r in rows:
                last_event_id = r[0]

                await websocket.send_json({
                    "event": r[1],
                    "chunk_id": r[2],
                    "time": r[3].isoformat(),
                })

                if r[1] == "job_done":
                    await websocket.close()
                    return

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        return

# =========================================================
# CANCEL
# =========================================================

@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE ai_jobs
        SET status = 'cancelled'
        WHERE job_id = %s
          AND status NOT IN ('done', 'cancelled')
        """,
        (job_id,),
    )

    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(400, "job already finished or cancelled")

    cur.execute(
        """
        INSERT INTO ai_job_events (job_id, event_type)
        VALUES (%s, 'job_cancelled')
        """,
        (job_id,),
    )

    conn.close()

    return {"job_id": job_id, "status": "cancelled"}

@app.get("/jobs/{job_id}/results")
def get_job_results(job_id: str):
    conn = get_conn()
    cur = conn.cursor()

    # Проверка job
    cur.execute(
        "SELECT status FROM ai_jobs WHERE job_id = %s",
        (job_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "job not found")

    status = row[0]
    if status != "done":
        return {
            "job_id": job_id,
            "status": status,
            "results": None,
        }

    # Забираем все чанки
    cur.execute(
        """
        SELECT chunk_id, result
        FROM ai_results
        WHERE job_id = %s
        ORDER BY chunk_id
        """,
        (job_id,),
    )

    rows = cur.fetchall()
    conn.close()

    return {
        "job_id": job_id,
        "status": "done",
        "chunks": [
            {
                "chunk_id": cid,
                "result": res,
            }
            for cid, res in rows
        ],
    }




@app.get("/jobs/{job_id}/summary")
def get_job_summary(job_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT result FROM ai_results WHERE job_id = %s",
        (job_id,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        raise HTTPException(404, "no results")

    total_pos = total_neg = total_neu = 0
    scores = []
    neg_texts = []
    pos_texts = []
    all_texts = []

    for (res,) in rows:
        total_pos += res["positive"]
        total_neg += res["negative"]
        total_neu += res["neutral"]
        scores.append(res["avg_score"])

        for item in res["items"]:
            all_texts.append(item["text"])
            if item["label"] == "negative":
                neg_texts.append(item["text"])
            elif item["label"] == "positive":
                pos_texts.append(item["text"])

    return {
        "job_id": job_id,
        "totals": {
            "positive": total_pos,
            "negative": total_neg,
            "neutral": total_neu,
        },
        "avg_score": round(sum(scores) / len(scores), 3),
        "top_negative_phrases": Counter(neg_texts).most_common(5),
        "top_positive_phrases": Counter(pos_texts).most_common(5),
    }
