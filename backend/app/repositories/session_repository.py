import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.models.user_session import UserSession
from backend.app.repositories.base import BaseRepository


class SessionRepository(BaseRepository):
    def get_by_id(self, session_id: uuid.UUID) -> Optional[UserSession]:
        return self.db.get(UserSession, session_id)

    def get_by_token_hash(self, token_hash: str) -> Optional[UserSession]:
        stmt = select(UserSession).where(UserSession.token_hash == token_hash)
        return self.db.scalars(stmt).first()

    def create(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> UserSession:
        session = UserSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            last_seen_at=datetime.now(timezone.utc),
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def touch(self, session_id: uuid.UUID) -> Optional[UserSession]:
        session = self.get_by_id(session_id)
        if not session:
            return None
        session.last_seen_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(session)
        return session

    def revoke(self, session_id: uuid.UUID) -> bool:
        session = self.get_by_id(session_id)
        if not session:
            return False
        session.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount

    def rotate(
        self,
        old_session_id: uuid.UUID,
        new_token_hash: str,
        new_expires_at: datetime,
    ) -> Optional[UserSession]:
        """
        Atomically revokes the old session and creates a new one in a single transaction.
        """
        old_session = self.get_by_id(old_session_id)
        if not old_session:
            return None

        # Revoke old session
        old_session.revoked_at = datetime.now(timezone.utc)

        # Create new session
        new_session = UserSession(
            user_id=old_session.user_id,
            token_hash=new_token_hash,
            expires_at=new_expires_at,
            last_seen_at=datetime.now(timezone.utc),
        )
        self.db.add(new_session)
        self.db.commit()
        self.db.refresh(new_session)
        return new_session
