from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATA_DIR}/generations.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    generations = relationship("Generation", back_populates="user", cascade="all, delete-orphan")


class Generation(Base):
    __tablename__ = "generations"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_type = Column(String)
    area = Column(Float)
    height = Column(Float)
    style = Column(String)
    description = Column(Text)
    furniture_json = Column(Text)
    result_json = Column(Text)
    time_sec = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="generations")


Base.metadata.create_all(bind=engine)


def _migrate():
    existing = {c["name"] for c in inspect(engine).get_columns("generations")}
    with engine.begin() as conn:
        for name, ddl in (("task_id", "VARCHAR"), ("result_json", "TEXT")):
            if name not in existing:
                conn.execute(text(f"ALTER TABLE generations ADD COLUMN {name} {ddl}"))


_migrate()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
