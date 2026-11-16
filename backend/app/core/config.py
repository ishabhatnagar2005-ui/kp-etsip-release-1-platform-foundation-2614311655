"""Load deployment configuration without embedding credentials."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Describe database, browser, and authentication configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_db: str = "etsip"
    jwt_secret: str = ""
    admin_password: str = ""
    demo_password: str = ""
    cors_origins: str = "http://localhost:5173"
    seed_on_startup: bool = True

    def validate_secrets(self) -> None:
        """Reject missing and public example credentials before startup."""
        if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("replace-"):
            raise ValueError("JWT_SECRET must be a unique random value of at least 32 characters")
        if self.seed_on_startup:
            for name in ("admin_password", "demo_password"):
                value = getattr(self, name)
                if len(value) < 12 or len(value.encode()) > 72 or "\x00" in value or value.startswith("replace-"):
                    raise ValueError(f"{name.upper()} must be a unique password of 12-72 bytes")
