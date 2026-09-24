"""
アプリケーション設定
pydantic-settings で .env を読み込む
"""
from pathlib import Path

from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    database_url: str = "postgresql://invest:invest@localhost:5432/invest"
    # SQLiteからの一度限りの移行元。通常のAPI・ETLは参照しない。
    legacy_sqlite_path: str = "data/invest.db"
    # 公開APIではPostgreSQLセッションとHTTP変更操作を読み取り専用にする。
    database_read_only: bool = False
    backfill_years: int = 5
    cors_origins: list[str] = ["http://localhost:3000"]
    jquants_api_key: str | None = None
    # 識別子の有無だけで日次の取得元を切り替えない。プランの提供期間を確認した上で明示的に有効化する。
    jquants_daily_enabled: bool = False
    jquants_base_url: str = "https://api.jquants.com/v2"
    jquants_timeout_seconds: float = 30.0
    # プランごとのレート制限（回/分）。Free=5 / Light=60 / Standard=120 / Premium=500
    jquants_requests_per_minute: int = 5
    # プランが提供しない直近日数と、遡れる年数。Freeは12週間(84日)前まで・2年分
    jquants_history_lag_days: int = 84
    jquants_history_years: int = 2
    raw_data_path: str = "data/raw"
    # GitHub Actions等でrawを永続化するGCS prefix。ローカル開発では未設定でよい。
    raw_data_uri: str | None = None
    management_api_enabled: bool = False
    management_api_key: str | None = None

    # .env はカレントディレクトリではなくプロジェクトルート基準で探す。
    # 実行場所（リポジトリルート / backend / CI）によって読めたり読めなかったりするのを避ける。
    # 後に指定したファイルが優先されるため、backend/.env がルートの .env を上書きする。
    model_config = {
        "env_file": (_PROJECT_ROOT / ".env", _PROJECT_ROOT / "backend" / ".env"),
        "env_file_encoding": "utf-8",
        # 廃止済みの設定が既存の .env に残っていても無視する。
        "extra": "ignore",
    }

    @property
    def legacy_db_path(self) -> Path:
        """移行元SQLiteの絶対パスを返す。"""
        p = Path(self.legacy_sqlite_path)
        if p.is_absolute():
            return p
        # .env の相対パスはプロジェクトルート基準
        return Path(__file__).parent.parent.parent / p

    @property
    def db_path(self) -> Path:
        """旧SQLite migration専用の互換alias。新規コードでは使わない。"""
        return self.legacy_db_path

    @property
    def daily_update_script(self) -> Path:
        return Path(__file__).parent.parent / "scripts" / "daily_update.py"

    @property
    def jquants_sync_script(self) -> Path:
        return Path(__file__).parent.parent / "scripts" / "jquants_sync.py"

    @property
    def raw_data_dir(self) -> Path:
        p = Path(self.raw_data_path)
        if p.is_absolute():
            return p
        return Path(__file__).parent.parent.parent / p


settings = Settings()
