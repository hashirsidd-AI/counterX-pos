"""User management and authentication. Permissions enforced here."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models
from ..config import ROLE_PERMISSIONS, ROLES
from ..security import hash_password, verify_password
from ..sync.service import enqueue_obj


class AuthenticationError(Exception):
    pass


class PermissionDenied(Exception):
    pass


class AuthService:
    def __init__(self, session: Session):
        self.s = session

    # -- users ---------------------------------------------------------------
    def create_user(self, username: str, password: str, full_name: str = "",
                    role: str = "cashier", actor: models.User | None = None) -> models.User:
        if role not in ROLES:
            raise ValueError(f"Unknown role: {role}")
        if actor is not None:
            self.require(actor, "users")
        if self.s.query(models.User).filter_by(username=username.strip()).first():
            raise ValueError("Username already exists")
        if len(password) < 4:
            raise ValueError("Password must be at least 4 characters")
        salt, phash = hash_password(password)
        user = models.User(username=username.strip(), password_hash=phash,
                           password_salt=salt, full_name=full_name, role=role)
        self.s.add(user)
        self.s.flush()
        self._audit(actor, "user.create", "users", user.id, f"username={username} role={role}")
        enqueue_obj(self.s, "users", user)  # redacted serializer: no credentials
        return user

    def authenticate(self, username: str, password: str) -> models.User:
        user = self.s.query(models.User).filter_by(username=username.strip()).first()
        if not user or not user.is_active:
            raise AuthenticationError("Invalid username or password")
        if not verify_password(password, user.password_salt, user.password_hash):
            raise AuthenticationError("Invalid username or password")
        self._audit(user, "auth.login", "users", user.id, "")
        return user

    def change_password(self, user: models.User, new_password: str,
                        actor: models.User | None = None) -> None:
        if actor is not None and actor.id != user.id:
            self.require(actor, "users")
        if len(new_password) < 4:
            raise ValueError("Password must be at least 4 characters")
        salt, phash = hash_password(new_password)
        user.password_salt, user.password_hash = salt, phash
        self._audit(actor or user, "user.password_change", "users", user.id, "")

    def set_active(self, user: models.User, active: bool, actor: models.User) -> None:
        self.require(actor, "users")
        user.is_active = active
        self._audit(actor, "user.set_active", "users", user.id, f"active={active}")

    def list_users(self) -> list[models.User]:
        return self.s.query(models.User).order_by(models.User.username).all()

    # -- administrator recovery ---------------------------------------------------
    # If the owner forgets their password, they can recover with a one-time
    # recovery code that was shown ONLY during first-time setup. Only the
    # code's SHA-256 hash is stored — never the code itself.
    _RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    def set_recovery_code(self, owner: models.User) -> str:
        """Generate, store (hashed) and return a new recovery code."""
        import hashlib as _hashlib
        import secrets as _secrets

        self.require(owner, "users")
        parts = ["".join(_secrets.choice(self._RECOVERY_ALPHABET)
                         for _ in range(4)) for _ in range(3)]
        code = "CXRC-" + "-".join(parts)
        digest = _hashlib.sha256(code.encode()).hexdigest()
        row = self.s.query(models.Setting).filter_by(
            key="recovery_code_hash").first()
        if row is None:
            row = models.Setting(key="recovery_code_hash", value=digest)
            self.s.add(row)
        else:
            row.value = digest
        self.s.flush()
        self._audit(owner, "user.recovery_code_set", "users", owner.id, "")
        return code

    def verify_recovery_code(self, code: str) -> bool:
        import hashlib as _hashlib
        import hmac as _hmac

        row = self.s.query(models.Setting).filter_by(
            key="recovery_code_hash").first()
        if not row or not row.value:
            return False
        digest = _hashlib.sha256(code.strip().upper().encode()).hexdigest()
        return _hmac.compare_digest(digest, row.value)

    def recover_owner_password(self, code: str, new_password: str) -> models.User:
        """Reset the (oldest active) owner account using a valid recovery code."""
        if not self.verify_recovery_code(code):
            raise AuthenticationError("Invalid recovery code")
        if len(new_password) < 4:
            raise ValueError("Password must be at least 4 characters")
        owner = (self.s.query(models.User)
                 .filter_by(role="owner", is_active=True)
                 .order_by(models.User.id).first())
        if not owner:
            raise AuthenticationError("No active owner account found")
        salt, phash = hash_password(new_password)
        owner.password_salt, owner.password_hash = salt, phash
        self._audit(None, "user.owner_recovered", "users", owner.id, "")
        self.s.flush()
        return owner

    # -- permissions ----------------------------------------------------------
    def permissions_of(self, user: models.User) -> set[str]:
        perms = set(ROLE_PERMISSIONS.get(user.role, ()))
        for ov in self.s.query(models.UserPermissionOverride).filter_by(user_id=user.id):
            if ov.granted:
                perms.add(ov.permission)
            else:
                perms.discard(ov.permission)
        return perms

    def has_permission(self, user: models.User, permission: str) -> bool:
        return permission in self.permissions_of(user)

    def require(self, user: models.User | None, permission: str) -> None:
        if user is None or not self.has_permission(user, permission):
            raise PermissionDenied(f"Permission required: {permission}")

    def set_override(self, user: models.User, permission: str,
                     granted: bool, actor: models.User) -> None:
        self.require(actor, "users")
        ov = self.s.query(models.UserPermissionOverride).filter_by(
            user_id=user.id, permission=permission).first()
        if ov is None:
            ov = models.UserPermissionOverride(user_id=user.id, permission=permission,
                                               granted=granted)
            self.s.add(ov)
        else:
            ov.granted = granted
        self._audit(actor, "user.permission_override", "users", user.id,
                    f"{permission}={'grant' if granted else 'revoke'}")

    # -- helpers ---------------------------------------------------------------
    def _audit(self, user: models.User | None, action: str, entity: str,
               entity_id: int | None, details: str) -> None:
        self.s.add(models.AuditLog(user_id=user.id if user else None, action=action,
                                   entity=entity, entity_id=entity_id, details=details))
