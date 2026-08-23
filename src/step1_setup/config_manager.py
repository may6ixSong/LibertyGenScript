"""
config_manager.py

입력 경로(PDK/DBS 폴더, Port List 파일) 저장/로드.
- 외부 의존성 없음 (표준 라이브러리만 사용)
- 저장 위치: 이 프로젝트 폴더 내부(config/user_config.json), 소스 실행/빌드된 exe 실행
  모두에서 동일하게 동작 (runtime_paths.get_app_root() 기준)
"""

from __future__ import annotations

import json

from step1_setup.field_defs import INPUT_PATH_FIELDS
from runtime_paths import get_app_root

CONFIG_DIR = get_app_root() / "config"
CONFIG_FILE = CONFIG_DIR / "user_config.json"


def _default_config() -> dict:
    return {key: "" for key, _, _, _ in INPUT_PATH_FIELDS}


def load_config() -> dict:
    """config 파일이 있으면 로드, 없거나 손상된 경우 기본값(빈 문자열) 반환."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**_default_config(), **data}
        except (json.JSONDecodeError, OSError) as e:
            print(f"[Warning] Failed to read config file, starting with defaults: {e}")
    return _default_config()


def save_config(data: dict) -> None:
    """입력 경로 값을 JSON 파일로 저장."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)