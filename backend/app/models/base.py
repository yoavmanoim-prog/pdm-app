from sqlalchemy.orm import DeclarativeBase


# All models inherit from this Base.
# SQLAlchemy uses it to know which classes are database tables.
class Base(DeclarativeBase):
    pass
