"""
udc_manager.py

Step 2 상태(공통 필드 + pair별 Voltage Condition 선택값) 저장/로드 (2026-08 전면
재설계).
- 외부 의존성 없음 (표준 라이브러리만 사용)
- 저장 위치: config/udc_settings.json (config_manager.py 와 같은 config 폴더 사용)

pair 자체(1:1 매칭 결과)는 저장하지 않는다 - PDK/DBS 폴더 내용이 바뀔 수 있으므로
화면을 열 때마다 udc_field_defs.compute_pairs()로 항상 다시 계산한다. 저장하는 것은
PDK 파일명을 key로 한 Voltage Condition(bst/wst/tiv) 선택값뿐이며, 폴더 내용이 바뀌어
해당 파일명이 더 이상 유효한 pair를 이루지 못하게 되어도 안전하게 무시된다.
"""

from __future__ import annotations

import json

from step1_setup.config_manager import CONFIG_DIR
from step2_udc.udc_field_defs import all_common_field_keys

UDC_SETTINGS_FILE = CONFIG_DIR / "udc_settings.json"


def _default_common() -> dict:
    return {key: "" for key in all_common_field_keys()}


def default_state() -> dict:
    return {"common": _default_common(), "pair_settings": {}}


def load_state() -> dict:
    """저장된 Step2 상태를 로드. 필드가 추가/변경돼도 기본값과 병합해서 안전하게 반환."""
    if UDC_SETTINGS_FILE.exists():
        try:
            with open(UDC_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            common = {**_default_common(), **data.get("common", {})}
            pair_settings = data.get("pair_settings", {})
            if not isinstance(pair_settings, dict):
                pair_settings = {}
            return {"common": common, "pair_settings": pair_settings}
        except (json.JSONDecodeError, OSError) as e:
            print(f"[Warning] Failed to read UDC settings file, starting with defaults: {e}")
    return default_state()


def save_state(state: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(UDC_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_voltage_condition(pair_settings: dict, pdk_file: str) -> str:
    return pair_settings.get(pdk_file, {}).get("voltage_condition", "")


def set_voltage_condition(pair_settings: dict, pdk_file: str, value: str) -> None:
    pair_settings.setdefault(pdk_file, {})["voltage_condition"] = value
