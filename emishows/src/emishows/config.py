import os

from pydantic import BaseModel


class Config(BaseModel):
    db_host: str = os.getenv("EMISHOWS_DB_HOST", "localhost")
    db_port: int = int(os.getenv("EMISHOWS_DB_PORT", 34000))
    emitimes_host: str = os.getenv("EMISHOWS_EMITIMES_HOST", "localhost")
    emitimes_port: int = int(os.getenv("EMISHOWS_EMITIMES_PORT", 36000))
    emitimes_user: str = os.getenv("EMISHOWS_EMITIMES_USER", "user")
    emitimes_password: str = os.getenv(
        "EMISHOWS_EMITIMES_PASSWORD", "password"
    )
    emitimes_calendar: str = os.getenv(
        "EMISHOWS_EMITIMES_CALENDAR", "emitimes"
    )


config = Config()
