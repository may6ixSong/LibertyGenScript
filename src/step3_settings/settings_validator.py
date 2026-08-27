"""
settings_validator.py

Step 3 Constants(output_prefix / DFF Cell Name / LUT Table / Worst case primitive
liberty) + Pin 설정(및 각 pin에 연계된 하위 필드)에 대한 유효성 검사와, Step 2로 옮겨진
Voltage Map(사용자 정의 voltage condition x Power Type)에 대한 유효성 검사
(validate_voltage_map - Step 2 Validate에서 호출). GUI에 의존하지 않는 순수 함수로 작성.

2026-08 수정: 이전에는 Pin 설정만 검사 대상이었으나, 다음 값들이 비어 있으면 이후
단계(liberty 파일명/voltage_map/block3 lu_table_template/block4 cell·pg_pin/block5
timing·internal_power)를 만들 수 없으므로 이제 Validate 단계에서 함께 걸러낸다:
  - output_prefix (출력 파일명에 쓰임)
  - DFF Cell Name / LUT Table (block3의 lu_table_template index_1/index_2를
    PDK/DK 파일에서 찾아오는 데 쓰임)
  - Worst case primitive liberty (그 lu_table_template을 어느 PDK에서 가져올지 -
    Step2의 liberty setting들이 고른 PDK 파일 중 하나여야 함)
  - class / process_prefix (block4의 cell 속성에 쓰임 - {process_prefix}_class 등)
  - Pin 설정의 모든 하위 필드 (switch_function/pg_function, rise·fall power/when,
    timing_sense/timing_type, 인식된 DBS output pin마다의 related pin)

DBS output pin의 related pin 검사(2026-08 확정 → 2026-08 자동 채움 도입으로 수정):
  1. "Check DBS Output Pins"로 인식해 둔 pin 집합이 지금 Port List로 다시 펼친 결과와
     동일해야 한다 (Port List 파일이 바뀌면 인식 결과가 달라지므로, 다르면 다시 Check).
  2. 각 related pin은 비어 있으면 안 되고,
  3. Port List에 실제로 존재하는 Pin name이어야 한다.

  (변경 이력) 예전에는 여기에 "그 DBS output pin이 있는 Port List 행의 'Related Pin'
  컬럼 값과 정확히 일치해야 한다"는 4번째 규칙이 있었다. 이제 "Check DBS Output Pins"를
  누르면 각 pin의 Related Pin이 Port List의 'Related Pin' 컬럼 값으로 **자동
  채워지고**(settings_view._fill_related_pin_table), 사용자가 표에서 직접 다른 pin으로
  고쳐 쓸 수도 있는 것이 의도된 동작이므로(Port List와 다른 pin을 쓰고 싶은 경우), 그
  자동 채움 값을 그대로 다시 강제하는 이 규칙은 삭제했다 - 이제는 자동 채움이 곧 기본값
  일치를 보장하고, 사용자가 의도적으로 바꾼 값은 "Port List에 실제 존재하는 pin"이기만
  하면 통과한다.
"""

from __future__ import annotations

import fnmatch

from step1_setup.port_list_reader import list_all_pin_names, list_pins_by_port_type
from step3_settings.constants_field_defs import (
    CONDITION_NAME_KEY, CONDITION_VALUES_KEY, VOLTAGE_CONDITIONS_KEY, condition_value_key,
    power_type_count_of, power_type_label, voltage_map_name_key,
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


def validate_constants(scalars: dict, paired_pdk_files: list[str] | None = None) -> list[str]:
    """
    class / process_prefix / output_prefix / DFF Cell Name / LUT Table(비어있으면 출력
    파일명 또는 block3를 만들 수 없음)과 Worst case primitive liberty(lu_table_template과
    block5 max_capacitance를 가져올 PDK)가 채워져 있는지 검사.

    Voltage Map은 화면이 Step 2로 옮겨졌으므로 여기서 검사하지 않는다
    (validate_voltage_map 참고).

    Args:
        paired_pdk_files: Step2의 liberty setting들이 고른 PDK 파일명 목록.
            None이면 "Step2 목록과 대조"는 건너뛰고 비어있는지만 검사한다.
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
            f"{_WORST_CASE_PDK_LABEL} '{worst_case_pdk}' is not one of the PDK files "
            "selected by the Step 2 liberty settings. Select it again."
        )

    return errors


def validate_voltage_map(voltage_map: dict) -> list[str]:
    """
    Voltage Map 검사 (2026-08: 화면이 Step 2 왼쪽 열로 옮겨져 Step 2 Validate에서 호출됨).

      - voltage condition이 최소 1개는 있어야 하고,
      - condition 이름이 비어 있으면 안 되며 서로 중복되어도 안 된다
        (Step 2의 liberty setting이 이름으로 condition을 고르기 때문. 대소문자만 다른
        이름도 같은 이름으로 본다),
      - 각 condition의 Power Type1..N(현재 Power Type 개수만큼) 값이 전부 채워진
        숫자여야 하고,
      - 그 개수만큼의 Power Type voltage name이 전부 채워져 있어야 한다.
    """
    errors: list[str] = []

    power_type_count = power_type_count_of(voltage_map)
    conditions = voltage_map.get(VOLTAGE_CONDITIONS_KEY) or []
    if not conditions:
        errors.append(
            "No voltage condition has been added to the Voltage Map. Add at least one "
            "(each liberty setting selects one of them)."
        )
        return errors

    seen_names: dict[str, int] = {}
    for index, condition in enumerate(conditions):
        name = str(condition.get(CONDITION_NAME_KEY, "")).strip()
        label = f"Voltage condition #{index + 1}"
        if not name:
            errors.append(f"{label} has no name.")
        else:
            label = f"Voltage condition '{name}'"
            first_index = seen_names.setdefault(name.lower(), index)
            if first_index != index:
                errors.append(
                    f"{label} has the same name as voltage condition #{first_index + 1}. "
                    "Voltage condition names must be unique."
                )

        values = condition.get(CONDITION_VALUES_KEY) or {}
        for type_index in range(1, power_type_count + 1):
            value = str(values.get(condition_value_key(type_index), "")).strip()
            value_label = f"{label} {power_type_label(type_index)}"
            if not value:
                errors.append(f"{value_label} is empty.")
                continue
            try:
                float(value)
            except ValueError:
                errors.append(f"{value_label} is not a valid number: {value!r}")

    names = voltage_map.get("names", {}) or {}
    for type_index in range(1, power_type_count + 1):
        value = str(names.get(voltage_map_name_key(type_index), "")).strip()
        if not value:
            errors.append(f"Voltage Map {power_type_label(type_index)} voltage name is empty.")

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

    for pin_name in recognized:
        value = str(related_map.get(pin_name, "")).strip()
        if not value:
            errors.append(f"Related Pin for DBS output pin '{pin_name}' is empty.")
            continue
        if value not in all_pin_names:
            errors.append(
                f"Related Pin '{value}' (for DBS output pin '{pin_name}') is not a pin in the Port List."
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
