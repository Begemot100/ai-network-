"""
Configuration module for the Distributed AI Network Main Server.
Uses Pydantic Settings for type-safe configuration with environment variables.
"""

import os
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # =========================================================================
    # Database
    # =========================================================================
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5433, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="ai", alias="POSTGRES_USER")
    postgres_password: str = Field(default="ai_secure_password", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="ainetwork", alias="POSTGRES_DB")

    db_pool_size: int = Field(default=20, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")

    @property
    def database_url(self) -> str:
        """Construct database URL from components."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Construct async database URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # =========================================================================
    # Redis
    # =========================================================================
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6380, alias="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")
    redis_db: int = Field(default=0, alias="REDIS_DB")

    @property
    def redis_url(self) -> str:
        """Construct Redis URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # =========================================================================
    # Kafka
    # =========================================================================
    kafka_bootstrap: str = Field(default="localhost:29092", alias="KAFKA_BOOTSTRAP")

    kafka_topic_tasks: str = Field(default="ai.tasks.v2", alias="KAFKA_TOPIC_TASKS")
    kafka_topic_results: str = Field(default="ai.results.v2", alias="KAFKA_TOPIC_RESULTS")
    kafka_topic_events: str = Field(default="ai.events.v1", alias="KAFKA_TOPIC_EVENTS")
    kafka_topic_audit: str = Field(default="ai.audit.v1", alias="KAFKA_TOPIC_AUDIT")

    # =========================================================================
    # Server
    # =========================================================================
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_port: int = Field(default=8020, alias="SERVER_PORT")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # =========================================================================
    # Worker Management
    # =========================================================================
    worker_task_timeout: int = Field(default=300, alias="WORKER_TASK_TIMEOUT")
    worker_heartbeat_interval: int = Field(default=30, alias="WORKER_HEARTBEAT_INTERVAL")
    worker_offline_threshold: int = Field(default=120, alias="WORKER_OFFLINE_THRESHOLD")

    # =========================================================================
    # Validation & Rewards
    # =========================================================================
    validation_match_reward_a: float = Field(default=0.05, alias="VALIDATION_MATCH_REWARD_A")
    validation_match_reward_b: float = Field(default=0.02, alias="VALIDATION_MATCH_REWARD_B")
    validation_mismatch_penalty: float = Field(default=0.1, alias="VALIDATION_MISMATCH_PENALTY")
    validation_mismatch_bonus_b: float = Field(default=0.01, alias="VALIDATION_MISMATCH_BONUS_B")

    # =========================================================================
    # Reputation
    # =========================================================================
    reputation_increase_on_success: float = Field(default=0.01, alias="REPUTATION_INCREASE_ON_SUCCESS")
    reputation_decrease_on_failure: float = Field(default=0.1, alias="REPUTATION_DECREASE_ON_FAILURE")
    reputation_validator_bonus: float = Field(default=0.005, alias="REPUTATION_VALIDATOR_BONUS")
    reputation_min: float = Field(default=0.0, alias="REPUTATION_MIN")
    reputation_max: float = Field(default=10.0, alias="REPUTATION_MAX")

    # =========================================================================
    # Golden Tasks
    # =========================================================================
    golden_task_ratio: float = Field(default=0.1, alias="GOLDEN_TASK_RATIO")
    golden_task_penalty_multiplier: float = Field(default=2.0, alias="GOLDEN_TASK_PENALTY_MULTIPLIER")

    # =========================================================================
    # Task Rewards by Type
    # =========================================================================
    reward_text: float = Field(default=0.05, alias="REWARD_TEXT")
    reward_reverse: float = Field(default=0.10, alias="REWARD_REVERSE")
    reward_math: float = Field(default=0.15, alias="REWARD_MATH")
    reward_llm: float = Field(default=0.50, alias="REWARD_LLM")
    reward_heavy: float = Field(default=1.00, alias="REWARD_HEAVY")
    reward_sentiment: float = Field(default=0.05, alias="REWARD_SENTIMENT")
    reward_classification: float = Field(default=0.08, alias="REWARD_CLASSIFICATION")
    reward_extraction: float = Field(default=0.12, alias="REWARD_EXTRACTION")

    def get_task_reward(self, task_type: str) -> float:
        """Get reward amount for a task type."""
        rewards = {
            "text": self.reward_text,
            "reverse": self.reward_reverse,
            "math": self.reward_math,
            "llm": self.reward_llm,
            "heavy": self.reward_heavy,
            "sentiment": self.reward_sentiment,
            "classification": self.reward_classification,
            "extraction": self.reward_extraction,
        }
        return rewards.get(task_type, self.reward_text)

    # =========================================================================
    # Security
    # =========================================================================
    jwt_secret: str = Field(default="change-me-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiry_minutes: int = Field(default=15, alias="JWT_EXPIRY_MINUTES")
    jwt_refresh_expiry_days: int = Field(default=7, alias="JWT_REFRESH_EXPIRY_DAYS")

    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into list."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]

    # =========================================================================
    # Feature Flags
    # =========================================================================
    feature_golden_tasks: bool = Field(default=True, alias="FEATURE_GOLDEN_TASKS")
    feature_reputation_decay: bool = Field(default=True, alias="FEATURE_REPUTATION_DECAY")
    feature_collusion_detection: bool = Field(default=True, alias="FEATURE_COLLUSION_DETECTION")
    feature_websocket_updates: bool = Field(default=True, alias="FEATURE_WEBSOCKET_UPDATES")

    # =========================================================================
    # Development
    # =========================================================================
    dev_mode: bool = Field(default=False, alias="DEV_MODE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience exports
settings = get_settings()
