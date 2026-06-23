"""Cloudflare R2（S3 相容）物件儲存。"""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.cloudflare_config import r2_enabled


class R2Error(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"].strip(),
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def _bucket() -> str:
    return os.environ["R2_BUCKET_NAME"].strip()


async def put_object(key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
    if not r2_enabled():
        raise R2Error("R2 未設定")
    client = _s3_client()
    await asyncio.to_thread(
        client.put_object,
        Bucket=_bucket(),
        Key=key,
        Body=body,
        ContentType=content_type,
    )


async def get_object(key: str) -> bytes | None:
    if not r2_enabled():
        raise R2Error("R2 未設定")
    client = _s3_client()

    def _read() -> bytes | None:
        try:
            response = client.get_object(Bucket=_bucket(), Key=key)
            return response["Body"].read()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404", "NotFound"}:
                return None
            raise

    return await asyncio.to_thread(_read)


async def object_exists(key: str) -> bool:
    data = await get_object(key)
    return data is not None
