import json
import time
import os
from fastapi import FastAPI
from sqlmodel import Session
from common.kafka_client import get_consumer, get_producer
from common.redis_client import redis_publish
from .db import engine, init_db
from .models import Task, Worker, Transaction

KAFKA_TOPIC = "tasks.results"

app = FastAPI(title="Validator Service")

consumer = get_consumer("validator-service", [KAFKA_TOPIC])
producer = get_producer()


@app.on_event("startup")
def startup():
    init_db()
    import threading
    t = threading.Thread(target=loop, daemon=True)
    t.start()


@app.get("/")
def root():
    return {"status": "validator-online"}


def reward(worker: Worker, amount: float, description: str, session: Session):
    worker.balance += amount
    tx = Transaction(
        worker_id=worker.id,
        amount=amount,
        description=description,
        timestamp=str(time.time())
    )
    session.add(tx)


def loop():
    while True:
        msg = consumer.poll(1.0)
        if not msg:
            continue

        if msg.error():
            print("Validator Kafka error:", msg.error())
            continue

        data = json.loads(msg.value().decode())
        task_id = data["task_id"]
        result_A = data["result_A"]
        result_B = data["result_B"]

        print(f"[VALIDATOR] incoming results for task #{task_id}")

        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                print("[ERR] no such task")
                continue

            worker_A = session.get(Worker, task.worker_id)
            worker_B = session.get(Worker, task.validator_worker_id)

            # MATCH ----------------------------------------
            if result_A == result_B:
                task.status = "done"
                task.validator_result = result_B
                task.updated_at = time.time()

                worker_A.reputation += 0.01
                worker_B.reputation += 0.005

                reward(worker_A, 0.05, f"Reward Task {task_id} A (passed)", session)
                reward(worker_B, 0.02, f"Reward Task {task_id} B (validator)", session)

                print(f"[VALIDATOR] Task {task_id}: MATCH")
            else:
                # MISMATCH ----------------------------------
                task.status = "rejected"
                task.validator_result = result_B
                task.updated_at = time.time()

                worker_A.reputation -= 0.1
                worker_B.reputation += 0.01

                print(f"[VALIDATOR] Task {task_id}: MISMATCH")

            session.add(task)
            session.add(worker_A)
            session.add(worker_B)
            session.commit()

            # Push WS event
            redis_publish("task_updates", {
                "task_id": task_id,
                "status": task.status,
                "worker_A_rep": worker_A.reputation,
                "worker_B_rep": worker_B.reputation
            })

