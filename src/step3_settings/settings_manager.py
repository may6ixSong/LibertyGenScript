"""
settings_manager.py

Step 3 Constants + Pin 설정 저장/로드 + Voltage Map 저장/로드.
- 저장 위치: config/step3_settings.json (step1_setup.config_manager 와 같은 config 폴더)

2026-08: Voltage Map 화면은 Step 2(왼쪽 열)로 옮겨졌지만, **저장 위치는 그대로**
step3_settings.json의 `voltage_map` key다 - 기존에 저장해 둔 config를 그대로 이어서
쓸 수 있게 하기 위해서다. Step 2 화면은 load_voltage_map()/save_voltage_map()으로
이 부분만 읽고 쓴다(다른 Step3 값은 건드리지 않는다).

Voltage Map 구조 (2026-08 사용자 정의 condition 재설계 → 2026-08 Power Type 개수 무제한
+ voltage(digital) 필드 추가):
    {"power_type_count": 3,
     "conditions": [{"id": ..., "name": "BST", "values": {"type1": "0.8", ...}}, ...],
     "names": {"power_type1_name": ..., ...},
     "digital_voltages": {"power_type1_digital_voltage": "0.8", ...}}

예전 config는 conditions 대신 `values: {"bst_type1": ..., "tiv_type3": ...}` 형태로
BST/WST/TIV 세 그룹이 고정되어 있었다. 그런 config를 읽으면 그 값 그대로 BST/WST/TIV
세 condition을 만들어 준다(_migrate_legacy_conditions). `digital_voltages` 필드가 아예
없는 config(2026-08 이전)를 읽을 때는 Power Type1/2/3에 한해 예전 고정 매칭값
(0.8/2.2/1.8)을 그대로 seed해서, 사용자가 새 필드를 손대지 않아도 기존과 같은 생성
결과가 나오게 한다.
"""

from __future__ import annotations

import json

