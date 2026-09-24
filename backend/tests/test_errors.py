"""エラー応答の形式を検証する。

成功時は素のボディ、エラー時のみ `{"error": {...}}` に揃える。
"""

import pytest

from app.errors import error_body, error_code


@pytest.mark.parametrize(
    "status_code, expected",
    [
        (404, "not_found"),
        (422, "validation_error"),
        (405, "method_not_allowed"),
        (418, "client_error"),  # 未知の4xx
        (502, "server_error"),  # 未知の5xx
    ],
)
def test_error_code_is_derived_from_status(status_code, expected):
    """クライアントが message ではなく code で分岐できるようにする。"""
    assert error_code(status_code) == expected


def test_error_body_omits_details_when_absent():
    assert error_body(404, "Theme not found") == {
        "error": {"status": 404, "code": "not_found", "message": "Theme not found"}
    }


def test_not_found_uses_the_unified_shape(client):
    """HTTPExceptionが統一形式で返る。"""
    body = client.get("/api/themes/9999").json()

    assert body == {
        "error": {"status": 404, "code": "not_found", "message": "Theme not found"}
    }


def test_validation_error_reports_the_offending_field(client, db):
    """入力検証エラーは、どの項目が不正かを details に含める。"""
    res = client.get("/api/investment-targets/1/prices?days=0")

    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "validation_error"
    assert any("days" in detail["location"] for detail in error["details"])


def test_success_responses_stay_unwrapped(client):
    """成功時は素のボディのまま。`{data, error, meta}` でラップしない。"""
    body = client.get("/api/themes/summary").json()

    assert isinstance(body, list)


def test_read_only_rejection_uses_the_unified_shape(client, monkeypatch):
    """読み取り専用モードの405も同じ形式で返す。"""
    from app.config import settings

    monkeypatch.setattr(settings, "database_read_only", True)
    body = client.post("/api/themes/", json={}).json()

    assert body["error"]["status"] == 405
    assert body["error"]["code"] == "method_not_allowed"


def test_unknown_path_uses_the_unified_shape(client):
    """ルートに一致しない404も統一形式で返す。

    FastAPIの HTTPException は Starlette のサブクラスなので、サブクラス側だけを
    ハンドラに登録すると、Starlette自身が投げるこの404を拾えない。
    """
    res = client.get("/api/does-not-exist")

    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_method_not_allowed_uses_the_unified_shape(client):
    """ルーティングが拒否する405も統一形式で返す。"""
    res = client.patch("/api/themes/summary")

    assert res.status_code == 405
    assert res.json()["error"]["code"] == "method_not_allowed"
