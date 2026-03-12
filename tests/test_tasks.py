import os
import requests

SERVER = os.getenv("TEST_SERVER", "http://localhost:8020")



def test_full_pipeline():
    # 1. register two workers
    wid1 = requests.post(f"{SERVER}/workers/register",
                          json={"name": "A", "power": 5}).json()["worker_id"]

    wid2 = requests.post(f"{SERVER}/workers/register",
                          json={"name": "B", "power": 5}).json()["worker_id"]

    # 2. create task
    tid = requests.post(f"{SERVER}/tasks/create",
                        json={"prompt": "abc", "task_type": "text"}).json()["task_id"]

    # 3. worker A gets task
    t1 = requests.get(f"{SERVER}/tasks/next/{wid1}").json()
    assert t1["task_id"] == tid
    assert t1["mode"] == "work"

    # 4. A submits result
    r1 = requests.post(f"{SERVER}/tasks/submit",
                       json={"task_id": tid, "worker_id": wid1, "result": "cba"}).json()
    assert r1["status"] == "ok"

    # 5. worker B should now get validation task
    t2 = requests.get(f"{SERVER}/tasks/next/{wid2}").json()
    assert t2["task_id"] == tid
    assert t2["mode"] == "validate"

    # 6. B validates
    r2 = requests.post(f"{SERVER}/tasks/validate",
                       json={"task_id": tid, "worker_id": wid2, "result": "cba"}).json()
    assert r2["status"] == "ok"

    print("Pipeline OK")

