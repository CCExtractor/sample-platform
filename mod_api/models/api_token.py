"""
ApiToken model: server-side storage for scoped API tokens.

Tokens are opaque strings prefixed with 'spci_'. Only the argon2 hash
is persisted; the plaintext is returned exactly once at creation time.
"""

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import List

from argon2 import PasswordHasher
from argon2.exceptions import (InvalidHashError, VerificationError,
                               VerifyMismatchError)
from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import relationship

from database import Base

_ph = PasswordHasher()

VALID_SCOPES = frozenset([
    'runs:read',
    'runs:write',
    'results:read',
    'baselines:write',
    'system:read',
    'tokens:manage',
])

DEFAULT_SCOPES = ['runs:read', 'results:read']

TOKEN_PREFIX = 'spci_'
TOKEN_BYTE_LENGTH = 32


class ApiToken(Base):
    """Scoped API token bound to a user account."""

    __tablename__ = 'api_token'
    __table_args__ = (
        UniqueConstraint('user_id', 'token_name', name='uq_user_token_name'),
        {'mysql_engine': 'InnoDB'},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey('user.id', onupdate='CASCADE', ondelete='CASCADE'),
        nullable=False,
    )
    user = relationship('User', uselist=False)
    token_name = Column(String(50), nullable=False)
    token_hash = Column(String(255), nullable=False)
    token_prefix = Column(String(16), nullable=False, index=True)
    scopes_json = Column(Text(), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    def __init__(
        self,
        user_id: int,
        token_name: str,
        token_hash: str,
        token_prefix: str,
        scopes: List[str],
        expires_in_days: int = 7,
    ) -> None:
        self.user_id = user_id
        self.token_name = token_name
        self.token_hash = token_hash
        self.token_prefix = token_prefix
        self.scopes_json = json.dumps(scopes)
        self.created_at = datetime.now(timezone.utc)
        self.expires_at = self.created_at + timedelta(days=expires_in_days)

    def __repr__(self) -> str:
        """Return a debug representation of the token."""
        return f'<ApiToken {self.id} user={self.user_id}>'

    @property
    def scopes(self) -> List[str]:
        """Parse the JSON scopes column into a list."""
        return json.loads(self.scopes_json)

    @property
    def is_expired(self) -> bool:
        """Check whether this token has passed its expiration time."""
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires is None:
            return True
        # MySQL DATETIME columns don't preserve tzinfo; treat naive as UTC.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return bool(now > expires)

    @property
    def is_revoked(self) -> bool:
        """Check whether this token has been explicitly revoked."""
        return bool(self.revoked_at is not None)

    @property
    def is_valid(self) -> bool:
        """Return True if the token is neither expired nor revoked."""
        return not self.is_expired and not self.is_revoked

    def has_scope(self, scope: str) -> bool:
        """Return True if the token grants the given scope."""
        return scope in self.scopes

    def revoke(self) -> None:
        """Mark this token as revoked with the current timestamp."""
        self.revoked_at = datetime.now(timezone.utc)

    @staticmethod
    def generate_token() -> str:
        """Create a new random token string with the spci_ prefix."""
        random_bytes = secrets.token_urlsafe(TOKEN_BYTE_LENGTH)
        return f'{TOKEN_PREFIX}{random_bytes}'

    @staticmethod
    def hash_token(plaintext: str) -> str:
        """Hash a token with argon2 for storage."""
        return _ph.hash(plaintext)

    @staticmethod
    def verify_token(plaintext: str, token_hash: str) -> bool:
        """Verify a plaintext token against its stored argon2 hash."""
        try:
            return _ph.verify(token_hash, plaintext)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    @staticmethod
    def extract_prefix(token: str) -> str:
        """Return the first 16 chars used for DB lookup."""
        return token[:16] if len(token) >= 16 else token
