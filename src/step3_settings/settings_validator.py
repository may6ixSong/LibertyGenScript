"""
settings_validator.py

Step 3 Constants(output_prefix / Voltage Condition / DFF·Primitive Cell Name) + Pin
설정에 대한 유효성 검사.
GUI에 의존하지 않는 순수 함수로 작성.

2026-08 수정: 이전에는 Pin 설정만 검사 대상이었으나, 다음 값들이 비어 있으면 이후
단계(liberty 파일명/voltage_map/block3 lu_table_template/block4 cell·pg_pin)를 만들
수 없으므로 이제 Validate 단계에서 함께 걸러낸다:
  - output_prefix (출력 파일명에 쓰임)
  - Voltage Condition 9칸 (BST/WST/TIV x High/Mid/Low, voltage_map에 쓰임)
  - DFF Cell Name / Primitive Cell Name (block3의 lu_table_template index_1/index_2를
    PDK/DK 파일에서 찾아오는 데 쓰임)
  - class / process_prefix (block4의 cell 속성에 쓰임 - {process_prefix}_class 등)
"""

from __future__ import annotations

import fnmatch

from step1_setup.port_list_reader import list_all_pin_names, list_pins_by_port_type
from step3_settings.constants_field_defs import VOLTAGE_CONDITION_FIELD_DEFS
from step3_settings.pin_field_defs import (
    DBS_OUTPUT_KEY, ENABLE_SIGNAL_KEY, ENABLE_SIGNAL_PORT_TYPE, POWER_DOWN_KEY,
    VIRTUAL_POWER_KEY, VIRTUAL_POWER_PORT_TYPE, split_pattern_and_range,
)

_REQUIRED_TEXT_SCALARS = [
    ("class", "class"),
    ("process_prefix", "process_prefix"),
    ("output_prefix", "output_prefix"),
    ("dff_cell_name", "DFF Cell Name"),
    ("primitive_cell_name", "Primitive Cell Name"),
]


def validate_constants(scalars: dict, voltage_condition: dict) -> list[str]:
    """
    output_prefix / DFF Cell Name / Primitive Cell Name(비어있으면 출력 파일명 또는
    block3를 만들 수 없음)과 Voltage Condition 9칸(비어있으면 voltage_map 값을 채울
    수 없음)이 전부 채워져 있는지 검사.
    """
    errors: list[str] = []

    for key, label in _REQUIRED_TEXT_SCALARS:
        value = str(scalars.get(key, "")).strip()
        if not value:
            errors.append(f"{label} is empty.")

    for key, label in VOLTAGE_CONDITION_FIELD_DEFS:
        value = str(voltage_condition.get(key, "")).strip()
        if not value:
            errors.append(f"Voltage Condition '{label}' is empty.")
            continue
        try:
            float(value)
        except ValueError:
            errors.append(f"Voltage Condition '{label}' is not a valid number: {value!r}")

    return errors


def validate_pin_settings(pins: dict, port_list_file: str) -> list[str]:
    errors: list[str] = []

    virtual_power = pins.get(VIRTUAL_POWER_KEY, "").strip()
    enable_signal = pins.get(ENABLE_SIGNAL_KEY, "").strip()
    power_down = pins.get(POWER_DOWN_KEY, "").strip()
    dbs_output = pins.get(DBS_OUTPUT_KEY, "").strip()

    if not virtual_power:
        errors.append("Virtual Power is not selected.")
    if not enable_signal:
        errors.append("Enable signal for power gate is empty.")
    if not power_down:
        errors.append("Power down control signal is empty.")
    if not dbs_output:
        errors.append("DBS output signal is empty.")

    if errors:
        # 비어있는 값은 port list 대조가 의미 없으므로 여기서 마무리
        return errors

    pwr_pins = list_pins_by_port_type(port_list_file, VIRTUAL_POWER_PORT_TYPE)
    if virtual_power not in pwr_pins:
        errors.append(f"Virtual Power '{virtual_power}' was not found among PWR pins.")

    port_pins = list_pins_by_port_type(port_list_file, ENABLE_SIGNAL_PORT_TYPE)
    enable_pattern, _ = split_pattern_and_range(enable_signal)
    if not any(fnmatch.fnmatchcase(p, enable_pattern) for p in port_pins):
        errors.append(f"Enable signal pattern '{enable_signal}' matched no PORT pins.")

    all_pins = list_all_pin_names(port_list_file)

    power_down_pattern, _ = split_pattern_and_range(power_down)
    if not any(fnmatch.fnmatchcase(p, power_down_pattern) for p in all_pins):
        errors.append(f"Power down control signal pattern '{power_down}' matched no pins.")

    dbs_pattern, _ = split_pattern_and_range(dbs_output)
    if not any(fnmatch.fnmatchcase(p, dbs_pattern) for p in all_pins):
        errors.append(f"DBS output signal pattern '{dbs_output}' matched no pins.")

    return errors
