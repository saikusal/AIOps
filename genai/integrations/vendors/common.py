import datetime
import json
from typing import Any, Dict, Optional

import requests


def credential_secret(integration) -> str:
    credential = getattr(integration, "credential", None)
    return str(getattr(credential, "secret_ref", "") or "")


def credential_metadata(integration) -> Dict[str, Any]:
    credential = getattr(integration, "credential", None)
    metadata = getattr(credential, "credential_metadata", None) or {}
    return metadata if isinstance(metadata, dict) else {}


def integration_metadata(integration) -> Dict[str, Any]:
    metadata = getattr(integration, "metadata_json", None) or {}
    return metadata if isinstance(metadata, dict) else {}


def auth_headers(integration, *, bearer: bool = True, api_key_header: Optional[str] = None) -> Dict[str, str]:
    secret = credential_secret(integration)
    metadata = credential_metadata(integration)
    if api_key_header and secret:
        return {api_key_header: secret}
    if bearer and secret:
        return {"Authorization": f"Bearer {secret}"}
    if metadata.get("username") and secret:
        return {}
    return {}


def request_json_lines(response: requests.Response):
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def parse_timestamp(value: Any) -> datetime.datetime:
    if not value:
        return datetime.datetime.now(datetime.timezone.utc)
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            value = value / 1000
        return datetime.datetime.fromtimestamp(float(value), tz=datetime.timezone.utc)
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.datetime.now(datetime.timezone.utc)
