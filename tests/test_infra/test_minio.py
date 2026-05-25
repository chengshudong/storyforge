import pytest

pytest.importorskip("minio")


def test_minio_endpoint_format():
    from infra.config import settings
    endpoint = settings.minio_endpoint
    assert ":" in endpoint


def test_minio_client_created():
    from infra.minio import get_minio
    client = get_minio()
    assert client is not None
