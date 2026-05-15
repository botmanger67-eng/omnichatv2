"""
Database configuration and ORM models for OmniChat.

Uses SQLAlchemy with SQLite backend. Defines models for ChatSession, Message,
Attachment, and VoiceRecording with relationships and indexes.
"""

from datetime import datetime
from typing import AsyncGenerator, Generator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# SQLite database URL – can be overridden via environment variable in production
DATABASE_URL = "sqlite:///./omnichat.db"

# Engine with thread safety for SQLite
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,  # Set to True for debugging SQL
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base
Base = declarative_base()


class ChatSession(Base):
    """Represents a chat session with a title and timestamps."""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    messages = relationship("Message", back_populates="chat_session", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, title='{self.title}')>"


class Message(Base):
    """Represents a single message in a chat session."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(
        Enum("user", "assistant", "system", name="message_role"),
        nullable=False,
        comment="Originator of the message: user, assistant, or system",
    )
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True, comment="Number of tokens in the message content")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    chat_session = relationship("ChatSession", back_populates="messages")
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")
    voice_recordings = relationship("VoiceRecording", back_populates="message", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role='{self.role}', session_id={self.chat_session_id})>"


class Attachment(Base):
    """Represents a file attached to a message."""

    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=True, comment="MIME type or extension hint")
    file_size = Column(Integer, nullable=True, comment="Size in bytes")
    file_path = Column(String(512), nullable=False, comment="Server-side file path")
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    message = relationship("Message", back_populates="attachments")

    def __repr__(self) -> str:
        return f"<Attachment(id={self.id}, filename='{self.filename}')>"


class VoiceRecording(Base):
    """Represents a voice recording attached to a message."""

    __tablename__ = "voice_recordings"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    duration = Column(Integer, nullable=True, comment="Duration in seconds")
    file_path = Column(String(512), nullable=False, comment="Server-side file path")
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    message = relationship("Message", back_populates="voice_recordings")

    def __repr__(self) -> str:
        return f"<VoiceRecording(id={self.id}, filename='{self.filename}')>"


def create_tables() -> None:
    """Create all database tables (if they don't exist)."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[Session, None]:
    """
    Async-compatible version of get_db for use with async endpoints.

    Uses synchronous SQLAlchemy session inside a thread pool executor.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()