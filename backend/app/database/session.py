from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings

engine = create_engine(
    settings().database_url,
    connect_args={"check_same_thread": False}
    if settings().database_url.startswith("sqlite")
    else {},
    pool_pre_ping=True,
)


def get_db():
    with Session(engine) as session:
        yield session
