from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, DateTime


class Base(DeclarativeBase):
    pass


class ChatConversation(Base):
    """Modèle représentant une conversation ou canal de discussion."""
    __tablename__ = "chat_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    type: Mapped[str] = mapped_column(String(20), default="channel")  # channel ou direct
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_message_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_message_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "title": self.title,
            "type": self.type,
            "avatar_url": self.avatar_url,
            "description": self.description,
            "last_message_text": self.last_message_text,
            "last_message_time": self.last_message_time.strftime("%H:%M") if self.last_message_time else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ChatMessage(Base):
    """Modèle représentant un message instantané."""
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    sender_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    sender_name: Mapped[str] = mapped_column(String(120), default="Utilisateur")
    sender_avatar: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="delivered")  # sent, delivered, read
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "sender_avatar": self.sender_avatar,
            "message": self.message,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "time_formatted": self.created_at.strftime("%H:%M") if self.created_at else "",
        }
