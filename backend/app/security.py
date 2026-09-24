"""管理APIのアプリケーション層認証。"""

from secrets import compare_digest

from fastapi import Header, HTTPException, Request, status

from app.config import settings

ADMIN_KEY_HEADER = "X-Admin-Key"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def verify_management_key(candidate: str | None) -> None:
    """管理機能の有効化と共有キーをfail closedで検証する。"""
    if not settings.management_api_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not settings.management_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Management API is not configured",
        )
    if candidate is None or not compare_digest(
        candidate.encode("utf-8"),
        settings.management_api_key.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid management API key",
        )


def require_management_access(
    x_admin_key: str | None = Header(default=None),
) -> None:
    """管理専用Routerから利用するFastAPI dependency。"""
    verify_management_key(x_admin_key)


def management_key_from_request(request: Request) -> str | None:
    return request.headers.get(ADMIN_KEY_HEADER)
