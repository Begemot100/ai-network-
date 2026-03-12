import json
import redis
import os

REDIS_HOST = os.getenv("REDIS_HOST", "ai_redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def redis_publish(channel: str, message: dict):
    r.publish(channel, json.dumps(message))

