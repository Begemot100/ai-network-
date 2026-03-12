import json
import threading
from fastapi import FastAPI
from sqlmodel import Session
from common.kafka_client import get_consumer, get_producer
from .db import init_db, engine
from .models import Task
import os

print("=== ENV:KAFKA_BOOTSTRAP =", os.getenv("KAFKA_BOOTSTRAP"))

app = FastAPI(title="Task Service")

producer = get_producer()
consumer = get_consumer("task-service", ["tasks.incoming"])


@app.on_event("startup")
def startup():
    print("[*] Task service starting...")
    init_db()
    print("[*] DB initialized")

    # Kafka consumer запускаем в отдельном потоке
    thread = threading.Thread(target=consume_loop, daemon=True)
    thread.start()
    print("[*] Consumer thread started")


@app.get("/")
def root():
    return {"status": "task-service-online"}


def consume_loop():
    print("[*] Enter consumer loop...")
    while True:
        msg = consumer.poll(1.0)
        if msg is None:
            continue

        if msg.error():
            print("Kafka error:", msg.error())
            continue

        data = json.loads(msg.value().decode())
        prompt = data["prompt"]
        task_type = data["task_type"]

        with Session(engine) as session:
            task = Task(prompt=prompt, task_type=task_type)
            session.add(task)
            session.commit()
            session.refresh(task)

        producer.produce(
            "tasks.to_workers",
            json.dumps({"task_id": task.id, "prompt": prompt}).encode()
        )
        producer.flush()

        print("Queued task:", task.id)
