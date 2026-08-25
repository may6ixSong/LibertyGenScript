"""
settings_validator.py

Step 3 Constants(output_prefix / Voltage Map / DFF Cell Name / LUT Table /
Worst case primitive liberty) + Pin 설정(및 각 pin에 연계된 하위 필드)에 대한 유효성
검사. GUI에 의존하지 않는 순수 함수로 작성.

2026-08 수정: 이전에는 Pin 설정만 검사 대상이었으나, 다음 값들이 비어 있으면 이후
단계(liberty 파일명/voltage_map/block3 lu_table_template/block4 cell·pg_pin/block5
timing·internal_power)를 만들 수 없으므로 이제 Validate 단계에서 함께 걸러낸다:
  - output_prefix (출력 파일명에 쓰임)
  - Voltage Map (BST/WST/TIV x Power Type1..N 값 + Power Type별 voltage name,
    voltage_map에 쓰임 - power type 개수만큼만 검사)
  - DFF Cell Name / LUT Table (block3의 lu_table_template index_1/index_2를
    PDK/DK 파일에서 찾아오는 데 쓰임)
  - Worst case primitive liberty (그 lu_table_template을 어느 PDK에서 가져올지 -
    Step2에서 pair가 성립한 PDK 파일 중 하나여야 함)
  - class / process_prefix (block4의 cell 속성에 쓰임 - {process_prefix}_class 등)
  - Pin 설정의 모든 하위 필드 (switch_function/pg_function, rise·fall power/when,
    timing_sense/timing_type, 인식된 DBS output pin마다의 related pin)

DBS output pin의 related pin 검사(2026-08 확정):
  1. "Check DBS Output Pins"로 인식해 둔 pin 집합이 지금 Port List로 다시 펼친 결과와
     동일해야 한다 (Port List 파일이 바뀌면 인식 결과가 달라지므로, 다르면 다시 Check).
  2. 각 related pin은 비어 있으면 안 되고,
  3. Port List에 실제로 존재하는 Pin name이어야 하며,
  4. 그 DBS output pin이 있는 Port List 행의 'Related Pin' 컬럼 값과 정확히 일치해야
     한다 (예: 입력이 'A'인데 Port List의 값이 'AA'면 에러).
"""

from __future__ import annotations

import fnmatch

from step1_setup.port_list_reader import (
    list_all_pin_names, list_pins_by_port_type, list_port_pins_detailed,
)
from step3_settings.constants_field_defs import (
    POWER_TYPE_COUNT_DEFAULT, POWER_TYPE_COUNT_KEY, VOLTAGE_MAP_GROUPS, power_type_label,
    voltage_map_name_key, voltage_map_value_key,
)
from step3_settings.pin_field_defs import (
    DBS_OUTPUT_KEY, DBS_RELATED_PINS_KEY, DBS_TIMING_SENSE_KEY, DBS_TIMING_TYPE_KEY,
    ENABLE_SIGNAL_KEY, ENABLE_SIGNAL_PORT_TYPE, POWER_DOWN_FALL_POWER_KEY, POWER_DOWN_KEY,
    POWER_DOWN_RISE_POWER_KEY, POWER_DOWN_WHEN_KEY, VIRTUAL_POWER_KEY,
    VIRTUAL_POWER_PG_FUNCTION_KEY, VIRTUAL_POWER_PORT_TYPE, VIRTUAL_POWER_SWITCH_FUNCTION_KEY,
    expand_dbs_output_pins, split_pattern_and_range,
)

_REQUIRED_TEXT_SCALARS = [
    ("class", "class"),
    ("process_prefix", "process_prefix"),
    ("output_prefix", "output_prefix"),
    ("dff_cell_name", "DFF Cell Name"),
    ("primitive_cell_name", "LUT Table"),
]

_WORST_CASE_PDK_KEY = "worst_case_pdk"
_WORST_CASE_PDK_LABEL = "Worst case primitive liberty"

