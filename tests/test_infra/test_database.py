import pytest

pytest.importorskip("sqlalchemy")


def test_database_url_format():
    from infra.config import settings
    url = settings.database_url
    assert url.startswith("postgresql+asyncpg://")
    assert "novel2drama" in url


def test_database_engine_created():
    from infra.database import _get_engine
    engine = _get_engine()
    assert engine is not None
