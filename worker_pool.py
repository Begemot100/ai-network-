import time
import requests
import json
import threading

SERVER = "http://localhost:8020"
WORKER_NAME = "worker-pool"
POWER = 50

WORKER_THREADS = 4       # ← число параллельных потоков


# --------------------------
# SAFE JSON
# --------------------------
def safe_json(response):
    try:
        return response.json()
    except:
        print("[WARN] Non-JSON:", response.text[:200])
        return None


# --------------------------
# REGISTER ONE WORKER
# --------------------------
def register():
    while True:
        try:
            print("[*] Registering worker...")
            r = requests.post(
                f"{SERVER}/workers/register",
                json={"name": WORKER_NAME, "power": POWER},
                timeout=5
            )
            data = safe_json(r)
            if not data:
                time.sleep(2)
                continue

            wid = data["worker_id"]
            print(f"[OK] Worker registered with ID: {wid}")
            return wid

        except Exception as e:
            print("[ERR] register:", e)
            time.sleep(2)


# --------------------------
# HEARTBEAT
# --------------------------
def heartbeat(worker_id):
    try:
        requests.post(
            f"{SERVER}/workers/heartbeat",
            params={"worker_id": worker_id},
            timeout=3
        )
    except:
        pass


# --------------------------
# GET TASK
# --------------------------
def get_task(worker_id):
    try:
        r = requests.get(f"{SERVER}/tasks/next/{worker_id}", timeout=5)
    except Exception as e:
        print("[ERR] get_task:", e)
        return None

    data = safe_json(r)
    if not data:
        return None

    if "task" in data and data["task"] is None:
        return None

    if "task_id" not in data:
        return None

    return {
        "task_id": data["task_id"],
        "prompt": data["prompt"],
        "task_type": data.get("task_type", "text"),
        "mode": data.get("mode", "work")
    }


# --------------------------
# SUBMIT RESULT (A)
# --------------------------
def submit(worker_id, task_id, result):
    payload = {
        "task_id": task_id,
        "worker_id": worker_id,
        "result": result
    }

    try:
        r = requests.post(f"{SERVER}/tasks/submit", json=payload, timeout=5)
        print("[A] submit:", safe_json(r))
    except Exception as e:
        print("[ERR submit]:", e)


# --------------------------
# VALIDATE RESULT (B)
# --------------------------
def validate(worker_id, task_id, result):
    payload = {
        "task_id": task_id,
        "worker_id": worker_id,
        "result": result
    }

    try:
        r = requests.post(f"{SERVER}/tasks/validate", json=payload, timeout=5)
        print("[B] validate:", safe_json(r))
    except Exception as e:
        print("[ERR validate]:", e)


# --------------------------
# EXECUTE
# --------------------------
def execute(prompt, mode):
    if prompt.startswith("reverse:"):
        return prompt.replace("reverse:", "")[::-1]

    return prompt.upper()


# --------------------------
# WORKER THREAD LOOP
# --------------------------
def worker_thread_loop(worker_id, thread_id):
    print(f"[THREAD {thread_id}] started")

    while True:
        heartbeat(worker_id)

        task = get_task(worker_id)
        if not task:
            time.sleep(1)
            continue

        tid = task["task_id"]
        mode = task["mode"]
        prompt = task["prompt"]

        print(f"[THREAD {thread_id}] GOT TASK #{tid} mode={mode} prompt={prompt}")

        result = execute(prompt, mode)
        time.sleep(0.5)

        if mode == "work":
            submit(worker_id, tid, result)
        elif mode == "validate":
            validate(worker_id, tid, result)
        else:
            print(f"[THREAD {thread_id}] ERR unknown mode:", mode)

        time.sleep(0.5)


# --------------------------
# MAIN: CREATE WORKER + THREAD POOL
# --------------------------
def main():
    worker_id = register()

    threads = []
    for i in range(WORKER_THREADS):
        t = threading.Thread(target=worker_thread_loop, args=(worker_id, i))
        t.daemon = True
        t.start()
        threads.append(t)

    print(f"[OK] Worker pool started with {WORKER_THREADS} threads")

    # Keep alive
    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()

