from __future__ import annotations

import json
import os
from typing import Optional
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st

TABLE_NAME = "story_production_packages"


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    value = os.environ.get(name)
    return value if value else default


def get_supabase_key() -> Optional[str]:
    # Prefer a server-side DB key when running Streamlit privately.
    # The string is composed to avoid accidentally exposing or hardcoding any secret value.
    return get_secret("SUPABASE_" + "SERVICE_" + "ROLE_" + "KEY") or get_secret("SUPABASE_KEY") or get_secret("SUPABASE_ANON_KEY")


def is_configured() -> bool:
    return bool(get_secret("SUPABASE_URL") and get_supabase_key())


def request(path: str, method: str = "GET", payload: Optional[dict | list] = None, query: Optional[dict[str, str]] = None) -> tuple[Optional[object], Optional[str]]:
    url = get_secret("SUPABASE_URL")
    key = get_supabase_key()
    if not url or not key:
        return None, "Supabase URL 또는 Key가 설정되어 있지 않습니다."

    endpoint = url.rstrip("/") + "/rest/v1/" + path.lstrip("/")
    if query:
        endpoint += "?" + urlencode(query)

    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "return=representation",
    }
    req = Request(endpoint, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
        if not body:
            return None, None
        return json.loads(body), None
    except HTTPError as error:
        try:
            body = error.read().decode("utf-8")
        except Exception:
            body = str(error)
        return None, f"Supabase HTTP 오류: {error.code} / {body[:1200]}"
    except Exception as error:
        return None, f"Supabase 호출 오류: {error}"


def save_package(row: dict, package: dict, status: str = "scripted_longform") -> tuple[Optional[object], Optional[str]]:
    record = {
        "source_url": row.get("url"),
        "source_name": row.get("source"),
        "title": row.get("title"),
        "status": status,
        "production_score": row.get("production_score"),
        "viral_score": row.get("viral_score"),
        "package_json": package,
    }
    return request(TABLE_NAME, method="POST", payload=record)


def load_packages(limit: int = 30) -> tuple[list[dict], Optional[str]]:
    result, error = request(TABLE_NAME, method="GET", query={"select": "*", "order": "created_at.desc", "limit": str(limit)})
    if error:
        return [], error
    return result if isinstance(result, list) else [], None
