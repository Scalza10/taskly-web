from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Where `npm run build` in frontend/ writes the page. Not in git.
PACKAGE_STATIC = Path(__file__).parent / "static"


class Settings(BaseSettings):
    """Read from the environment and `.env` in the working directory."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The SQLite file. docker-compose.yml sets it to /data/taskly.db, on the mounted volume.
    db_path: str = "./data/taskly.db"

    # The built page. If the folder doesn't exist (no build yet), the API runs without a page.
    static_dir: str = str(PACKAGE_STATIC)
