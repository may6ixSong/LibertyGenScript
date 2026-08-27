"""
udc_manager.py

Step 2 상태(공통 필드 + liberty 1개당 setting 목록) 저장/로드
(2026-08 전면 재설계 -> 2026-08 2차 재설계).
- 외부 의존성 없음 (표준 라이브러리만 사용)
- 저장 위치: config/udc_settings.json (config_manager.py 와 같은 config 폴더 사용)

1차 재설계에서는 파일명 자동 페어링 결과를 화면을 열 때마다 다시 계산하고 PDK 파일명을
key로 한 Voltage Condition 선택값만 저장했다. 2차 재설계에서는 사용자가 liberty 1개당
setting(corner/beol inform/voltage/temperature/condition/PDK file/DBS file)을 직접
만들기 때문에, 그 목록 자체를 `liberty_settings` 배열로 저장한다.

저장된 PDK/DBS 파일명이 폴더에서 사라졌더라도 로드 자체는 실패하지 않는다 - 파일 존재
여부는 Step2 Validate에서 검사한다.
"""

from __future__ import annotations

import json

from step1_setup.config_manager import CONFIG_DIR
from step2_udc.udc_field_defs import (
    ENTRY_ID_KEY, all_common_field_keys, new_entry,
)

UDC_SETTINGS_FILE = CONFIG_DIR / "udc_settings.json"

LIBERTY_SETTINGS_KEY = "liberty_settings"


def _default_common() -> dict:
    return {key: "" for key in all_common_field_keys()}


def default_state() -> dict:
    return {"common": _default_common(), LIBERTY_SETTINGS_KEY: []}


def _normalize_entry(raw) -> dict | None:
    """저장된 entry 하나를 현재 필드 정의에 맞춰 보정. dict가 아니면 버린다."""
    if not isinstance(raw, dict):
        return None
    entry = new_entry()
    for key in entry:
        if key in raw and raw[key] is not None:
            entry[key] = str(raw[key])
    if not entry.get(ENTRY_ID_KEY):
        entry[ENTRY_ID_KEY] = new_entry()[ENTRY_ID_KEY]
    return entry


def load_state() -> dict:
    """저장된 Step2 상태를 로드. 필드가 추가/변경돼도 기본값과 병합해서 안전하게 반환."""
    if UDC_SETTINGS_FILE.exists():
        try:
            with open(UDC_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            common = {**_default_common(), **data.get("common", {})}
            raw_entries = data.get(LIBERTY_SETTINGS_KEY, [])
            if not isinstance(raw_entries, list):
                raw_entries = []
            entries = [e for e in (_normalize_entry(raw) for raw in raw_entries) if e is not None]
            return {"common": common, LIBERTY_SETTINGS_KEY: entries}
        except (json.JSONDecodeError, OSError) as e:
            print(f"[Warning] Failed to read UDC settings file, starting with defaults: {e}")
    return default_state()


def save_state(state: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(UDC_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_entries(state: dict) -> list[dict]:
    entries = state.get(LIBERTY_SETTINGS_KEY, [])
    return entries if isinstance(entries, list) else []
