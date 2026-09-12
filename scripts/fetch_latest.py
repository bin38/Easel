#!/usr/bin/env python3
"""Fetch latest social-media data for configured sources."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "sources.yaml"
DEFAULT_DATA_DIR = ROOT / "data"
API_KEYS = {
    "xhs": "XHS_API_KEY",
    "douyin": "DOUYIN_API_KEY",
    "zhihu": "ZHIHU_API_KEY",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return cleaned.strip("-") or "source"


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(marker in key_text for marker in ("token", "secret", "password", "api_key", "apikey")):
                out[key] = "***"
            else:
                out[key] = _redact_sensitive(item)
        return out
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _load_config(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover - environment/setup failure
        raise RuntimeError("PyYAML is required to read config/sources.yaml") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("config/sources.yaml must contain a top-level mapping")
    return data


def _iter_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sources = config.get("sources")
    if isinstance(sources, list):
        for item in sources:
            if isinstance(item, dict):
                out.append(item)
    for platform in API_KEYS:
        items = config.get(platform)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            merged = dict(item)
            merged.setdefault("platform", platform)
            out.append(merged)
    return out


def _fetch_remote_json(source: dict[str, Any], api_key: str | None) -> Any:
    if "mock_data" in source:
        return source["mock_data"]
    url = source.get("url") or source.get("endpoint")
    if not url:
        raise ValueError("source requires `url` (or `endpoint`) when mock_data is absent")
    headers = {str(k): str(v) for k, v in (source.get("headers") or {}).items()}
    if api_key:
        headers.setdefault("Authorization", "Bearer " + api_key)
    params = source.get("params") or {}
    if isinstance(params, dict) and params:
        query = parse.urlencode({str(k): str(v) for k, v in params.items()})
        sep = "&" if "?" in str(url) else "?"
        url = f"{url}{sep}{query}"
    timeout = int(source.get("timeout", 30))
    req = request.Request(str(url), headers=headers)
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def _write_payload(data_dir: Path, platform: str, source: dict[str, Any], payload: Any) -> Path:
    name = str(source.get("name") or source.get("id") or "source")
    path = data_dir / f"{platform}_{_slug(name)}.json"
    record = {
        "platform": platform,
        "source": name,
        "fetched_at": _utc_now(),
        "data": _redact_sensitive(payload),
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run(config_path: Path, data_dir: Path) -> int:
    if not config_path.is_file():
        print(f"[fetch_latest] config not found: {config_path}", file=sys.stderr)
        return 1
    data_dir.mkdir(parents=True, exist_ok=True)
    config = _load_config(config_path)
    errors = 0
    for source in _iter_sources(config):
        if source.get("enabled", True) is False:
            continue
        platform = str(source.get("platform", "")).strip().lower()
        if platform not in API_KEYS:
            print("[fetch_latest] skip unknown platform")
            continue
        env_name = API_KEYS[platform]
        try:
            payload = _fetch_remote_json(source, os.getenv(env_name))
            output = _write_payload(data_dir, platform, source, payload)
            print(f"[fetch_latest] wrote {output.name}")
        except Exception as exc:  # pragma: no cover - narrow behavior validated in tests
            errors += 1
            print(f"[fetch_latest] {platform} fetch failed", file=sys.stderr)
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch latest social-media content into data/")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config/sources.yaml")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Directory to write JSON files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(Path(args.config), Path(args.data_dir))


if __name__ == "__main__":
    raise SystemExit(main())
