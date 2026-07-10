from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.contracts import LoginRequest, UserCreate, UserRead


class AuthenticationError(ValueError):
    pass


class DisabledUserError(ValueError):
    pass


class RegistrationConflictError(ValueError):
    pass


class AuthService:
    def __init__(self) -> None:
        # PBKDF2-SHA256 avoids storing plaintext passwords and supports long Unicode passwords.
        self.password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

    def register(self, db: Session, payload: UserCreate) -> UserRead:
        conflict = db.execute(
            text(
                """
                SELECT username, email
                FROM users
                WHERE username = :username OR email = :email
                LIMIT 1
                """
            ),
            {"username": payload.username, "email": payload.email},
        ).mappings().first()
        if conflict is not None:
            if conflict["username"].lower() == payload.username.lower():
                raise RegistrationConflictError("用户名已被使用。")
            raise RegistrationConflictError("邮箱已被注册。")

        try:
            result = db.execute(
                text(
                    """
                    INSERT INTO users (username, password_hash, email, role, status)
                    VALUES (:username, :password_hash, :email, 'user', 'active')
                    """
                ),
                {
                    "username": payload.username,
                    "password_hash": self.hash_password(payload.password),
                    "email": payload.email,
                },
            )
            user_id = int(result.lastrowid)
            db.execute(
                text(
                    """
                    INSERT INTO knowledge_bases (owner_id, name, description, visibility)
                    VALUES (:owner_id, :name, :description, 'private')
                    """
                ),
                {
                    "owner_id": user_id,
                    "name": "默认知识库",
                    "description": "注册时创建的默认私人知识库。",
                },
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise RegistrationConflictError("用户名或邮箱已被使用。") from exc

        user = self.get_user_by_id(db, user_id)
        if user is None:
            raise RuntimeError("注册成功后无法读取用户信息")
        return user

    def authenticate(self, db: Session, payload: LoginRequest) -> UserRead:
        row = db.execute(
            text(
                """
                SELECT id, username, email, password_hash, role, status
                FROM users
                WHERE username = :identity OR email = :identity
                LIMIT 1
                """
            ),
            {"identity": payload.username},
        ).mappings().first()

        if row is None or not self.verify_password(payload.password, row["password_hash"]):
            raise AuthenticationError("用户名、邮箱或密码错误。")
        if row["status"] != "active":
            raise DisabledUserError("用户已被禁用。")
        return self._to_user_read(row)

    def get_user_by_id(self, db: Session, user_id: int) -> UserRead | None:
        row = db.execute(
            text(
                """
                SELECT id, username, email, role, status
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        ).mappings().first()
        return self._to_user_read(row) if row is not None else None

    def create_access_token(self, user: UserRead) -> str:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value,
            "iat": now,
            "exp": expires_at,
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def decode_access_token(self, token: str) -> int:
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            subject = payload.get("sub")
            user_id = int(subject)
        except (JWTError, TypeError, ValueError) as exc:
            raise AuthenticationError("登录状态无效或已过期，请重新登录。") from exc
        if user_id <= 0:
            raise AuthenticationError("登录状态无效或已过期，请重新登录。")
        return user_id

    def hash_password(self, password: str) -> str:
        return self.password_context.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return self.password_context.verify(password, password_hash)
        except (TypeError, ValueError):
            return False

    def _to_user_read(self, row) -> UserRead:
        return UserRead(
            id=int(row["id"]),
            username=row["username"],
            email=row["email"],
            role=row["role"],
            status=row["status"],
        )


auth_service = AuthService()
