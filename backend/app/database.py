from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session

# Both start as None — set by init_db() when the app starts
_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def init_db(database_url: str) -> None:
    # Called once in the FastAPI lifespan handler at startup
    # This is the "lazy" pattern — DATABASE_URL is never read at import time
    global _engine, _SessionLocal
    _engine = create_engine(
        database_url,
        pool_pre_ping=True,  # checks connection is alive before using it
        pool_size=5,
        max_overflow=10,
    )
    _SessionLocal = sessionmaker(bind=_engine)


def get_db():
    # FastAPI injects this into routes via Depends(get_db)
    # yields a session and closes it automatically after the request
    assert _SessionLocal is not None, "init_db() was not called at startup"
    db: Session = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
