from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "fetch_latest.py"
SPEC = importlib.util.spec_from_file_location("fetch_latest", MODULE_PATH)
fetch_latest = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(fetch_latest)


def test_run_writes_json_for_enabled_sources(tmp_path):
    config = tmp_path / "sources.yaml"
    config.write_text(
        """
sources:
  - platform: xhs
    name: alice
    mock_data:
      items:
        - id: 1
  - platform: douyin
    name: bob
    enabled: false
    mock_data:
      items:
        - id: 2
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    code = fetch_latest.run(config, tmp_path / "data")

    assert code == 0
    target = tmp_path / "data" / "xhs_alice.json"
    assert target.is_file()
    assert (tmp_path / "data" / "douyin_bob.json").exists() is False


def test_run_skips_unknown_platform(tmp_path):
    config = tmp_path / "sources.yaml"
    config.write_text(
        """
sources:
  - platform: unknown
    name: no-op
    mock_data: {}
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    code = fetch_latest.run(config, tmp_path / "data")

    assert code == 0
    assert list((tmp_path / "data").glob("*.json")) == []
