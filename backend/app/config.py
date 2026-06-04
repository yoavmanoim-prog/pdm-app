from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # database connection string — read from environment variable
    DATABASE_URL: str

    # "local" = engineer's workspace, "remote" = shared vault server
    VAULT_MODE: str = "local"

    # URL of the remote vault — only used when VAULT_MODE=local
    REMOTE_VAULT_URL: str = "http://localhost:8001"

    # S3 bucket for storing SVG and PDF files
    S3_BUCKET: str = ""

    # AWS region — boto3 also reads this automatically
    AWS_REGION: str = "us-east-1"

    class Config:
        # pydantic-settings reads from .env file if it exists, otherwise from env vars
        env_file = ".env"
        extra = "ignore"  # ignore unknown env vars instead of crashing


# single instance used everywhere in the app — import this, not the class
settings = Settings()
