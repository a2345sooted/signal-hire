from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    @property
    def database_url_async(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def database_url_psycopg(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

settings = Settings()
