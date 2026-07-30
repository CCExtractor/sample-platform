"""
ApiToken model: server-side storage for scoped API tokens.

Tokens are opaque strings prefixed with 'spci_'. Only the SHA-256 hash
is persisted; the plaintext is returned exactly once at creation time.
A fast hash with a constant-time compare is sufficient here because the
tokens are 256-bit random secrets — a slow password KDF (argon2/bcrypt)
buys nothing against brute force on high-entropy values.
"""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import relationship, validates

from database import Base


class Scope:
    """The scopes a token can carry.

    Reference these constants instead of writing the strings inline, so a
    rename stays a single edit. Plain strings rather than a DeclEnum
    because scopes cross the wire: they arrive in request bodies, are
    stored as a JSON array, and are compared against what the client sent.
    """

    RUNS_READ = 'runs:read'
    RUNS_WRITE = 'runs:write'
    RESULTS_READ = 'results:read'
    BASELINES_WRITE = 'baselines:write'
    SYSTEM_READ = 'system:read'
    # Kept apart from system:read so a monitoring token can watch the
    # platform without being able to reconfigure it.
    SYSTEM_WRITE = 'system:write'
    TOKENS_MANAGE = 'tokens:manage'


VALID_SCOPES = frozenset([
    Scope.RUNS_READ,
    Scope.RUNS_WRITE,
    Scope.RESULTS_READ,
    Scope.BASELINES_WRITE,
    Scope.SYSTEM_READ,
    Scope.SYSTEM_WRITE,
    Scope.TOKENS_MANAGE,
])

DEFAULT_SCOPES = [Scope.RUNS_READ, Scope.RESULTS_READ]

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

    @validates('scopes_json')
    def validate_scopes_json(self, key, value):
        """Ensure scopes_json only contains known scopes."""
        try:
            scopes = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError("scopes_json must be a valid JSON string")

        if not isinstance(scopes, list):
            raise ValueError("scopes_json must be a JSON array")

        for scope in scopes:
            if scope not in VALID_SCOPES:
                raise ValueError(f"Unknown scope: {scope}")
        return value

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
        """Hash a token securely using SHA-256."""
        return hashlib.sha256(plaintext.encode('utf-8')).hexdigest()

    @staticmethod
    def verify_token(plaintext: str, token_hash: str) -> bool:
        """Verify a token against its SHA-256 hash using constant-time comparison."""
        if not plaintext or not token_hash:
            return False
        expected_hash = ApiToken.hash_token(plaintext)
        return hmac.compare_digest(expected_hash, token_hash)

    @staticmethod
    def extract_prefix(token: str) -> str:
        """Return the first 16 chars used for DB lookup."""
        return token[:16] if len(token) >= 16 else token
