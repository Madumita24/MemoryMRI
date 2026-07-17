from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from memory_mri.db.models import Base


def create_sqlite_session(database_url: str) -> Session:
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return Session(engine)
