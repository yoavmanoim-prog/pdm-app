import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def _engine():
    return create_engine(os.environ["DATABASE_URL"])


def get_db():
    db = sessionmaker(bind=_engine())()
    try:
        yield db
    finally:
        db.close()
