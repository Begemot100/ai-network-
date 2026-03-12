from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
import psycopg2
import json
import os
import time
from collections import Counter

# =========================================================
# CONFIG
# =========================================================

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
RESULT_TOPIC = "ai.results"
GROUP_ID = "ai-reducer-dev-1"


print("[reducer] starting...", flush=True)

# =========================================================
# DB CONNECTION
# =========================================================

def get_conn():
    while True:
        try:
            conn = psycopg2.connect(
                dbname="ainetwork",
                user="ai",
                password="ai",
                host="ai_postgres",
            )
            conn.autocommit = True
            return conn
        except psycopg2.OperationalError:
            print("[reducer] postgres not ready, retry 2s", flush=True)
            time.sleep(2)

conn = get_conn()
cur = conn.cursor()
print("[reducer] connected to Postgres", flush=True)

# =========================================================
# SUMMARY BUILDER
# =========================================================

def build_summary(cur, job_id: str):
    cur.execute(
        "SELECT result FROM ai_results WHERE job_id = %s",
        (job_id,),
    )
    rows = cur.fetchall()

    if not rows:
        return None

    total_pos = total_neg = total_neu = 0
    scores = []
    neg_texts = []
    pos_texts = []

    for (res,) in rows:
        total_pos += res["positive"]
        total_neg += res["negative"]
        total_neu += res["neutral"]
        scores.append(res["avg_score"])

        for item in res["items"]:
            if item["label"] == "negative":
                neg_texts.append(item["text"])
            elif item["label"] == "positive":
                pos_texts.append(item["text"])

    return {
        "totals": {
            "positive": total_pos,
            "negative": total_neg,
            "neutral": total_neu,
        },
        "avg_score": round(sum(scores) / len(scores), 3),
        "top_negative": Counter(neg_texts).most_common(5),
        "top_positive": Counter(pos_texts).most_common(5),
    }

# =========================================================
# KAFKA CONSUMER INIT
# =========================================================

while True:
    try:
        consumer = KafkaConsumer(
            RESULT_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id=GROUP_ID,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        break
    except NoBrokersAvailable:
        print("[reducer] kafka not ready, retry 2s", flush=True)
        time.sleep(2)

print("[reducer] listening ai.results", flush=True)

# =========================================================
# MAIN LOOP
# =========================================================

for msg in consumer:
    try:
        data = msg.value

        job_id = data["job_id"]
        chunk_id = data["chunk_id"]
        result = data["result"]

        # 1. STORE CHUNK RESULT (IDEMPOTENT)
        cur.execute(
            """
            INSERT INTO ai_results (job_id, chunk_id, result)
            VALUES (%s, %s, %s)
            ON CONFLICT (job_id, chunk_id) DO NOTHING
            """,
            (job_id, chunk_id, json.dumps(result)),
        )

        inserted = cur.rowcount == 1

        # 2. INCREMENT completed_chunks ONLY IF INSERTED
        if inserted:
            cur.execute(
                """
                UPDATE ai_jobs
                SET completed_chunks = completed_chunks + 1
                WHERE job_id = %s
                  AND status = 'running'
                """,
                (job_id,),
            )

        # 3. LOAD JOB STATE
        cur.execute(
            """
            SELECT total_chunks, completed_chunks, status
            FROM ai_jobs
            WHERE job_id = %s
            """,
            (job_id,),
        )

        row = cur.fetchone()
        if not row:
            consumer.commit()
            continue

        total, done, status = row

        # -------------------------------------------------
        # 4. FINALIZE JOB + BUILD SUMMARY (IDEMPOTENT)
        # -------------------------------------------------
        if total == done:
            # 1. Гарантируем статус done
            cur.execute(
                """
                UPDATE ai_jobs
                SET status = 'done'
                WHERE job_id = %s
                """,
                (job_id,),
            )

            # 2. Проверяем, есть ли summary
            cur.execute(
                """
                SELECT 1 FROM ai_job_summary WHERE job_id = %s
                """,
                (job_id,),
            )

            if cur.fetchone() is None:
                summary = build_summary(cur, job_id)

                if summary:
                    cur.execute(
                        """
                        INSERT INTO ai_job_summary
                            (job_id, totals, avg_score, top_negative, top_positive)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            job_id,
                            json.dumps(summary["totals"]),
                            summary["avg_score"],
                            json.dumps(summary["top_negative"]),
                            json.dumps(summary["top_positive"]),
                        ),
                    )

                    cur.execute(
                        """
                        INSERT INTO ai_job_events (job_id, event_type)
                        VALUES (%s, 'job_done')
                        """,
                        (job_id,),
                    )

                    print(f"[reducer] job {job_id} DONE + SUMMARY", flush=True)

        consumer.commit()

    except Exception as e:
        print("[reducer] error:", e, flush=True)
        consumer.commit()
