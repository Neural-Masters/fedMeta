"""Profile CRUD operations and management."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from fedMeta.database import UserProfileORM, get_db_manager
    _HAS_SQLALCHEMY = True
except ImportError:
    _HAS_SQLALCHEMY = False

from fedMeta.profile.models import UserProfile

logger = logging.getLogger(__name__)


class ProfileManager:
    """CRUD operations for user profiles.

    Provides methods to create, read, update, and delete user profiles
    in the database, as well as convert between ORM and dataclass
    representations.
    """

    def __init__(self, session: Optional[Session] = None) -> None:
        self._session = session
        self._owns_session = session is None

    @property
    def session(self):
        """Get or create a database session."""
        if not _HAS_SQLALCHEMY:
            raise ImportError("sqlalchemy is required for ProfileManager operations")
        if self._session is None:
            self._session = get_db_manager().get_session()
        return self._session

    def create_profile(
        self,
        user_id: str,
        name: str,
        role: Optional[str] = None,
        expertise_level: Optional[str] = None,
        communication_style: Optional[str] = None,
        preferred_format: Optional[str] = None,
        domains: Optional[List[str]] = None,
        custom_rules: Optional[Dict[str, Any]] = None,
    ) -> UserProfile:
        """Create a new user profile.

        Args:
            user_id: Unique identifier for the user.
            name: Display name.
            role: Professional role.
            expertise_level: Skill level.
            communication_style: Preferred tone.
            preferred_format: Response format preference.
            domains: Domain interests.
            custom_rules: Custom rules dict.

        Returns:
            The created UserProfile.

        Raises:
            ValueError: If a profile for this user_id already exists.
        """
        existing = self.get_profile(user_id)
        if existing is not None:
            raise ValueError(f"Profile already exists for user_id={user_id!r}")

        orm_profile = UserProfileORM(
            user_id=user_id,
            name=name,
            role=role,
            expertise_level=expertise_level,
            communication_style=communication_style,
            preferred_format=preferred_format,
            domains=domains or [],
            custom_rules=custom_rules or {},
        )
        self.session.add(orm_profile)
        self.session.commit()
        self.session.refresh(orm_profile)
        logger.info("Created profile for user_id=%s", user_id)
        return self._orm_to_dataclass(orm_profile)

    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Retrieve a user profile by user_id.

        Args:
            user_id: The unique user identifier.

        Returns:
            The UserProfile if found, None otherwise.
        """
        stmt = select(UserProfileORM).where(UserProfileORM.user_id == user_id)
        result = self.session.execute(stmt).scalar_one_or_none()
        if result is None:
            return None
        return self._orm_to_dataclass(result)

    def get_or_create_profile(self, user_id: str, name: str = "User") -> UserProfile:
        """Get an existing profile or create a default one.

        Args:
            user_id: The unique user identifier.
            name: Default name for new profiles.

        Returns:
            The existing or newly created UserProfile.
        """
        profile = self.get_profile(user_id)
        if profile is not None:
            return profile
        return self.create_profile(user_id=user_id, name=name)

    def update_profile(
        self,
        user_id: str,
        updates: Dict[str, Any],
    ) -> Optional[UserProfile]:
        """Update fields on an existing profile.

        Args:
            user_id: The unique user identifier.
            updates: Dictionary of fields to update.

        Returns:
            The updated UserProfile, or None if not found.
        """
        stmt = select(UserProfileORM).where(UserProfileORM.user_id == user_id)
        orm_profile = self.session.execute(stmt).scalar_one_or_none()
        if orm_profile is None:
            logger.warning("Profile not found for user_id=%s", user_id)
            return None

        for key, value in updates.items():
            if hasattr(orm_profile, key):
                setattr(orm_profile, key, value)

        self.session.commit()
        self.session.refresh(orm_profile)
        logger.info("Updated profile for user_id=%s", user_id)
        return self._orm_to_dataclass(orm_profile)

    def delete_profile(self, user_id: str) -> bool:
        """Delete a user profile.

        Args:
            user_id: The unique user identifier.

        Returns:
            True if deleted, False if not found.
        """
        stmt = select(UserProfileORM).where(UserProfileORM.user_id == user_id)
        orm_profile = self.session.execute(stmt).scalar_one_or_none()
        if orm_profile is None:
            return False

        self.session.delete(orm_profile)
        self.session.commit()
        logger.info("Deleted profile for user_id=%s", user_id)
        return True

    def list_profiles(self, limit: int = 100, offset: int = 0) -> List[UserProfile]:
        """List all user profiles with pagination.

        Args:
            limit: Maximum number of profiles to return.
            offset: Number of profiles to skip.

        Returns:
            List of UserProfile objects.
        """
        stmt = select(UserProfileORM).limit(limit).offset(offset)
        results = self.session.execute(stmt).scalars().all()
        return [self._orm_to_dataclass(r) for r in results]

    def profile_to_system_prompt(self, user_id: str) -> Optional[str]:
        """Get the system prompt context for a user.

        Args:
            user_id: The unique user identifier.

        Returns:
            Formatted profile string for prompt injection, or None.
        """
        profile = self.get_profile(user_id)
        if profile is None:
            return None
        return profile.to_prompt_context()

    def close(self) -> None:
        """Close the session if owned by this manager."""
        if self._owns_session and self._session is not None:
            self._session.close()
            self._session = None

    @staticmethod
    def _orm_to_dataclass(orm: UserProfileORM) -> UserProfile:
        """Convert a UserProfileORM to a UserProfile dataclass."""
        return UserProfile(
            name=orm.name,
            role=orm.role,
            expertise_level=orm.expertise_level,
            communication_style=orm.communication_style,
            preferred_format=orm.preferred_format,
            domains=orm.domains or [],
            custom_rules=orm.custom_rules or {},
        )
