import uuid
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.models.context_item import ContextItem
from backend.app.repositories.base import BaseRepository


class ContextRepository(BaseRepository):
    def get_by_id(
        self, merchant_id: uuid.UUID, context_id: uuid.UUID
    ) -> Optional[ContextItem]:
        stmt = select(ContextItem).where(
            ContextItem.id == context_id,
            ContextItem.merchant_id == merchant_id,
        )
        return self.db.scalars(stmt).first()

    def list_items(
        self,
        merchant_id: uuid.UUID,
        item_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ContextItem], int]:
        query = select(ContextItem).where(ContextItem.merchant_id == merchant_id)

        if item_type is not None:
            query = query.where(ContextItem.item_type == item_type)
        if is_active is not None:
            query = query.where(ContextItem.is_active == is_active)

        # Count total
        count_stmt = select(func.count()).select_from(query.subquery())
        total = self.db.scalar(count_stmt) or 0

        # Pagination with deterministic ordering
        offset = (page - 1) * page_size
        query = (
            query.order_by(ContextItem.created_at.desc(), ContextItem.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        items = list(self.db.scalars(query).all())
        return items, total

    def create(
        self,
        merchant_id: uuid.UUID,
        item_type: str,
        title: str,
        content: str,
        is_active: bool = True,
    ) -> ContextItem:
        item = ContextItem(
            merchant_id=merchant_id,
            item_type=item_type,
            title=title.strip(),
            content=content.strip(),
            is_active=is_active,
            version=1,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_with_version(
        self,
        merchant_id: uuid.UUID,
        context_id: uuid.UUID,
        expected_version: int,
        item_type: Optional[str] = None,
        title: Optional[str] = None,
        content: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[Optional[ContextItem], bool]:
        """
        Updates a context item checking expected version for optimistic concurrency.
        Returns:
            (None, False) if item not found
            (current_item, True) if version conflict (stale write)
            (updated_item, False) if update succeeded
        """
        item = self.get_by_id(merchant_id=merchant_id, context_id=context_id)
        if not item:
            return None, False

        if item.version != expected_version:
            # Stale version: return current item and conflict indicator
            return item, True

        # Versions match: apply updates and increment version
        if item_type is not None:
            item.item_type = item_type
        if title is not None:
            item.title = title.strip()
        if content is not None:
            item.content = content.strip()
        if is_active is not None:
            item.is_active = is_active

        item.version += 1
        self.db.commit()
        self.db.refresh(item)
        return item, False

    def delete(self, merchant_id: uuid.UUID, context_id: uuid.UUID) -> bool:
        item = self.get_by_id(merchant_id=merchant_id, context_id=context_id)
        if not item:
            return False
        self.db.delete(item)
        self.db.commit()
        return True
