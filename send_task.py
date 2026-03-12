from kafka import KafkaProducer
import json

producer = KafkaProducer(
    bootstrap_servers="localhost:29092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

job_id = "11111111-1111-1111-1111-111111111111"
chunks = 50
step = 2_000_000

for i in range(chunks):
    producer.send(
        "ai.tasks.v2",
        {
            "job_id": job_id,
            "chunk_id": i,
            "payload": {
                "type": "prime_count",
                "start": i * step,
                "end": (i + 1) * step,
            },
        },
    )

producer.flush()
print("tasks sent")
