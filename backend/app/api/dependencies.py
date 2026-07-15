from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.contracts import UserRead, UserRole, UserStatus
from app.services.auth_service import AuthenticationError, auth_service


bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "请先登录。") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserRead:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        user_id, token_version = auth_service.decode_access_token_details(credentials.credentials)
    except AuthenticationError as exc:
        raise _unauthorized(str(exc)) from exc

    user = auth_service.get_user_by_id(db, user_id)
    if user is None:
        raise _unauthorized("用户不存在，请重新登录。")
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已被禁用。")
    try:
        token_is_current = auth_service.is_token_version_current(db, user_id, token_version)
    except AuthenticationError as exc:
        raise _unauthorized(str(exc)) from exc
    if not token_is_current:
        raise _unauthorized("登录状态已失效，请重新登录。")
    return user


def require_admin(current_user: UserRead = Depends(get_current_user)) -> UserRead:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限。")
    return current_user
