import logging
from datetime import datetime, timezone
from sqlalchemy import select, desc, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
try:
    from .models import Base, ChatConversation, ChatMessage
except ImportError:
    from models import Base, ChatConversation, ChatMessage

logger = logging.getLogger("melodi_chat_server.database")


class DatabaseManager:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = create_async_engine(db_url, echo=False)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def reconnect(self, new_db_url: str):
        old_engine = self.engine
        old_session = self.session_factory
        old_url = self.db_url

        logger.info(f"[Database] Reconnexion vers la nouvelle base : {new_db_url}...")
        self.db_url = new_db_url
        self.engine = create_async_engine(new_db_url, echo=False)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

        try:
            await self.init_db()
            await old_engine.dispose()
            logger.info(f"[Database] Reconnexion et migration de schéma réussies !")
        except Exception as e:
            logger.error(f"[Database] Échec reconnexion: {e}, restauration de l'ancienne base.")
            self.db_url = old_url
            self.engine = old_engine
            self.session_factory = old_session
            raise

    @staticmethod
    async def test_connection(db_url: str) -> tuple[bool, str]:
        engine = None
        try:
            engine = create_async_engine(db_url, echo=False)
            async with engine.connect() as conn:
                from sqlalchemy import text
                await conn.execute(text("SELECT 1"))
            return True, "Connexion réussie"
        except Exception as e:
            return False, str(e)
        finally:
            if engine:
                await engine.dispose()

    async def init_db(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("[Database] Tables initialisées avec succès.")

        # Seed initial channels if database is completely empty
        async with self.session_factory() as session:
            res = await session.execute(select(ChatConversation).limit(1))
            if not res.scalar_one_or_none():
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                defaults = [
                    ChatConversation(
                        code="general",
                        title="Équipe Générale",
                        type="channel",
                        description="Canal de communication pour l'ensemble des collaborateurs",
                        last_message_text="Bienvenue sur le serveur de chat dédié !",
                        last_message_time=now,
                        created_at=now
                    ),
                    ChatConversation(
                        code="ventes",
                        title="Commercial & Ventes",
                        type="channel",
                        description="Opportunités, devis et commandes",
                        last_message_text="Canal ventes actif",
                        last_message_time=now,
                        created_at=now
                    ),
                    ChatConversation(
                        code="support",
                        title="Support Technique",
                        type="channel",
                        description="Assistance technique et incidents",
                        last_message_text="Serveur opérationnel sur port 7070",
                        last_message_time=now,
                        created_at=now
                    )
                ]
                session.add_all(defaults)
                await session.commit()
                logger.info("[Database] Canaux par défaut initialisés.")

    async def check_health(self) -> tuple[bool, str]:
        try:
            async with self.session_factory() as session:
                await session.execute(select(1))
            return True, "Base de données opérationnelle"
        except Exception as e:
            return False, str(e)

    async def get_conversations(self, current_user_id: str | None = None) -> list[ChatConversation]:
        async with self.session_factory() as session:
            stmt = select(ChatConversation).order_by(
                desc(ChatConversation.last_message_time),
                ChatConversation.id
            )
            res = await session.execute(stmt)
            all_convs = list(res.scalars().all())

            if not current_user_id:
                return all_convs

            visible = []
            for conv in all_convs:
                if conv.type == "channel":
                    visible.append(conv)
                elif conv.code.startswith("direct_"):
                    if current_user_id in conv.code or conv.code == "direct_direction":
                        visible.append(conv)
                else:
                    visible.append(conv)
            return visible

    async def get_conversation(self, conv_id: int) -> ChatConversation | None:
        async with self.session_factory() as session:
            stmt = select(ChatConversation).where(ChatConversation.id == conv_id)
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    async def get_or_create_direct_conversation(
        self,
        user1_id: str,
        user1_name: str,
        user2_id: str,
        user2_name: str
    ) -> ChatConversation:
        sorted_ids = sorted([str(user1_id), str(user2_id)])
        code = f"direct_{sorted_ids[0]}_{sorted_ids[1]}"

        async with self.session_factory() as session:
            stmt = select(ChatConversation).where(ChatConversation.code == code)
            res = await session.execute(stmt)
            conv = res.scalar_one_or_none()

            if not conv:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                conv = ChatConversation(
                    code=code,
                    title=f"{user2_name}",
                    type="direct",
                    description=f"Discussion directe avec {user2_name}",
                    last_message_text="Discussion démarrée",
                    last_message_time=now,
                    created_at=now
                )
                session.add(conv)
                await session.commit()
                await session.refresh(conv)

            return conv

    async def create_group_conversation(
        self,
        title: str,
        description: str | None = None,
        created_by_id: str | None = None,
        created_by_name: str = "Admin",
        member_ids: list[str] | None = None
    ) -> ChatConversation:
        import uuid
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        code = f"group_{uuid.uuid4().hex[:10]}"

        async with self.session_factory() as session:
            conv = ChatConversation(
                code=code,
                title=title,
                type="channel",
                description=description or f"Groupe créé par {created_by_name}",
                last_message_text="Groupe créé",
                last_message_time=now,
                created_at=now
            )
            session.add(conv)
            await session.flush()

            init_msg = ChatMessage(
                conversation_id=conv.id,
                sender_id=created_by_id,
                sender_name="Système",
                message=f"Le groupe « {title} » a été créé par {created_by_name}.",
                status="read",
                created_at=now
            )
            session.add(init_msg)
            await session.commit()
            await session.refresh(conv)
            return conv

    async def get_messages(self, conversation_id: int, limit: int = 50) -> list[ChatMessage]:
        async with self.session_factory() as session:
            stmt = select(ChatMessage).where(
                ChatMessage.conversation_id == conversation_id
            ).order_by(ChatMessage.id.asc()).limit(limit)
            res = await session.execute(stmt)
            return list(res.scalars().all())

    async def create_message(
        self,
        conversation_id: int,
        sender_id: str | None,
        sender_name: str,
        message: str,
        sender_avatar: str | None = None
    ) -> ChatMessage:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.session_factory() as session:
            msg = ChatMessage(
                conversation_id=conversation_id,
                sender_id=sender_id,
                sender_name=sender_name,
                sender_avatar=sender_avatar,
                message=message,
                status="delivered",
                created_at=now
            )
            session.add(msg)

            # Update parent conversation's last message
            conv_stmt = select(ChatConversation).where(ChatConversation.id == conversation_id)
            conv_res = await session.execute(conv_stmt)
            conv = conv_res.scalar_one_or_none()
            if conv:
                conv.last_message_text = (message[:50] + "...") if len(message) > 50 else message
                conv.last_message_time = now

            await session.commit()
            await session.refresh(msg)
            return msg

    async def delete_message(self, message_id: int) -> tuple[bool, int | None]:
        async with self.session_factory() as session:
            stmt = select(ChatMessage).where(ChatMessage.id == message_id)
            res = await session.execute(stmt)
            msg = res.scalar_one_or_none()
            if not msg:
                return False, None

            conv_id = msg.conversation_id
            await session.delete(msg)

            # Recompute last message
            last_stmt = select(ChatMessage).where(
                ChatMessage.conversation_id == conv_id
            ).order_by(desc(ChatMessage.id)).limit(1)
            last_res = await session.execute(last_stmt)
            last_msg = last_res.scalar_one_or_none()

            conv_stmt = select(ChatConversation).where(ChatConversation.id == conv_id)
            conv_res = await session.execute(conv_stmt)
            conv = conv_res.scalar_one_or_none()
            if conv:
                if last_msg:
                    conv.last_message_text = (last_msg.message[:50] + "...") if len(last_msg.message) > 50 else last_msg.message
                    conv.last_message_time = last_msg.created_at
                else:
                    conv.last_message_text = "Aucun message"
                    conv.last_message_time = conv.created_at

            await session.commit()
            return True, conv_id

    async def delete_conversation(self, conv_id: int) -> bool:
        async with self.session_factory() as session:
            stmt = select(ChatConversation).where(ChatConversation.id == conv_id)
            res = await session.execute(stmt)
            conv = res.scalar_one_or_none()
            if not conv:
                return False

            await session.execute(delete(ChatMessage).where(ChatMessage.conversation_id == conv_id))
            await session.delete(conv)
            await session.commit()
            return True

    async def get_stats(self) -> dict:
        from sqlalchemy import func
        async with self.session_factory() as session:
            total_convs = (await session.execute(select(func.count(ChatConversation.id)))).scalar() or 0
            total_msgs = (await session.execute(select(func.count(ChatMessage.id)))).scalar() or 0
            return {
                "total_conversations": total_convs,
                "total_messages": total_msgs
            }
