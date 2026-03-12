"""
Dead Letter Queue (DLQ) Monitor for Distributed AI Network.

Monitors failed messages in DLQ topics and provides:
- Error categorization and analysis
- Retry logic with exponential backoff
- Alerting (webhook, logging)
- Metrics and reporting
"""

import json
import os
import time
import uuid
import logging
import threading
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable
import requests

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

# =============================================================================
# CONFIGURATION
# =============================================================================

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")

# DLQ topics to monitor
DLQ_TOPICS = [
    "ai.dlq",
    "ai.dlq.gpu",
    "ai.dlq.cpu",
]

# Retry configuration
MAX_RETRIES = int(os.getenv("DLQ_MAX_RETRIES", "3"))
RETRY_DELAY_BASE = int(os.getenv("DLQ_RETRY_DELAY_BASE", "60"))  # seconds
RETRY_DELAY_MAX = int(os.getenv("DLQ_RETRY_DELAY_MAX", "3600"))  # 1 hour max

# Alerting
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
ALERT_THRESHOLD = int(os.getenv("DLQ_ALERT_THRESHOLD", "10"))  # Alert after X errors
ALERT_WINDOW_MINUTES = int(os.getenv("DLQ_ALERT_WINDOW", "5"))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("dlq-monitor")


# =============================================================================
# ERROR CATEGORIES
# =============================================================================

class ErrorCategory(str, Enum):
    """Categories of DLQ errors."""
    TRANSIENT = "transient"          # Temporary failures, can retry
    PERMANENT = "permanent"          # Permanent failures, don't retry
    VALIDATION = "validation"        # Data validation errors
    TIMEOUT = "timeout"              # Timeout errors
    RESOURCE = "resource"            # Resource exhaustion (memory, etc.)
    UNKNOWN = "unknown"              # Unknown errors


ERROR_PATTERNS = {
    # Transient errors (can retry)
    ErrorCategory.TRANSIENT: [
        "connection refused",
        "timeout",
        "service unavailable",
        "too many requests",
        "rate limit",
        "temporary failure",
        "retry later",
        "connection reset",
        "broken pipe",
    ],
    # Permanent errors (don't retry)
    ErrorCategory.PERMANENT: [
        "invalid task type",
        "unsupported",
        "not found",
        "authentication failed",
        "forbidden",
        "invalid api key",
    ],
    # Validation errors
    ErrorCategory.VALIDATION: [
        "validation error",
        "invalid input",
        "missing required",
        "malformed",
        "parse error",
        "json decode",
    ],
    # Timeout errors
    ErrorCategory.TIMEOUT: [
        "timeout",
        "timed out",
        "deadline exceeded",
    ],
    # Resource errors
    ErrorCategory.RESOURCE: [
        "out of memory",
        "oom",
        "resource exhausted",
        "disk full",
        "no space left",
        "cuda out of memory",
    ],
}


def categorize_error(error_message: str) -> ErrorCategory:
    """Categorize an error based on the message."""
    error_lower = error_message.lower()

    for category, patterns in ERROR_PATTERNS.items():
        for pattern in patterns:
            if pattern in error_lower:
                return category

    return ErrorCategory.UNKNOWN


def should_retry(category: ErrorCategory, retry_count: int) -> bool:
    """Determine if an error should be retried."""
    if retry_count >= MAX_RETRIES:
        return False

    # Only retry transient, timeout, and resource errors
    return category in [
        ErrorCategory.TRANSIENT,
        ErrorCategory.TIMEOUT,
        ErrorCategory.RESOURCE,
    ]


def calculate_retry_delay(retry_count: int) -> int:
    """Calculate delay before next retry (exponential backoff)."""
    delay = RETRY_DELAY_BASE * (2 ** retry_count)
    return min(delay, RETRY_DELAY_MAX)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class DLQMessage:
    """Represents a message from the DLQ."""
    message_id: str
    topic: str
    error: str
    error_category: ErrorCategory
    raw_task: Optional[dict]
    worker_id: Optional[str]
    worker_type: Optional[str]
    timestamp: datetime
    retry_count: int = 0
    retry_after: Optional[datetime] = None

    @classmethod
    def from_kafka_message(cls, topic: str, value: dict) -> "DLQMessage":
        """Create from Kafka message value."""
        error = value.get("error", "Unknown error")

        return cls(
            message_id=str(uuid.uuid4()),
            topic=topic,
            error=error,
            error_category=categorize_error(error),
            raw_task=value.get("raw_task") or value.get("raw"),
            worker_id=value.get("worker_id"),
            worker_type=value.get("worker_type"),
            timestamp=datetime.utcnow(),
            retry_count=value.get("retry_count", 0),
        )


