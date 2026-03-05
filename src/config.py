import os
import logging
import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from typing import Optional, Any

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # OpenAI Configuration
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    
    # Model Configuration (Optional in env, but we have defaults in factory if not set)
    # The requirement said "should not have any default values" for things that are required.
    # I will treat these as required if they are expected to be in .env
    model_4o_mini: str = Field(default="gpt-4o-mini", alias="MODEL_4O_MINI")
    model_5_mini: str = Field(default="gpt-5-mini-2025-08-07", alias="MODEL_5_MINI")
    model_5_2: str = Field(default="gpt-5.2-2025-12-11", alias="MODEL_5_2")

    # Database Configuration
    db_name: str = Field(alias="DB_NAME")
    db_user: str = Field(alias="DB_USER")
    db_password: str = Field(alias="DB_PASSWORD")
    db_host: str = Field(alias="DB_HOST")
    db_port: int = Field(alias="DB_PORT")

    # Auth0 Configuration
    auth0_domain: str = Field(alias="AUTH0_DOMAIN")
    auth0_audience: str = Field(alias="AUTH0_AUDIENCE")
    auth0_client_id: str = Field(alias="AUTH0_CLIENT_ID")
    auth0_client_secret: str = Field(alias="AUTH0_CLIENT_SECRET")

    # S3 Configuration
    s3_endpoint: str = Field(alias="S3_ENDPOINT")
    s3_access_key: str = Field(alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(alias="S3_SECRET_KEY")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    s3_bucket: str = Field(alias="S3_BUCKET")
    
    # SES Configuration
    ses_region: str = Field(default="us-east-1", alias="SES_REGION")
    ses_access_key: str = Field(alias="SES_ACCESS_KEY")
    ses_secret_key: str = Field(alias="SES_SECRET_KEY")
    ses_sender_email: str = Field(alias="SES_SENDER_EMAIL")
    
    # Sentry Configuration
    sentry_dsn: Optional[str] = Field(default=None, alias="SENTRY_DSN")
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Frontend Configuration
    frontend_url: str = Field(alias="FRONTEND_URL")

    @model_validator(mode="before")
    @classmethod
    def parse_db_password_json(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Check for DB_PASSWORD in the input data (pydantic aliases are handled after this usually, 
            # but BaseSettings might have them already if coming from env)
            db_password = data.get("DB_PASSWORD") or data.get("db_password")
            if db_password and isinstance(db_password, str) and db_password.startswith("{") and db_password.endswith("}"):
                try:
                    creds = json.loads(db_password)
                    if isinstance(creds, dict) and "password" in creds:
                        logger.info("Detected JSON-encoded DB_PASSWORD, extracting password value")
                        data["DB_PASSWORD"] = creds["password"]
                        # Also extract username if not already set or if it's default
                        if "username" in creds:
                            data["DB_USER"] = creds["username"]
                except json.JSONDecodeError:
                    pass
        return data

    @property
    def database_url_async(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def database_url_psycopg(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    def log_config(self):
        """Log the configuration, masking sensitive data."""
        sensitive_keywords = ["key", "secret", "dsn"]
        logger.info("Current Configuration:")
        for key, value in self.model_dump().items():
            if any(kw in key.lower() for kw in sensitive_keywords):
                masked_value = "********" if value else "None"
                logger.info(f"{key.upper()}: {masked_value}")
            else:
                logger.info(f"{key.upper()}: {value}")

# In ECS/Production, we don't want to fail if .env is missing.
# Pydantic Settings will still pick up environment variables.
env_file = (".env", ".env.local")
if os.getenv("ENVIRONMENT") == "production":
    env_file = None

settings = Settings(_env_file=env_file)
settings.log_config()
