"""
Database configuration using SQLAlchemy + SQLite.
File database.sqlite sẽ được tạo tự động trong thư mục data/.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'database.sqlite')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # cần thiết cho SQLite + FastAPI
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency để inject DB session vào mỗi request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
