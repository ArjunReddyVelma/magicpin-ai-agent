import uuid
from datetime import datetime
from typing import Optional, List, Tuple, Any
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.models.suggested_action import SuggestedAction
from backend.app.repositories.base import BaseRepository


class ActionRepository(BaseRepository):
    def get_by_id(
        self, merchant_id: uuid.UUID, action_id: uuid.UUID
    ) -> Optional[SuggestedAction]:
        stmt = select(SuggestedAction).where(
            SuggestedAction.id == action_id,
            SuggestedAction.merchant_id == merchant_id,
        )
        return self.db.scalars(stmt).first()

    def list_actions(
        self,
        merchant_id: uuid.UUID,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[SuggestedAction], int]:
        stmt = select(SuggestedAction).where(SuggestedAction.merchant_id == merchant_id)

        if status is not None:
            stmt = stmt.where(SuggestedAction.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(SuggestedAction.created_at.desc(), SuggestedAction.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        items = list(self.db.scalars(stmt).all())
        return items, total

    def create(
        self,
        merchant_id: uuid.UUID,
        action_type: str,
        title: str,
        description: str,
        conversation_id: Optional[uuid.UUID] = None,
        payload: Optional[Any] = None,
        created_by: str = "assistant",
        status: str = "pending",
        commit: bool = True,
    ) -> SuggestedAction:
        action = SuggestedAction(
            merchant_id=merchant_id,
            conversation_id=conversation_id,
            action_type=action_type,
            title=title.strip(),
            description=description.strip(),
            payload=payload,
            status=status,
            created_by=created_by,
        )
        self.db.add(action)
        if commit:
            self.db.commit()
            self.db.refresh(action)
        else:
            self.db.flush()
        return action

    def update_content(
        self,
        merchant_id: uuid.UUID,
        action_id: uuid.UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        payload: Optional[Any] = None,
    ) -> Optional[SuggestedAction]:
        action = self.get_by_id(merchant_id=merchant_id, action_id=action_id)
        if not action or action.status != "pending":
            return None

        if title is not None:
            action.title = title.strip()
        if description is not None:
            action.description = description.strip()
        if payload is not None:
            action.payload = payload

        self.db.commit()
        self.db.refresh(action)
        return action

    def transition_status(
        self, merchant_id: uuid.UUID, action_id: uuid.UUID, target_status: str
    ) -> Tuple[Optional[SuggestedAction], bool]:
        """
        Transition action status from pending to approved or dismissed.
        Returns:
            (None, False) if not found
            (action, False) if transition is invalid (e.g. action already approved/dismissed)
            (action, True) if transition succeeded
        """
        action = self.get_by_id(merchant_id=merchant_id, action_id=action_id)
        if not action:
            return None, False

        # Only 'pending' items can be approved or dismissed
        if action.status != "pending":
            return action, False

        if target_status not in ("approved", "dismissed"):
            return action, False

        action.status = target_status
        action.reviewed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(action)
        return action, True

    def count_pending(self, merchant_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(SuggestedAction)
            .where(
                SuggestedAction.merchant_id == merchant_id,
                SuggestedAction.status == "pending",
            )
        )
        return self.db.scalar(stmt) or 0
