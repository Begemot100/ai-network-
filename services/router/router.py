from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable
import json
import os
import time

# =========================================================
# CONFIG
# =========================================================

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")

IN_TOPIC = "ai.tasks.v2"
CPU_TOPIC = "ai.tasks.cpu"
GPU_TOPIC = "ai.tasks.gpu"

GROUP_ID = "router-v1"

# =========================================================
# HELPERS
# =========================================================

def safe_json(m):
    try:
        return json.loads(m.decode("utf-8"))
    except Exception:
        return None

# =========================================================
# KAFKA INIT (RETRY LOOP — CRITICAL)
# =========================================================

print("[router] starting...", flush=True)

while True:
    try:
        consumer = KafkaConsumer(
            IN_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id=GROUP_ID,
            auto_offset_reset="latest",
            enable_auto_commit=False,
            value_deserializer=safe_json,
        )

        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        break

    except NoBrokersAvailable:
        print("[router] kafka not ready, retry 2s", flush=True)
        time.sleep(2)

print("[router] connected to Kafka", flush=True)
print("[router] listening", IN_TOPIC, flush=True)

# =========================================================
# MAIN LOOP
# =========================================================

for msg in consumer:
    task = msg.value

    if not task:
        consumer.commit()
        continue

    payload = task.get("payload", {})
    task_type = payload.get("type")

    # ----------------------------------
    # ROUTING LOGIC
    # ----------------------------------

    target_topic = CPU_TOPIC

    if task_type == "sentiment_analysis":
        texts = payload.get("texts", [])
        if len(texts) >= 20:
            target_topic = GPU_TOPIC

    producer.send(target_topic, task)
    producer.flush()

    print(
        f"[router] job={task['job_id']} "
        f"chunk={task['chunk_id']} → {target_topic}",
        flush=True,
    )

    consumer.commit()
