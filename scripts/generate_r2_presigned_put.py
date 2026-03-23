#!/usr/bin/env python3
"""Generate a presigned PUT URL for Cloudflare R2 / S3-compatible storage."""

from __future__ import annotations

import argparse
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict
from urllib.parse import quote, urlencode, urlparse


def sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def encode_uri_path(bucket: str, key: str) -> str:
    parts = [bucket, *[part for part in key.split("/") if part]]
    return "/" + "/".join(quote(part, safe="-_.~") for part in parts)


def build_presigned_url(
    *,
    endpoint: str,
    bucket: str,
    key: str,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    expires: int,
) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError(f"Invalid endpoint: {endpoint!r}")

    host = parsed.netloc
    canonical_uri = encode_uri_path(bucket, key)
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"

    query_params: Dict[str, str] = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key_id}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_query = urlencode(sorted(query_params.items()))
    canonical_headers = f"host:{host}\n"
    canonical_request = "\n".join(
        [
            "PUT",
            canonical_uri,
            canonical_query,
            canonical_headers,
            "host",
            "UNSIGNED-PAYLOAD",
        ]
    )
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    k_date = sign(("AWS4" + secret_access_key).encode("utf-8"), date_stamp)
    k_region = sign(k_date, region)
    k_service = sign(k_region, "s3")
    k_signing = sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    final_query = canonical_query + f"&X-Amz-Signature={signature}"
    return f"{parsed.scheme}://{host}{canonical_uri}?{final_query}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="S3-compatible endpoint, e.g. https://<account>.r2.cloudflarestorage.com")
    parser.add_argument("--bucket", required=True, help="Bucket name")
    parser.add_argument("--key", required=True, help="Object key, e.g. state/live-state.json")
    parser.add_argument("--access-key-id", required=True, help="Access key id")
    parser.add_argument("--secret-access-key", required=True, help="Secret access key")
    parser.add_argument("--region", default="auto", help="Signing region; R2 uses auto")
    parser.add_argument("--expires", type=int, default=604800, help="Expiry in seconds, max 604800 for S3-compatible presign")
    args = parser.parse_args()

    expires = max(1, min(args.expires, 604800))
    print(
        build_presigned_url(
            endpoint=args.endpoint,
            bucket=args.bucket,
            key=args.key,
            access_key_id=args.access_key_id,
            secret_access_key=args.secret_access_key,
            region=args.region,
            expires=expires,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