# 비어 있으면 안 되는 pin 하위 필드 (key, 화면 라벨, 와일드카드 허용 여부)
_REQUIRED_PIN_TEXT_FIELDS = [
    (ENABLE_SIGNAL_KEY, "Enable Signal for power gate", True),
    (VIRTUAL_POWER_SWITCH_FUNCTION_KEY, "Virtual Power Switch Function", False),
    (VIRTUAL_POWER_PG_FUNCTION_KEY, "Virtual Power PG Function", False),
    (POWER_DOWN_KEY, "Power down control signal", True),
    (POWER_DOWN_WHEN_KEY, "Power down control signal - when", False),
    (DBS_OUTPUT_KEY, "DBS output pin", True),
    (DBS_TIMING_SENSE_KEY, "DBS output pin - timing_sense", False),
    (DBS_TIMING_TYPE_KEY, "DBS output pin - timing_type", False),
]

# 비어 있으면 안 되고 숫자로도 읽혀야 하는 pin 하위 필드
_REQUIRED_PIN_NUMBER_FIELDS = [
    (POWER_DOWN_RISE_POWER_KEY, "Power down control signal - rise power"),
    (POWER_DOWN_FALL_POWER_KEY, "Power down control signal - fall power"),
]


def validate_constants(
    scalars: dict, voltage_map: dict, paired_pdk_files: list[str] | None = None,
) -> list[str]:
    """
    output_prefix / DFF Cell Name / LUT Table(비어있으면 출력 파일명 또는 block3를
    만들 수 없음), Worst case primitive liberty(lu_table_template을 가져올 PDK),
    Voltage Map(BST/WST/TIV x Power Type1..N 값 + Power Type별 voltage name, 현재
    power type 개수만큼만 - 비어있으면 voltage_map 값을 채울 수 없음)이 전부 채워져
    있는지 검사.

    Args:
        paired_pdk_files: Step2에서 DBS output과 1:1 pair가 성립한 PDK 파일명 목록.
            None이면 "pair 목록과 대조"는 건너뛰고 비어있는지만 검사한다.
    """
    errors: list[str] = []

    for key, label in _REQUIRED_TEXT_SCALARS:
        value = str(scalars.get(key, "")).strip()
        if not value:
            errors.append(f"{label} is empty.")

    worst_case_pdk = str(scalars.get(_WORST_CASE_PDK_KEY, "")).strip()
    if not worst_case_pdk:
        errors.append(f"{_WORST_CASE_PDK_LABEL} is not selected.")
    elif paired_pdk_files is not None and worst_case_pdk not in paired_pdk_files:
        errors.append(
            f"{_WORST_CASE_PDK_LABEL} '{worst_case_pdk}' is not one of the PDK files that "
            "currently form a 1:1 pair in Step 2. Select it again."
        )

    try:
        power_type_count = int(voltage_map.get(POWER_TYPE_COUNT_KEY, POWER_TYPE_COUNT_DEFAULT))
    except (TypeError, ValueError):
        power_type_count = POWER_TYPE_COUNT_DEFAULT
    values = voltage_map.get("values", {}) or {}
    names = voltage_map.get("names", {}) or {}

    for group in VOLTAGE_MAP_GROUPS:
        for type_index in range(1, power_type_count + 1):
            key = voltage_map_value_key(group, type_index)
            label = f"Voltage Map {group} {power_type_label(type_index)}"
            value = str(values.get(key, "")).strip()
            if not value:
                errors.append(f"{label} is empty.")
                continue
            try:
                float(value)
            except ValueError:
                errors.append(f"{label} is not a valid number: {value!r}")

    for type_index in range(1, power_type_count + 1):
        key = voltage_map_name_key(type_index)
        label = f"Voltage Map {power_type_label(type_index)} voltage name"
        value = str(names.get(key, "")).strip()
        if not value:
            errors.append(f"{label} is empty.")

    return errors


