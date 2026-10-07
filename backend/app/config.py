import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://autotax:autotax@localhost:5434/autotax"
    )
    # Set JWT_SECRET (32+ random bytes) in any shared or production deployment.
    jwt_secret: str = os.environ.get("JWT_SECRET", "dev-only-insecure-secret-change-me-0123456789")
    jwt_ttl_minutes: int = int(os.environ.get("JWT_TTL_MINUTES", "720"))
    cors_origins: tuple[str, ...] = tuple(
        o for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o
    )
    fetch_fx_automatically: bool = os.environ.get("FETCH_FX", "1") == "1"


settings = Settings()
