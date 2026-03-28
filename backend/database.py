from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "promos.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String(50), nullable=False, index=True)       # 'aldi', 'lidl', ...
    name = Column(String(500), nullable=False)
    category = Column(String(100), default="Autre", index=True)
    original_price = Column(Float, nullable=True)
    promo_price = Column(Float, nullable=True)
    discount_percent = Column(Float, nullable=True)
    image_url = Column(String(1000), nullable=True)
    description = Column(Text, nullable=True)
    valid_from = Column(String(50), nullable=True)
    valid_until = Column(String(50), nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
