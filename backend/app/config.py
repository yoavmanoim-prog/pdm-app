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

    # home directory mount point inside the container.
    # user picks any subfolder when creating a repo — no restart needed.
    WATCH_BASE: str = "/watch"

    # comma-separated list of origins allowed to call this API cross-origin.
    # add http://localhost:3000 so the local frontend can call the remote vault.
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # --- authentication ---
    # secret used to sign/verify JWT login tokens. The default is for local dev
    # ONLY — production must override it with a strong random value injected from
    # AWS Secrets Manager (via External Secrets), the same way DATABASE_URL is.
    JWT_SECRET: str = "dev-insecure-change-me"
    # signing algorithm — HS256 is symmetric (same secret signs and verifies)
    JWT_ALGORITHM: str = "HS256"
    # how long a login token stays valid (minutes) before the user must log in again
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720  # 12 hours — a factory work shift

    # optional one-time admin bootstrap: if set and no admin exists yet, an admin
    # account with these credentials is created at startup. Leave blank to skip.
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    class Config:
        # pydantic-settings reads from .env file if it exists, otherwise from env vars
        env_file = ".env"
        extra = "ignore"  # ignore unknown env vars instead of crashing


# single instance used everywhere in the app — import this, not the class
settings = Settings()
