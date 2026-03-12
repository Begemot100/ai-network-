import os
from confluent_kafka import Producer, Consumer

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")


def get_producer():
    return Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP
    })


def get_consumer(group_id: str, topics: list[str]):
    c = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": group_id,
        "auto.offset.reset": "earliest"
    })
    c.subscribe(topics)
    return c
