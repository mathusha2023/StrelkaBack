from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE=".env.develop"


class Settings(BaseSettings):

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8")

    host: str
    port: int

    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_database: str

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+asyncpg:"
            f"//{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_database}"
        )


settings = Settings()