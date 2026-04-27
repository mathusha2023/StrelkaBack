from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE=".env"


class Settings(BaseSettings):

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8")

    host: str
    port: int

    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_database: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int
    jwt_refresh_token_expire_days: int
    redis_host: str
    redis_port: int
    redis_db: int
    redis_password: str
    S3_HOST: str
    S3_PORT: int
    S3_ADMIN_PORT: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str
    S3_SECURE: bool = False

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+asyncpg:"
            f"//{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_database}"
        )

    @property
    def redis_url(self) -> str:
        credentials = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{credentials}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def s3_endpoint(self) -> str:
        return f"{self.S3_HOST}:{self.S3_PORT}"


settings = Settings()
