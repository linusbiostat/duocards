"""
Pydantic & SQLAlchemy models for the flashcard app.
Implements SM-2 spaced repetition fields.
"""

from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, create_engine, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()

# SQLAlchemy ORM Model
class CardDB(Base):
    __tablename__ = "cards"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String(255), nullable=False, index=True)
    translation = Column(String(500), nullable=False)
    grammar = Column(Text, nullable=True)
    example = Column(Text, nullable=True)
    audio_url = Column(String(500), nullable=True)
    
    # SM-2 Spaced Repetition fields
    ease_factor = Column(Float, default=2.5)  # Starting EF
    interval = Column(Integer, default=0)      # Days until next review
    repetitions = Column(Integer, default=0)   # Successful reviews in a row
    next_review = Column(DateTime, default=datetime.utcnow)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to history
    history = relationship("ReviewHistory", back_populates="card", cascade="all, delete-orphan")


class ReviewHistory(Base):
    __tablename__ = "review_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False)
    quality = Column(Integer, nullable=False)  # 0-5
    reviewed_at = Column(DateTime, default=datetime.utcnow)
    
    card = relationship("CardDB", back_populates="history")


# Pydantic models for API
class CardCreate(BaseModel):
    word: str
    translation: str
    grammar: Optional[str] = None
    example: Optional[str] = None
    audio_url: Optional[str] = None


class CardResponse(BaseModel):
    id: int
    word: str
    translation: str
    grammar: Optional[str] = None
    example: Optional[str] = None
    audio_url: Optional[str] = None
    ease_factor: float
    interval: int
    repetitions: int
    next_review: datetime
    
    class Config:
        from_attributes = True


class ReviewHistoryResponse(BaseModel):
    id: int
    quality: int
    reviewed_at: datetime
    
    class Config:
        from_attributes = True


class CardDetailResponse(CardResponse):
    """Extended card response with history."""
    history: list[ReviewHistoryResponse] = []


class ReviewRequest(BaseModel):
    quality: int = Field(..., ge=0, le=5, description="0=complete blackout, 5=perfect")


class GenerateRequest(BaseModel):
    word: str
    source_lang: str = "Slowenisch"
    target_lang: str = "Deutsch"


class GenerateResponse(BaseModel):
    """Enhanced generation response with dictionary-style content."""
    word: str
    translation: str
    grammar: str  # Detailed grammar with tables in HTML/markdown
    examples: list[str]  # 3 example sentences to choose from
    synonyms: list[dict]  # [{"word": "čas", "translation": "time"}, ...]
    usage: str  # Usage explanation
    meaning: str  # Meaning/definition


# Database setup
def get_engine(db_path: str = "flashcards.db"):
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db(engine):
    Base.metadata.create_all(engine)


def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()
