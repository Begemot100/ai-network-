import time
import requests
import json

SERVER = "http://localhost:8020"
WORKER_NAME = "worker-auto"
POWER = 10


# --------------------------
# SAFE PARSER
# --------------------------
def safe_json(response):
    try:
        return response.json()
    except:
        print("[WARN] Non-JSON response:")
        print(response.text[:200])
        return None


# --------------------------
# REGISTER WORKER
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
            print("[OK] Worker registered with ID:", wid)
            return wid

        except Exception as e:
            print("[ERR] register:", e)
            time.sleep(2)


# --------------------------
# HEARTBEAT
# --------------------------
def heartbeat(worker_id):
    try:
        requests.post(f"{SERVER}/workers/heartbeat",
                      params={"worker_id": worker_id},
                      timeout=3)
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
# SUBMIT (Worker A)
# --------------------------
def submit(worker_id, task_id, result):
    payload = {
        "task_id": task_id,
        "worker_id": worker_id,
        "result": result
    }

    try:
        r = requests.post(f"{SERVER}/tasks/submit", json=payload, timeout=5)
        print("[A → SERVER] submit:", safe_json(r))
    except Exception as e:
        print("[ERR] submit:", e)


# --------------------------
# VALIDATE (Worker B)
# --------------------------
def validate(worker_id, task_id, result):
    payload = {
        "task_id": task_id,
        "worker_id": worker_id,
        "result": result
    }

    try:
        r = requests.post(f"{SERVER}/tasks/validate", json=payload, timeout=5)
        print("[B → SERVER] validate:", safe_json(r))
    except Exception as e:
        print("[ERR] validate:", e)


# --------------------------
# LOCAL EXECUTOR
# --------------------------
def execute(prompt, mode):
    """
    mode='work'     → Worker A task
    mode='validate' → Worker B validates worker A's answer
    """

    # simple logic for now
    if prompt.startswith("reverse:"):
        return prompt.replace("reverse:", "")[::-1]

    if mode == "validate":
        # naive validator: return uppercase (same logic as worker A)
        return prompt.upper()

    return prompt.upper()


# --------------------------
# MAIN LOOP
# --------------------------
def main():
    wid = register()

    while True:
        heartbeat(wid)

        task = get_task(wid)
        if not task:
            print("[*] no tasks, sleeping...")
            time.sleep(2)
            continue

        tid = task["task_id"]
        prompt = task["prompt"]
        mode = task["mode"]

        print(f"\n=== GOT TASK #{tid} mode={mode} prompt='{prompt}' ===")

        # emulate computation
        result = execute(prompt, mode)
        time.sleep(1)

        if mode == "work":
            submit(wid, tid, result)

        elif mode == "validate":
            validate(wid, tid, result)

        else:
            print("[ERR] unknown mode:", mode)

        time.sleep(0.5)


if __name__ == "__main__":
    main()
