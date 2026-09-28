from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from the environment and `.env` in the working directory."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The SQLite file. docker-compose.yml sets it to /data/taskly.db, on the mounted volume.
    db_path: str = "./data/taskly.db"
