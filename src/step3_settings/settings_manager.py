"""
settings_manager.py

Step 3 Constants + Pin 설정 저장/로드 (2026-08 재설계: Constants 스칼라 + Voltage Map
(BST/WST/TIV x Power Type1..N 값 + Power Type별 voltage name + power type 개수) + Pin
설정과 그에 연계된 하위 필드들).
- 저장 위치: config/step3_settings.json (step1_setup.config_manager 와 같은 config 폴더)
"""

from __future__ import annotations

import json

from step1_setup.config_manager import CONFIG_DIR
from step3_settings.constants_field_defs import (
    POWER_TYPE_COUNT_DEFAULT, POWER_TYPE_COUNT_KEY, POWER_TYPE_COUNT_MAX, POWER_TYPE_COUNT_MIN,
    POWER_TYPE_DEFAULT_VOLTAGE, SCALAR_CONSTANT_DEFS, VOLTAGE_MAP_GROUPS, voltage_map_name_key,
    voltage_map_value_key,
)
from step3_settings.pin_field_defs import (
    DBS_OUTPUT_KEY, DBS_RELATED_PINS_KEY, DBS_TIMING_SENSE_DEFAULT, DBS_TIMING_SENSE_KEY,
    DBS_TIMING_TYPE_DEFAULT, DBS_TIMING_TYPE_KEY, ENABLE_SIGNAL_KEY,
    POWER_DOWN_FALL_POWER_DEFAULT, POWER_DOWN_FALL_POWER_KEY, POWER_DOWN_KEY,
    POWER_DOWN_RISE_POWER_DEFAULT, POWER_DOWN_RISE_POWER_KEY, POWER_DOWN_WHEN_DEFAULT,
    POWER_DOWN_WHEN_KEY, VIRTUAL_POWER_KEY, VIRTUAL_POWER_PG_FUNCTION_KEY,
    VIRTUAL_POWER_SWITCH_FUNCTION_KEY,
)

SETTINGS_FILE = CONFIG_DIR / "step3_settings.json"


def _default_scalars() -> dict:
    return {key: str(default) for key, _, _kind, default in SCALAR_CONSTANT_DEFS}


def _default_voltage_map() -> dict:
    """
    2026-08 확정: BST/WST/TIV x Power Type1..3의 전압 값은 Power Type별 대표값
    (0.8V/2.2V/1.8V)으로 미리 채워 둔다(과거 "전부 빈 값으로 시작" 방침에서 변경).
    voltage name은 기본값이 없으므로 빈 문자열로 시작.
    """
    values = {
        voltage_map_value_key(group, i): str(POWER_TYPE_DEFAULT_VOLTAGE[i])
        for group in VOLTAGE_MAP_GROUPS
        for i in POWER_TYPE_DEFAULT_VOLTAGE
    }
    names = {voltage_map_name_key(i): "" for i in POWER_TYPE_DEFAULT_VOLTAGE}
    return {POWER_TYPE_COUNT_KEY: POWER_TYPE_COUNT_DEFAULT, "values": values, "names": names}


def _merge_voltage_map(saved: dict | None) -> dict:
    defaults = _default_voltage_map()
    saved = saved or {}

    try:
        count = int(saved.get(POWER_TYPE_COUNT_KEY, defaults[POWER_TYPE_COUNT_KEY]))
    except (TypeError, ValueError):
        count = defaults[POWER_TYPE_COUNT_KEY]
    count = max(POWER_TYPE_COUNT_MIN, min(POWER_TYPE_COUNT_MAX, count))

    saved_values = saved.get("values")
    saved_names = saved.get("names")
    values = {**defaults["values"], **(saved_values if isinstance(saved_values, dict) else {})}
    names = {**defaults["names"], **(saved_names if isinstance(saved_names, dict) else {})}

    return {POWER_TYPE_COUNT_KEY: count, "values": values, "names": names}


def _default_pins() -> dict:
    """
    2026-08 추가: 상위 pin 입력에 연계되는 하위 필드들. rise/fall power, when,
    timing_sense, timing_type의 기본값은 예전에 block5_writer.py에 하드코딩되어 있던
    값을 그대로 초기값으로 쓴다 (pin_field_defs의 *_DEFAULT 상수).

    dbs_related_pins는 "Check DBS Output Pins"로 인식된 pin 이름을 key로 하는 dict
    ({pin name: related pin})이며, Port List가 바뀌면 key 집합도 달라진다.
    """
    return {
        VIRTUAL_POWER_KEY: "",
        ENABLE_SIGNAL_KEY: "",
        VIRTUAL_POWER_SWITCH_FUNCTION_KEY: "",
        VIRTUAL_POWER_PG_FUNCTION_KEY: "",
        POWER_DOWN_KEY: "",
        POWER_DOWN_RISE_POWER_KEY: POWER_DOWN_RISE_POWER_DEFAULT,
        POWER_DOWN_FALL_POWER_KEY: POWER_DOWN_FALL_POWER_DEFAULT,
        POWER_DOWN_WHEN_KEY: POWER_DOWN_WHEN_DEFAULT,
        DBS_OUTPUT_KEY: "",
        DBS_TIMING_SENSE_KEY: DBS_TIMING_SENSE_DEFAULT,
        DBS_TIMING_TYPE_KEY: DBS_TIMING_TYPE_DEFAULT,
        DBS_RELATED_PINS_KEY: {},
    }


def default_settings() -> dict:
    return {
        "scalars": _default_scalars(),
        "voltage_map": _default_voltage_map(),
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
            merged_voltage_map = _merge_voltage_map(data.get("voltage_map"))
            merged_pins = {**defaults["pins"], **data.get("pins", {})}
            # dbs_related_pins는 dict여야 함 - 예전 포맷/손상된 파일이면 기본값으로 되돌림
            if not isinstance(merged_pins.get(DBS_RELATED_PINS_KEY), dict):
                merged_pins[DBS_RELATED_PINS_KEY] = {}
            output_path = data.get("output_path", defaults["output_path"])
            return {
                "scalars": merged_scalars,
                "voltage_map": merged_voltage_map,
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