from step1_setup.config_manager import CONFIG_DIR
from step3_settings.constants_field_defs import (
    CONDITION_ID_KEY, CONDITION_NAME_KEY, CONDITION_VALUES_KEY, LEGACY_POWER_TYPE_SEED_VOLTAGE,
    LEGACY_VOLTAGE_MAP_GROUPS, LEGACY_VOLTAGE_MAP_VALUES_KEY, POWER_TYPE_COUNT_DEFAULT,
    POWER_TYPE_COUNT_KEY, POWER_TYPE_COUNT_MIN, SCALAR_CONSTANT_DEFS, VOLTAGE_CONDITIONS_KEY,
    condition_value_key, default_conditions, legacy_voltage_map_value_key, new_condition,
    voltage_map_digital_voltage_key, voltage_map_name_key,
)
from step3_settings.pin_field_defs import (
    DBS_BIT_SPLIT_KEY, DBS_OUTPUT_KEY, DBS_RELATED_PINS_KEY, DBS_TIMING_SENSE_DEFAULT,
    DBS_TIMING_SENSE_KEY, DBS_TIMING_TYPE_DEFAULT, DBS_TIMING_TYPE_KEY, ENABLE_SIGNAL_KEY,
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
    config가 아예 없을 때의 Voltage Map: 기본 condition 3개(BST/WST/TIV) x Power Type
    대표값(0.8V/2.2V/1.8V). voltage name은 기본값이 없으므로 빈 문자열로 시작하고,
    voltage(digital)은 예전 고정 매칭값으로 seed된다(2026-08 추가).
    """
    names = {voltage_map_name_key(i): "" for i in LEGACY_POWER_TYPE_SEED_VOLTAGE}
    digital_voltages = {
        voltage_map_digital_voltage_key(i): str(v)
        for i, v in LEGACY_POWER_TYPE_SEED_VOLTAGE.items()
    }
    return {
        POWER_TYPE_COUNT_KEY: POWER_TYPE_COUNT_DEFAULT,
        VOLTAGE_CONDITIONS_KEY: default_conditions(),
        "names": names,
        "digital_voltages": digital_voltages,
    }


def _normalize_condition(raw, fallback_name: str = "") -> dict | None:
    """저장된 condition 하나를 현재 구조에 맞춰 보정. dict가 아니면 버린다."""
    if not isinstance(raw, dict):
        return None
    raw_values = raw.get(CONDITION_VALUES_KEY)
    values = raw_values if isinstance(raw_values, dict) else {}
    condition = new_condition(
        str(raw.get(CONDITION_NAME_KEY, fallback_name) or fallback_name), values,
    )
    saved_id = str(raw.get(CONDITION_ID_KEY, "") or "").strip()
    if saved_id:
        condition[CONDITION_ID_KEY] = saved_id
    return condition


# 아주 예전(2026-08 사용자 정의 condition 재설계 이전) config는 BST/WST/TIV 세
# 그룹 x Power Type1~3으로 고정되어 있었다 - Power Type 개수 무제한 재설계와
# 무관한, 이 마이그레이션 전용 상수다.
_LEGACY_POWER_TYPE_COUNT = 3


def _migrate_legacy_conditions(saved: dict) -> list[dict]:
    """
    2026-08 이전 config(`values: {"bst_type1": ...}`)를 condition 목록으로 옮긴다.
    값이 하나도 없으면 빈 목록을 반환해서 호출자가 기본값을 쓰게 한다.
    """
    legacy_values = saved.get(LEGACY_VOLTAGE_MAP_VALUES_KEY)
    if not isinstance(legacy_values, dict) or not legacy_values:
        return []

    conditions = []
    for group in LEGACY_VOLTAGE_MAP_GROUPS:
        values = {}
        for type_index in range(1, _LEGACY_POWER_TYPE_COUNT + 1):
            value = legacy_values.get(legacy_voltage_map_value_key(group, type_index))
            if value is not None and str(value).strip():
                values[condition_value_key(type_index)] = str(value).strip()
        conditions.append(new_condition(group, values))
    return conditions


def _merge_voltage_map(saved: dict | None) -> dict:
    defaults = _default_voltage_map()
    saved = saved if isinstance(saved, dict) else {}

    try:
        count = int(saved.get(POWER_TYPE_COUNT_KEY, defaults[POWER_TYPE_COUNT_KEY]))
    except (TypeError, ValueError):
        count = defaults[POWER_TYPE_COUNT_KEY]
    count = max(POWER_TYPE_COUNT_MIN, count)

    raw_conditions = saved.get(VOLTAGE_CONDITIONS_KEY)
    conditions: list[dict] = []
    if isinstance(raw_conditions, list):
        conditions = [c for c in (_normalize_condition(raw) for raw in raw_conditions) if c]
    if not conditions:
        conditions = _migrate_legacy_conditions(saved)
    if not conditions:
        conditions = defaults[VOLTAGE_CONDITIONS_KEY]

    saved_names = saved.get("names")
    names = {**defaults["names"], **(saved_names if isinstance(saved_names, dict) else {})}

    # 2026-08 추가: voltage(digital) 필드가 없는 예전 config는 defaults(Power Type1~3
    # 예전 고정값)로 채워진다 - 사용자가 이 필드를 아예 본 적이 없어도 매칭 결과가
    # 그대로 유지되도록.
    saved_digital = saved.get("digital_voltages")
    digital_voltages = {
        **defaults["digital_voltages"],
        **(saved_digital if isinstance(saved_digital, dict) else {}),
    }

    return {
        POWER_TYPE_COUNT_KEY: count,
        VOLTAGE_CONDITIONS_KEY: conditions,
        "names": names,
        "digital_voltages": digital_voltages,
    }


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
        DBS_BIT_SPLIT_KEY: {},
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
            # dbs_related_pins/dbs_output_bit_split는 dict여야 함 - 예전 포맷/손상된
            # 파일이면 기본값으로 되돌림
            if not isinstance(merged_pins.get(DBS_RELATED_PINS_KEY), dict):
                merged_pins[DBS_RELATED_PINS_KEY] = {}
            if not isinstance(merged_pins.get(DBS_BIT_SPLIT_KEY), dict):
                merged_pins[DBS_BIT_SPLIT_KEY] = {}
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


# ---------------------------------------------------------------------------
# Voltage Map 전용 접근자 (화면은 Step 2에 있지만 저장 위치는 여기 그대로)
# ---------------------------------------------------------------------------
def load_voltage_map() -> dict:
    return load_settings()["voltage_map"]


def save_voltage_map(voltage_map: dict) -> None:
    """
    저장 파일의 voltage_map 부분만 갈아끼운다. Step 2에서 Voltage Map을 고쳐도
    Step 3에서 입력한 다른 값(scalars/pins/output_path)이 날아가지 않도록, 항상
    파일을 먼저 읽어서 병합한 뒤 저장한다.
    """
    settings = load_settings()
    settings["voltage_map"] = _merge_voltage_map(voltage_map)
    save_settings(settings)