def _validate_dbs_related_pins(pins: dict, port_list_file: str) -> list[str]:
    """
    "Check DBS Output Pins"로 인식해 둔 DBS output pin마다의 related pin 검사.
    (자세한 규칙은 이 모듈 docstring 참고)
    """
    errors: list[str] = []

    related_map = pins.get(DBS_RELATED_PINS_KEY)
    if not isinstance(related_map, dict):
        related_map = {}

    recognized = expand_dbs_output_pins(port_list_file, pins.get(DBS_OUTPUT_KEY, ""))
    if not recognized:
        errors.append(
            "DBS output pin pattern matched no PORT pins. Run 'Check DBS Output Pins' "
            "again after fixing the pattern or the Port List."
        )
        return errors

    if set(related_map) != set(recognized):
        errors.append(
            "The DBS output pins recognized from the current Port List differ from the "
            "checked list (%d checked / %d recognized now). Run 'Check DBS Output Pins' again."
            % (len(related_map), len(recognized))
        )
        return errors

    all_pin_names = set(list_all_pin_names(port_list_file))
    port_list_related = {
        pin["pin_name"]: (pin.get("related_pin") or "").strip()
        for pin in list_port_pins_detailed(port_list_file)
    }

    for pin_name in recognized:
        value = str(related_map.get(pin_name, "")).strip()
        if not value:
            errors.append(f"Related Pin for DBS output pin '{pin_name}' is empty.")
            continue
        if value not in all_pin_names:
            errors.append(
                f"Related Pin '{value}' (for DBS output pin '{pin_name}') is not a pin in the Port List."
            )
            continue
        expected = port_list_related.get(pin_name, "")
        if value != expected:
            errors.append(
                f"Related Pin '{value}' (for DBS output pin '{pin_name}') does not match the "
                f"Port List 'Related Pin' column value {expected!r}."
            )

    return errors


def validate_pin_settings(pins: dict, port_list_file: str) -> list[str]:
    errors: list[str] = []

    virtual_power = str(pins.get(VIRTUAL_POWER_KEY, "")).strip()
    if not virtual_power:
        errors.append("Virtual Power is not selected.")

    for key, label, allows_wildcard in _REQUIRED_PIN_TEXT_FIELDS:
        value = str(pins.get(key, "")).strip()
        if not value:
            errors.append(f"{label} is empty.")
        elif not allows_wildcard and "*" in value:
            errors.append(f"{label} does not allow a wildcard (*): {value!r}")

    for key, label in _REQUIRED_PIN_NUMBER_FIELDS:
        value = str(pins.get(key, "")).strip()
        if not value:
            errors.append(f"{label} is empty.")
            continue
        try:
            float(value)
        except ValueError:
            errors.append(f"{label} is not a valid number: {value!r}")

    if errors:
        # 비어있는 값이 있으면 port list 대조가 의미 없으므로 여기서 마무리
        return errors

    pwr_pins = list_pins_by_port_type(port_list_file, VIRTUAL_POWER_PORT_TYPE)
    if virtual_power not in pwr_pins:
        errors.append(f"Virtual Power '{virtual_power}' was not found among PWR pins.")

    port_pins = list_pins_by_port_type(port_list_file, ENABLE_SIGNAL_PORT_TYPE)
    enable_signal = str(pins.get(ENABLE_SIGNAL_KEY, "")).strip()
    enable_pattern, _ = split_pattern_and_range(enable_signal)
    if not any(fnmatch.fnmatchcase(p, enable_pattern) for p in port_pins):
        errors.append(f"Enable signal pattern '{enable_signal}' matched no PORT pins.")

    all_pins = list_all_pin_names(port_list_file)
    power_down = str(pins.get(POWER_DOWN_KEY, "")).strip()
    power_down_pattern, _ = split_pattern_and_range(power_down)
    if not any(fnmatch.fnmatchcase(p, power_down_pattern) for p in all_pins):
        errors.append(f"Power down control signal pattern '{power_down}' matched no pins.")

    errors += _validate_dbs_related_pins(pins, port_list_file)

    return errors
