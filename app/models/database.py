from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Get database URL from environment variable or use default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./random_draw.db")

# If using Heroku with Postgres, we need to modify the URL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL)

# Create session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for declarative models
Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Room(Base):
    __tablename__ = "rooms"

    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_coin_flip = Column(Boolean, default=False)
    min_value = Column(Integer, default=1)
    max_value = Column(Integer, default=100)
    with_replacement = Column(Boolean, default=True)
    
    # Relationship with logs
    logs = relationship("Log", back_populates="room")

class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_name = Column(String)
    action = Column(String)
    result = Column(String)
    
    # Relationship with room
    room = relationship("Room", back_populates="logs")

# Create tables in the database
def create_tables():
    Base.metadata.create_all(bind=engine) 