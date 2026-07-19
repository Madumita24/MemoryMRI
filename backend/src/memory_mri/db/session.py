from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from memory_mri.db.models import Base

_ENGINES: list[Engine] = []


def create_sqlite_session(database_url: str) -> Session:
    engine = create_engine(database_url, future=True)
    _ENGINES.append(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def dispose_sqlite_engines() -> None:
    while _ENGINES:
        engine = _ENGINES.pop()
        engine.dispose()
