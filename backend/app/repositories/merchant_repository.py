import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.merchant_profile import MerchantProfile
from backend.app.repositories.base import BaseRepository


class MerchantRepository(BaseRepository):
    def get_by_id(self, merchant_id: uuid.UUID) -> Optional[MerchantProfile]:
        return self.db.get(MerchantProfile, merchant_id)

    def get_by_user_id(self, user_id: uuid.UUID) -> Optional[MerchantProfile]:
        stmt = select(MerchantProfile).where(MerchantProfile.user_id == user_id)
        return self.db.scalars(stmt).first()

    def create(
        self,
        user_id: uuid.UUID,
        business_name: str,
        category: Optional[str] = None,
        location: Optional[str] = None,
        description: Optional[str] = None,
        timezone: str = "Asia/Kolkata",
    ) -> MerchantProfile:
        profile = MerchantProfile(
            user_id=user_id,
            business_name=business_name.strip(),
            category=category.strip() if category else None,
            location=location.strip() if location else None,
            description=description.strip() if description else None,
            timezone=timezone.strip() if timezone else "Asia/Kolkata",
        )
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def update(
        self,
        merchant_id: uuid.UUID,
        business_name: Optional[str] = None,
        category: Optional[str] = None,
        location: Optional[str] = None,
        description: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> Optional[MerchantProfile]:
        profile = self.get_by_id(merchant_id)
        if not profile:
            return None
        if business_name is not None:
            profile.business_name = business_name.strip()
        if category is not None:
            profile.category = category.strip() if category else None
        if location is not None:
            profile.location = location.strip() if location else None
        if description is not None:
            profile.description = description.strip() if description else None
        if timezone is not None:
            profile.timezone = timezone.strip()
        self.db.commit()
        self.db.refresh(profile)
        return profile
