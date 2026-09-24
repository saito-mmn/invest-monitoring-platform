from app import server


def test_server_uses_cloud_run_port(monkeypatch) -> None:
    called_with: dict[str, object] = {}

    def fake_run(app: str, *, host: str, port: int) -> None:
        called_with.update(app=app, host=host, port=port)

    monkeypatch.setenv("PORT", "9090")
    monkeypatch.setattr(server.uvicorn, "run", fake_run)

    server.main()

    assert called_with == {"app": "app.main:app", "host": "0.0.0.0", "port": 9090}
