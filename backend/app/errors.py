"""エラー応答の形式を統一する。

成功時は素のボディ（配列・オブジェクト）を返し、**エラー時だけ**形を揃える。
全応答を `{data, error, meta}` でラップする案は採らない。FastAPIの標準から外れ、
フロントの全呼び出しを書き換える割に得るものが小さいため。判断の記録は
docs/ROADMAP_TODO.md の Phase 1E「unified error response の扱い」を参照。

    {
      "error": {
        "status": 404,
        "code": "not_found",
        "message": "Theme not found",
        "details": [...]        // 入力検証エラーのときだけ
      }
    }
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# FastAPIの HTTPException は Starlette のサブクラス。ベースクラス側を登録しないと、
# ルート未一致の404やメソッド不一致の405など Starlette 自身が投げる例外を拾えない。
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# starlette 0.4x で定数名が HTTP_422_UNPROCESSABLE_CONTENT へ変わったため、
# 存在する方を使う。
_HTTP_422 = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", None) or status.HTTP_422_UNPROCESSABLE_ENTITY

# HTTPステータスから機械可読なコードを決める。クライアントは message ではなく
# code で分岐できる。未知のステータスは汎用コードへ落とす。
_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    _HTTP_422: "validation_error",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}


def error_code(status_code: int) -> str:
    """ステータスに対応するエラーコードを返す。"""
    if status_code in _STATUS_CODES:
        return _STATUS_CODES[status_code]
    return "client_error" if status_code < 500 else "server_error"


def error_body(
    status_code: int, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """統一形式のエラーボディを組み立てる。"""
    error: dict[str, Any] = {
        "status": status_code,
        "code": error_code(status_code),
        "message": message,
    }
    if details:
        error["details"] = details
    return {"error": error}


def _message_from_detail(detail: Any) -> str:
    """HTTPExceptionのdetailを表示用の文字列にする。

    detailには文字列のほか、辞書を入れている箇所もある（readiness応答など）。
    """
    if isinstance(detail, str):
        return detail
    return str(detail)


async def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.status_code, _message_from_detail(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """入力検証エラー。どの項目が不正かを details に残す。"""
    details = [
        {
            "location": list(error.get("loc", [])),
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=_HTTP_422,
        content=error_body(_HTTP_422, "リクエストの内容が不正です", details),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """想定外の例外。内部の詳細は返さず、ログにだけ残す。"""
    logger.exception("未処理の例外: %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "サーバー内部でエラーが発生しました"
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    """アプリへエラーハンドラを登録する。"""
    # サブクラス（fastapi.HTTPException）もこの登録で拾われる。
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
