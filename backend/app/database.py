import os
from functools import lru_cache
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # lru_cache makes this a singleton — engine is created once and reused for all requests
    # thread-safe and lazy: DATABASE_URL is only read on the first real request, not at import time
    return create_engine(
        os.environ["DATABASE_URL"],
        pool_pre_ping=True,  # checks the connection is alive before using it
        pool_size=5,         # keep 5 connections open and ready
        max_overflow=10,     # allow up to 10 extra connections under heavy load
    )


def get_db():
    # FastAPI injects this into any route that declares: db: Session = Depends(get_db)
    # yield means the session is automatically closed after the request finishes
    db: Session = sessionmaker(bind=get_engine())()
    try:
        yield db
    finally:
        db.close()
