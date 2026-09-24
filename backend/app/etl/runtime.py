from pathlib import Path

from app.config import settings
from app.database import Connection
from app.etl.fetchers.jquants import JQuantsClient
from app.etl.pipeline import JQuantsMarketPipeline


def build_jquants_pipeline(conn: Connection) -> JQuantsMarketPipeline:
    if not settings.jquants_api_key:
        raise RuntimeError("JQUANTS_API_KEY is not configured")
    client = JQuantsClient(
        settings.jquants_api_key,
        base_url=settings.jquants_base_url,
        timeout=settings.jquants_timeout_seconds,
        requests_per_minute=settings.jquants_requests_per_minute,
    )
    project_root = Path(__file__).parents[3]
    return JQuantsMarketPipeline(conn, client, settings.raw_data_dir, project_root)
