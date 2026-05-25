from io import BytesIO

from minio import Minio
from minio.error import S3Error

from infra.config import settings

_minio_client: Minio | None = None


def get_minio() -> Minio:
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        _ensure_bucket(_minio_client)
    return _minio_client


def _ensure_bucket(client: Minio) -> None:
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


async def upload_file(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    client = get_minio()
    client.put_object(
        settings.minio_bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_name


async def download_file(object_name: str) -> bytes:
    client = get_minio()
    response = client.get_object(settings.minio_bucket, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


async def check_minio_health() -> bool:
    try:
        client = get_minio()
        client.list_buckets()
        return True
    except Exception:
        return False
