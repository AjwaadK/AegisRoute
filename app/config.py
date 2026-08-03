"""Project environment configuration."""

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_project_environment() -> None:
    """Load .env defaults without replacing explicitly supplied configuration."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
