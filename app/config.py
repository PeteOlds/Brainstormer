import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def get_env(key: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


class Config:
    # Flask
    SECRET_KEY = get_env("SECRET_KEY", required=True)
    FLASK_ENV = get_env("FLASK_ENV", "production")
    JSON_SORT_KEYS = False

    # Database
    SQLALCHEMY_DATABASE_URI = get_env("DATABASE_URL", required=True)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 300,
    }

    # Redis
    REDIS_URL = get_env("REDIS_URL", "redis://localhost:6379")

    # Ollama
    OLLAMA_BASE_URL = get_env("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_TIMEOUT = int(get_env("OLLAMA_TIMEOUT", "120"))

    # JWT Authentication
    JWT_SECRET_KEY = get_env("JWT_SECRET_KEY", required=True)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=int(get_env("JWT_ACCESS_TOKEN_EXPIRES", "900")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(seconds=int(get_env("JWT_REFRESH_TOKEN_EXPIRES", "604800")))
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_COOKIE_SECURE = FLASK_ENV == "production"
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_COOKIE_SAMESITE = "Strict"
    JWT_ACCESS_COOKIE_NAME = "access_token"
    JWT_REFRESH_COOKIE_NAME = "refresh_token"

    # Encryption (Fernet)
    FERNET_KEY = get_env("FERNET_KEY", required=True)

    # Celery
    CELERY_BROKER_URL = get_env("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = get_env("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TIMEZONE = "UTC"
    CELERY_ENABLE_UTC = True
    CELERY_TASK_ACKS_LATE = True
    CELERY_TASK_REJECT_ON_WORKER_LOST = True
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1
    CELERY_TASK_SOFT_TIME_LIMIT = 120
    CELERY_TASK_TIME_LIMIT = 150
    CELERY_TASK_ROUTES = {
        "app.tasks.ollama_tasks.*": {"queue": "ollama"},
        "app.tasks.maintenance_tasks.*": {"queue": "default"},
    }
    CELERY_BEAT_SCHEDULE = {
        "check-due-prompts": {
            "task": "app.tasks.ollama_tasks.check_due_prompts",
            "schedule": 60.0,
        },
    }

    # Rate Limiting
    RATE_LIMIT_STORAGE_URL = get_env("RATE_LIMIT_STORAGE_URL", "redis://localhost:6379/2")
    RATE_LIMIT_DEFAULT = "100 per minute"
    RATE_LIMIT_HEADERS_ENABLED = True

    # Security
    SESSION_COOKIE_SECURE = FLASK_ENV == "production"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"

    # Prompt Encryption
    ENCRYPT_PROMPTS = True

    # Prompt Templates
    PROMPT_TEMPLATES_DIR = "app/prompt_templates"


class DevelopmentConfig(Config):
    FLASK_ENV = "development"
    DEBUG = True
    SQLALCHEMY_ECHO = False
    JWT_COOKIE_SECURE = False


class ProductionConfig(Config):
    FLASK_ENV = "production"
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    JWT_COOKIE_SECURE = True


class TestingConfig(Config):
    FLASK_ENV = "testing"
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    REDIS_URL = "redis://localhost:6379/3"
    CELERY_BROKER_URL = "redis://localhost:6379/3"
    CELERY_RESULT_BACKEND = "redis://localhost:6379/3"
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    WTF_CSRF_ENABLED = False
    JWT_COOKIE_SECURE = False
    SQLALCHEMY_ENGINE_OPTIONS = {}
    RATELIMIT_ENABLED = False
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_COOKIE_CSRF_PROTECT = False
    JWT_ACCESS_CSRF_HEADER_NAME = "X-CSRF-TOKEN"
    JWT_REFRESH_CSRF_HEADER_NAME = "X-CSRF-TOKEN"


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}