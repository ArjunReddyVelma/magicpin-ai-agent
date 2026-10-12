import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.user import User
from backend.app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> Optional[User]:
        normalized = email.lower().strip()
        stmt = select(User).where(User.email == normalized)
        return self.db.scalars(stmt).first()

    def create(
        self,
        full_name: str,
        email: str,
        password_hash: str,
        is_active: bool = True,
    ) -> User:
        user = User(
            full_name=full_name.strip(),
            email=email.lower().strip(),
            password_hash=password_hash,
            is_active=is_active,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_password(self, user_id: uuid.UUID, password_hash: str) -> Optional[User]:
        user = self.get_by_id(user_id)
        if not user:
            return None
        user.password_hash = password_hash
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user_id: uuid.UUID) -> bool:
        user = self.get_by_id(user_id)
        if not user:
            return False
        self.db.delete(user)
        self.db.commit()
        return True