@dataclass
class ErrorStats:
    """Statistics about errors in a time window."""
    total_errors: int = 0
    by_category: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_topic: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_worker: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    recent_errors: List[DLQMessage] = field(default_factory=list)


# =============================================================================
# ALERTING
# =============================================================================

class AlertManager:
    """Manages alerting for DLQ errors."""

    def __init__(self):
        self.error_window: List[DLQMessage] = []
        self.last_alert_time: Optional[datetime] = None
        self.alert_cooldown = timedelta(minutes=15)

    def add_error(self, message: DLQMessage) -> None:
        """Add an error to the tracking window."""
        self.error_window.append(message)

        # Clean old errors
        cutoff = datetime.utcnow() - timedelta(minutes=ALERT_WINDOW_MINUTES)
        self.error_window = [m for m in self.error_window if m.timestamp > cutoff]

    def should_alert(self) -> bool:
        """Check if we should send an alert."""
        if len(self.error_window) < ALERT_THRESHOLD:
            return False

        if self.last_alert_time:
            if datetime.utcnow() - self.last_alert_time < self.alert_cooldown:
                return False

        return True

    def send_alert(self, stats: ErrorStats) -> None:
        """Send alert via configured channels."""
        self.last_alert_time = datetime.utcnow()

        message = self._format_alert(stats)

        # Log alert
        logger.warning(f"DLQ ALERT: {message}")

        # Send to webhook if configured
        if ALERT_WEBHOOK_URL:
            try:
                self._send_webhook(stats)
            except Exception as e:
                logger.error(f"Failed to send webhook alert: {e}")

    def _format_alert(self, stats: ErrorStats) -> str:
        """Format alert message."""
        return (
            f"DLQ Alert: {stats.total_errors} errors in last {ALERT_WINDOW_MINUTES} minutes. "
            f"Categories: {dict(stats.by_category)}. "
            f"Topics: {dict(stats.by_topic)}."
        )

    def _send_webhook(self, stats: ErrorStats) -> None:
        """Send alert to webhook."""
        payload = {
            "text": f":warning: DLQ Alert: {stats.total_errors} errors detected",
            "attachments": [
                {
                    "color": "danger",
                    "fields": [
                        {
                            "title": "Total Errors",
                            "value": str(stats.total_errors),
                            "short": True,
                        },
                        {
                            "title": "Time Window",
                            "value": f"{ALERT_WINDOW_MINUTES} minutes",
                            "short": True,
                        },
                        {
                            "title": "By Category",
                            "value": json.dumps(dict(stats.by_category), indent=2),
                            "short": False,
                        },
                        {
                            "title": "By Topic",
                            "value": json.dumps(dict(stats.by_topic), indent=2),
                            "short": False,
                        },
                    ],
                }
            ],
        }

        requests.post(
            ALERT_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )


# =============================================================================
# RETRY MANAGER
# =============================================================================

class RetryManager:
    """Manages retry logic for DLQ messages."""

    def __init__(self, producer: KafkaProducer):
        self.producer = producer
        self.retry_queue: List[DLQMessage] = []
        self._lock = threading.Lock()

    def schedule_retry(self, message: DLQMessage) -> bool:
        """Schedule a message for retry."""
        if not should_retry(message.error_category, message.retry_count):
            logger.info(
                f"Message {message.message_id} not eligible for retry "
                f"(category={message.error_category}, retries={message.retry_count})"
            )
            return False

        delay = calculate_retry_delay(message.retry_count)
        message.retry_after = datetime.utcnow() + timedelta(seconds=delay)
        message.retry_count += 1

        with self._lock:
            self.retry_queue.append(message)

        logger.info(
            f"Scheduled retry for {message.message_id} "
            f"(attempt {message.retry_count}, delay {delay}s)"
        )
        return True

    def process_retries(self) -> int:
        """Process messages ready for retry."""
        now = datetime.utcnow()
        retried = 0

        with self._lock:
            ready = [m for m in self.retry_queue if m.retry_after and m.retry_after <= now]
            self.retry_queue = [m for m in self.retry_queue if m not in ready]

        for message in ready:
            if self._retry_message(message):
                retried += 1

        return retried

    def _retry_message(self, message: DLQMessage) -> bool:
        """Retry a single message."""
        if not message.raw_task:
            logger.warning(f"Cannot retry {message.message_id}: no raw task data")
            return False

        # Determine target topic
        target_topic = self._get_retry_topic(message)
        if not target_topic:
            logger.warning(f"Cannot retry {message.message_id}: unknown target topic")
            return False

        # Add retry metadata
        task = message.raw_task.copy()
        task["_retry_count"] = message.retry_count
        task["_original_error"] = message.error

        try:
            self.producer.send(target_topic, task)
            self.producer.flush()
            logger.info(f"Retried message {message.message_id} to {target_topic}")
            return True
        except KafkaError as e:
            logger.error(f"Failed to retry {message.message_id}: {e}")
            return False

    def _get_retry_topic(self, message: DLQMessage) -> Optional[str]:
        """Determine which topic to retry to."""
        # Map DLQ topics to original topics
        topic_map = {
            "ai.dlq.gpu": "ai.tasks.gpu",
            "ai.dlq.cpu": "ai.tasks.cpu",
            "ai.dlq": "ai.tasks.v2",
        }
        return topic_map.get(message.topic)


