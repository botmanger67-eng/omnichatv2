import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import (
    Column, String, DateTime, Text, ForeignKey, create_engine
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.future import select
from sqlalchemy import delete as sql_delete
from pydantic import BaseModel, Field

# ---------- Configuration ----------
DATABASE_URL = "sqlite+aiosqlite:///./omni_chat.db"
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
FRONTEND_DIR = Path("frontend")
assert FRONTEND_DIR.exists(), "Frontend directory 'frontend' must exist."

# ---------- SQLAlchemy Models ----------
Base = declarative_base()

class SessionDB(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    messages = relationship("MessageDB", back_populates="session", cascade="all, delete-orphan")

class MessageDB(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    file_url = Column(String, nullable=True)  # path relative to /uploads
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    session = relationship("SessionDB", back_populates="messages")

# ---------- Pydantic Schemas ----------
class MessageCreate(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str
    file_url: Optional[str] = None

class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    file_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class SessionCreate(BaseModel):
    title: Optional[str] = "New Chat"

class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse] = []

    class Config:
        from_attributes = True

class SessionListItem(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ---------- Database Setup ----------
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with SessionLocal() as session:
        yield session

# ---------- FastAPI Application ----------
app = FastAPI(title="OmniChat API", version="1.0.0")

# CORS - allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Static File Mounting ----------
app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ---------- Routes ----------
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>Frontend not built</h1>", status_code=404)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))

# Sessions
@app.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SessionDB).order_by(SessionDB.updated_at.desc()))
    sessions = result.scalars().all()
    return sessions

@app.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(session: SessionCreate, db: AsyncSession = Depends(get_db)):
    new_session = SessionDB(title=session.title)
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    # Prepopulate with a welcome message from assistant (optional)
    welcome_msg = MessageDB(
        session_id=new_session.id,
        role="assistant",
        content="Hello! I'm OmniChat. How can I help you today?"
    )
    db.add(welcome_msg)
    await db.commit()
    await db.refresh(new_session)
    return new_session

@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SessionDB).where(SessionDB.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SessionDB).where(SessionDB.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    await db.commit()
    return

# Messages
@app.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    # Verify session exists
    session_result = await db.execute(
        select(SessionDB).where(SessionDB.id == session_id)
    )
    if not session_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    result = await db.execute(
        select(MessageDB)
        .where(MessageDB.session_id == session_id)
        .order_by(MessageDB.created_at)
    )
    return result.scalars().all()

@app.post("/sessions/{session_id}/messages", response_model=MessageResponse, status_code=201)
async def create_message(
    session_id: str,
    message: MessageCreate,
    db: AsyncSession = Depends(get_db)
):
    # Verify session exists
    session_result = await db.execute(
        select(SessionDB).where(SessionDB.id == session_id)
    )
    if not session_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    new_msg = MessageDB(
        session_id=session_id,
        role=message.role,
        content=message.content,
        file_url=message.file_url
    )
    db.add(new_msg)
    # Update session's updated_at
    session_obj = session_result.scalar_one()
    session_obj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(new_msg)
    return new_msg

# File Upload
@app.post("/upload", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    # Generate unique filename to avoid collisions
    ext = Path(file.filename).suffix if file.filename else ""
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = UPLOAD_DIR / unique_name
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    # Return the relative URL that can be used in messages
    return {"file_url": f"/uploads/{unique_name}"}

# ---------- Run (only if executed directly) ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)