#!/usr/bin/env python3
"""
AI Network — GPU Worker Node
Connects to scheduler, processes AI tasks, returns results
"""

import os
import sys
import time
import uuid
import argparse
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import text, image, audio

# ============================================================
# CONFIGURATION
# ============================================================

SCHEDULER_URL = os.getenv("SCHEDULER_URL", "http://localhost:8001")
WORKER_ID = os.getenv("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))

# ============================================================
# WORKER
# ============================================================

class Worker:
    def __init__(self, worker_id: str, capabilities: list):
        self.worker_id = worker_id
        self.capabilities = capabilities
        self.running = True
        self.tasks_completed = 0

    def register(self) -> bool:
        """Register with scheduler"""
        try:
            resp = requests.post(
                f"{SCHEDULER_URL}/workers/register",
                json={
                    "worker_id": self.worker_id,
                    "capabilities": self.capabilities,
                    "gpu_name": self.get_gpu_name(),
                },
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"[Worker] Registered as {self.worker_id}")
                print(f"[Worker] Capabilities: {self.capabilities}")
                return True
            else:
                print(f"[Worker] Registration failed: {resp.text}")
                return False
        except Exception as e:
            print(f"[Worker] Cannot connect to scheduler: {e}")
            return False

    def get_gpu_name(self) -> str:
        """Get GPU name if available"""
        try:
            import torch
            if torch.cuda.is_available():
                return torch.cuda.get_device_name(0)
        except:
            pass
        return "CPU"

    def heartbeat(self):
        """Send heartbeat to scheduler"""
        try:
            requests.post(
                f"{SCHEDULER_URL}/workers/{self.worker_id}/heartbeat",
                timeout=5,
            )
        except:
            pass

    def poll_task(self) -> dict:
        """Poll scheduler for a task"""
        try:
            resp = requests.get(
                f"{SCHEDULER_URL}/workers/{self.worker_id}/task",
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"[Worker] Poll error: {e}")
        return {"task_id": None}

    def submit_result(self, task_id: str, result: str, success: bool = True, error: str = None):
        """Submit task result to scheduler"""
        try:
            resp = requests.post(
                f"{SCHEDULER_URL}/workers/{self.worker_id}/result",
                json={
                    "task_id": task_id,
                    "worker_id": self.worker_id,
                    "result": result,
                    "success": success,
                    "error": error,
                },
                timeout=30,
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"[Worker] Submit error: {e}")
            return False

    def process_task(self, task: dict) -> tuple:
        """Process a task and return (result, success, error)"""
        task_type = task.get("type", "text")
        payload = task.get("payload", {})

        print(f"[Worker] Processing {task_type} task...")

        try:
            if task_type == "text":
                result = text.generate(
                    prompt=payload.get("prompt", ""),
                    max_tokens=payload.get("max_tokens", 256),
                    temperature=payload.get("temperature", 0.7),
                )
                return result, True, None

            elif task_type == "image":
                result = image.generate(
                    prompt=payload.get("prompt", ""),
                    width=payload.get("width", 512),
                    height=payload.get("height", 512),
                )
                return result, True, None

            elif task_type == "audio":
                result = audio.transcribe(
                    audio_base64=payload.get("audio_base64", ""),
                    language=payload.get("language", "en"),
                )
                return result, True, None

            else:
                return f"Unknown task type: {task_type}", False, "Unknown task type"

        except Exception as e:
            return None, False, str(e)

    def run(self):
        """Main worker loop"""
        print(f"\n{'='*50}")
        print(f"  AI Network Worker")
        print(f"  ID: {self.worker_id}")
        print(f"  Scheduler: {SCHEDULER_URL}")
        print(f"{'='*50}\n")

        # Load models
        print("[Worker] Loading models...")
        text.load_model()
        image.load_model()
        audio.load_model()
        print("[Worker] Models ready\n")

        # Register
        if not self.register():
            print("[Worker] Failed to register. Retrying in 5 seconds...")
            time.sleep(5)
            if not self.register():
                print("[Worker] Cannot register. Exiting.")
                return

        print("[Worker] Waiting for tasks...\n")

        last_heartbeat = 0

        while self.running:
            try:
                # Send heartbeat every 10 seconds
                if time.time() - last_heartbeat > 10:
                    self.heartbeat()
                    last_heartbeat = time.time()

                # Poll for task
                task_data = self.poll_task()

                if task_data.get("task_id"):
                    task_id = task_data["task_id"]
                    print(f"[Worker] Got task: {task_id[:8]}...")

                    # Process
                    start_time = time.time()
                    result, success, error = self.process_task(task_data)
                    duration = time.time() - start_time

                    # Submit result
                    self.submit_result(task_id, result, success, error)
                    self.tasks_completed += 1

                    status = "✓" if success else "✗"
                    print(f"[Worker] Task {task_id[:8]} {status} ({duration:.2f}s) | Total: {self.tasks_completed}")

                else:
                    # No task, wait
                    time.sleep(POLL_INTERVAL)

            except KeyboardInterrupt:
                print("\n[Worker] Shutting down...")
                self.running = False

            except Exception as e:
                print(f"[Worker] Error: {e}")
                time.sleep(5)

        print(f"[Worker] Completed {self.tasks_completed} tasks. Goodbye!")

# ============================================================
# MAIN
# ============================================================

def main():
    global SCHEDULER_URL

    parser = argparse.ArgumentParser(description="AI Network Worker")
    parser.add_argument("--id", default=WORKER_ID, help="Worker ID")
    parser.add_argument("--scheduler", default=SCHEDULER_URL, help="Scheduler URL")
    parser.add_argument("--capabilities", default="text,image,audio", help="Comma-separated capabilities")
    args = parser.parse_args()

    SCHEDULER_URL = args.scheduler

    capabilities = [c.strip() for c in args.capabilities.split(",")]

    worker = Worker(args.id, capabilities)
    worker.run()

if __name__ == "__main__":
    main()
