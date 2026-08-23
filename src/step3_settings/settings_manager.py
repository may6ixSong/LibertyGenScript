"""
settings_manager.py

Step 3 Constants + Pin 설정 저장/로드 (2026-08 재설계: 스칼라 3개 + Voltage Condition
단일 행 9칸).
- 저장 위치: config/step3_settings.json (step1_setup.config_manager 와 같은 config 폴더)
"""

from __future__ import annotations

import json

from step1_setup.config_manager import CONFIG_DIR
from step3_settings.constants_field_defs import SCALAR_CONSTANT_DEFS, VOLTAGE_CONDITION_FIELD_DEFS
from step3_settings.pin_field_defs import (
    DBS_OUTPUT_KEY, ENABLE_SIGNAL_KEY, POWER_DOWN_KEY, VIRTUAL_POWER_KEY,
)

SETTINGS_FILE = CONFIG_DIR / "step3_settings.json"


def _default_scalars() -> dict:
    return {key: str(default) for key, _, _kind, default in SCALAR_CONSTANT_DEFS}


def _default_voltage_condition() -> dict:
    # 코드에 기본값을 하드코딩하지 않음(2026-08 확정) - 전부 빈 문자열로 시작
    return {key: "" for key, _label in VOLTAGE_CONDITION_FIELD_DEFS}


def _default_pins() -> dict:
    return {
        VIRTUAL_POWER_KEY: "",
        ENABLE_SIGNAL_KEY: "",
        POWER_DOWN_KEY: "",
        DBS_OUTPUT_KEY: "",
    }


def default_settings() -> dict:
    return {
        "scalars": _default_scalars(),
        "voltage_condition": _default_voltage_condition(),
        "pins": _default_pins(),
        "output_path": "",
    }


def load_settings() -> dict:
    """저장된 설정이 있으면 로드(필드 변경사항과 병합), 없으면 기본값 반환."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            defaults = default_settings()
            merged_scalars = {**defaults["scalars"], **data.get("scalars", {})}
            merged_voltage = {**defaults["voltage_condition"], **data.get("voltage_condition", {})}
            merged_pins = {**defaults["pins"], **data.get("pins", {})}
            output_path = data.get("output_path", defaults["output_path"])
            return {
                "scalars": merged_scalars,
                "voltage_condition": merged_voltage,
                "pins": merged_pins,
                "output_path": output_path,
            }
        except (json.JSONDecodeError, OSError) as e:
            print(f"[Warning] Failed to read Step 3 settings file, starting with defaults: {e}")
    return default_settings()


def save_settings(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
