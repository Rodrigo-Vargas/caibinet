from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as DBSession
from typing import Generator
from ..config import settings
from .models import Base


def get_engine():
    settings.ensure_data_dir()
    return create_engine(
        settings.db_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )


# Module-level engine & SessionLocal – recreated on first import
engine = get_engine()
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[DBSession, None, None]:
    """FastAPI dependency – yields a database session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
