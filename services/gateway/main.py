from fastapi import FastAPI
from pydantic import BaseModel
from common.kafka_client import get_producer
import json

app = FastAPI(title="Gateway Service")
producer = get_producer()

class TaskRequest(BaseModel):
    prompt: str
    task_type: str = "text"


@app.post("/tasks/create")
def create_task(req: TaskRequest):
    data = {
        "prompt": req.prompt,
        "task_type": req.task_type
    }
    producer.produce("tasks.incoming", json.dumps(data).encode())
    producer.flush()

    return {"status": "queued", "data": data}


@app.get("/")
def root():
    return {"status": "gateway-online"}

