from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings

engine = create_engine(
    settings().database_url,
    connect_args={"check_same_thread": False}
    if settings().database_url.startswith("sqlite")
    else {
        "connect_timeout": 5,
        "options": "-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=60000",
    },
    **(
        {"pool_size": 5, "max_overflow": 5, "pool_timeout": 5}
        if settings().database_url.startswith("postgresql")
        else {}
    ),
    pool_pre_ping=True,
)


def get_db():
    with Session(engine) as session:
        yield session