# =============================================================================
# MAIN MONITOR
# =============================================================================

class DLQMonitor:
    """Main DLQ monitoring service."""

    def __init__(self):
        self.consumer = None
        self.producer = None
        self.alert_manager = AlertManager()
        self.retry_manager = None
        self.stats = ErrorStats()
        self.running = False

    def connect(self) -> None:
        """Connect to Kafka."""
        while True:
            try:
                self.consumer = KafkaConsumer(
                    *DLQ_TOPICS,
                    bootstrap_servers=KAFKA_BOOTSTRAP,
                    group_id="dlq-monitor",
                    auto_offset_reset="latest",
                    enable_auto_commit=False,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                )

                self.producer = KafkaProducer(
                    bootstrap_servers=KAFKA_BOOTSTRAP,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                )

                self.retry_manager = RetryManager(self.producer)

                logger.info("Connected to Kafka")
                break
            except Exception as e:
                logger.warning(f"Kafka not ready: {e}, retrying in 5s...")
                time.sleep(5)

    def process_message(self, topic: str, value: dict) -> None:
        """Process a DLQ message."""
        message = DLQMessage.from_kafka_message(topic, value)

        # Update stats
        self.stats.total_errors += 1
        self.stats.by_category[message.error_category.value] += 1
        self.stats.by_topic[topic] += 1
        if message.worker_id:
            self.stats.by_worker[message.worker_id] += 1
        self.stats.recent_errors.append(message)

        # Keep only recent errors
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self.stats.recent_errors = [
            m for m in self.stats.recent_errors if m.timestamp > cutoff
        ]

        # Log the error
        logger.warning(
            f"DLQ message: topic={topic} "
            f"category={message.error_category.value} "
            f"worker={message.worker_id} "
            f"error={message.error[:100]}"
        )

        # Add to alert tracking
        self.alert_manager.add_error(message)

        # Check if we should alert
        if self.alert_manager.should_alert():
            self.alert_manager.send_alert(self.stats)

        # Schedule retry if applicable
        self.retry_manager.schedule_retry(message)

    def retry_loop(self) -> None:
        """Background thread for processing retries."""
        while self.running:
            try:
                retried = self.retry_manager.process_retries()
                if retried > 0:
                    logger.info(f"Processed {retried} retries")
            except Exception as e:
                logger.error(f"Retry loop error: {e}")

            time.sleep(10)  # Check every 10 seconds

    def run(self) -> None:
        """Main run loop."""
        self.connect()
        self.running = True

        # Start retry thread
        retry_thread = threading.Thread(target=self.retry_loop, daemon=True)
        retry_thread.start()

        logger.info(f"DLQ Monitor started, watching topics: {DLQ_TOPICS}")

        try:
            for msg in self.consumer:
                try:
                    self.process_message(msg.topic, msg.value)
                    self.consumer.commit()
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    traceback.print_exc()
                    self.consumer.commit()

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.running = False
            if self.consumer:
                self.consumer.close()
            if self.producer:
                self.producer.close()

    def get_stats(self) -> dict:
        """Get current statistics."""
        return {
            "total_errors": self.stats.total_errors,
            "by_category": dict(self.stats.by_category),
            "by_topic": dict(self.stats.by_topic),
            "by_worker": dict(self.stats.by_worker),
            "recent_count": len(self.stats.recent_errors),
            "retry_queue_size": len(self.retry_manager.retry_queue) if self.retry_manager else 0,
        }


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    monitor = DLQMonitor()
    monitor.run()
