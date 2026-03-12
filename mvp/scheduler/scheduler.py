"""
AI Network — Task Scheduler
Distributes tasks to available workers
"""

import time
import uuid
from typing import Dict, Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from collections import deque
import threading

app = FastAPI(title="AI Network Scheduler", version="1.0.0")

# ============================================================
# IN-MEMORY STORAGE
# ============================================================

# Workers: {worker_id: {id, capabilities, last_seen, status}}
workers: Dict[str, dict] = {}

# Tasks: {task_id: {id, type, payload, status, result, worker_id, created_at}}
tasks: Dict[str, dict] = {}

# Task queue by type
task_queues: Dict[str, deque] = {
    "text": deque(),
    "image": deque(),
    "audio": deque(),
}

# Lock for thread safety
lock = threading.Lock()

# ============================================================
# SCHEMAS
# ============================================================

class WorkerRegistration(BaseModel):
    worker_id: str
    capabilities: List[str]  # ["text", "image", "audio"]
    gpu_name: Optional[str] = None

class TaskSubmission(BaseModel):
    id: str
    type: str  # "text", "image", "audio"
    payload: dict

class TaskResult(BaseModel):
    task_id: str
    worker_id: str
    result: str
    success: bool = True
    error: Optional[str] = None

# ============================================================
# WORKER ENDPOINTS
# ============================================================

@app.post("/workers/register")
def register_worker(reg: WorkerRegistration):
    """Worker registers with scheduler"""
    with lock:
        workers[reg.worker_id] = {
            "id": reg.worker_id,
            "capabilities": reg.capabilities,
            "gpu_name": reg.gpu_name,
            "last_seen": time.time(),
            "status": "idle",
            "tasks_completed": 0,
        }
    print(f"[Scheduler] Worker registered: {reg.worker_id} ({reg.capabilities})")
    return {"status": "registered", "worker_id": reg.worker_id}

@app.post("/workers/{worker_id}/heartbeat")
def worker_heartbeat(worker_id: str):
    """Worker sends heartbeat"""
    with lock:
        if worker_id in workers:
            workers[worker_id]["last_seen"] = time.time()
            return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Worker not found")

@app.get("/workers/{worker_id}/task")
def get_task_for_worker(worker_id: str):
    """Worker polls for a task"""
    with lock:
        if worker_id not in workers:
            raise HTTPException(status_code=404, detail="Worker not registered")

        worker = workers[worker_id]
        worker["last_seen"] = time.time()

        # Find a task matching worker capabilities
        for task_type in worker["capabilities"]:
            if task_type in task_queues and task_queues[task_type]:
                task_id = task_queues[task_type].popleft()
                if task_id in tasks:
                    task = tasks[task_id]
                    task["status"] = "processing"
                    task["worker_id"] = worker_id
                    task["started_at"] = time.time()
                    worker["status"] = "busy"

                    print(f"[Scheduler] Task {task_id[:8]} assigned to {worker_id}")

                    return {
                        "task_id": task["id"],
                        "type": task["type"],
                        "payload": task["payload"],
                    }

    # No task available
    return {"task_id": None}

@app.post("/workers/{worker_id}/result")
def submit_result(worker_id: str, result: TaskResult):
    """Worker submits task result"""
    with lock:
        if result.task_id not in tasks:
            raise HTTPException(status_code=404, detail="Task not found")

        task = tasks[result.task_id]

        if result.success:
            task["status"] = "completed"
            task["result"] = result.result
            task["completed_at"] = time.time()
        else:
            task["status"] = "failed"
            task["error"] = result.error

        # Update worker
        if worker_id in workers:
            workers[worker_id]["status"] = "idle"
            workers[worker_id]["tasks_completed"] += 1

        print(f"[Scheduler] Task {result.task_id[:8]} completed by {worker_id}")

    return {"status": "ok"}

# ============================================================
# API ENDPOINTS (for API Gateway)
# ============================================================

@app.post("/tasks/submit")
def submit_task(task: TaskSubmission):
    """API Gateway submits a task"""
    with lock:
        task_data = {
            "id": task.id,
            "type": task.type,
            "payload": task.payload,
            "status": "pending",
            "result": None,
            "error": None,
            "worker_id": None,
            "created_at": time.time(),
        }
        tasks[task.id] = task_data

        # Add to queue
        if task.type in task_queues:
            task_queues[task.type].append(task.id)
        else:
            task_queues["text"].append(task.id)  # default

    print(f"[Scheduler] Task {task.id[:8]} queued ({task.type})")
    return {"status": "queued", "task_id": task.id}

@app.get("/tasks/{task_id}/result")
def get_task_result(task_id: str):
    """API Gateway polls for task result"""
    with lock:
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="Task not found")

        task = tasks[task_id]
        return {
            "task_id": task_id,
            "status": task["status"],
            "result": task.get("result"),
            "error": task.get("error"),
        }

# ============================================================
# MONITORING
# ============================================================

@app.get("/")
def root():
    return {"status": "Scheduler running", "workers": len(workers), "tasks": len(tasks)}

@app.get("/stats")
def stats():
    with lock:
        active_workers = sum(1 for w in workers.values() if time.time() - w["last_seen"] < 30)
        pending = sum(1 for t in tasks.values() if t["status"] == "pending")
        processing = sum(1 for t in tasks.values() if t["status"] == "processing")
        completed = sum(1 for t in tasks.values() if t["status"] == "completed")

        return {
            "workers": {
                "total": len(workers),
                "active": active_workers,
            },
            "tasks": {
                "pending": pending,
                "processing": processing,
                "completed": completed,
                "total": len(tasks),
            },
            "queues": {k: len(v) for k, v in task_queues.items()},
        }

@app.get("/workers")
def list_workers():
    with lock:
        return {
            "workers": [
                {
                    "id": w["id"],
                    "capabilities": w["capabilities"],
                    "status": w["status"],
                    "tasks_completed": w["tasks_completed"],
                    "last_seen": int(time.time() - w["last_seen"]),
                }
                for w in workers.values()
            ]
        }

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    print("[Scheduler] Starting on port 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
