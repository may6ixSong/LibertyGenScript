"""
liberty_assembler.py

Step2(자동 페어링 + pair별 Voltage Condition(bst/wst/tiv) 선택) + Step3(Constants,
Voltage Map(BST/WST/TIV x Power Type1..N 값 + Power Type별 voltage name + power type
개수), DFF Cell Name/LUT Table/Worst case primitive liberty, Pin Settings와 그 연계
입력들) + Step1(PDK Folder, Port List)을 조합해서, liberty_writter의
write_liberty_file()에 바로 넘길 수 있는 "job"(파일 1개 생성에 필요한 값 전부)을 메모리
상에서 만든다.

.udc/.pdt/pg_pin 같은 중간 파일은 만들지 않는다(2026-08 확정) - PDK 파일 자체는
write_liberty_file()이 직접 스트리밍해서 읽으므로, 이 모듈은 그 외의 값(출력 파일명,
library 이름, nom_voltage/nom_temperature, voltage_map/type_bus/lu_table_template/
cell/pg_pin에 쓸 값 등)만 조립한다.

GUI에 의존하지 않는 순수 함수로 작성.
"""

from __future__ import annotations

from pathlib import Path

from step2_udc.udc_field_defs import VOLTAGE_CONDITION_OPTIONS
from step3_settings.constants_field_defs import (
    POWER_TYPE_COUNT_DEFAULT, POWER_TYPE_COUNT_KEY, POWER_TYPE_DEFAULT_VOLTAGE,
    voltage_map_name_key, voltage_map_value_key,
)
from step3_settings.pin_field_defs import (
    DBS_OUTPUT_KEY, DBS_RELATED_PINS_KEY, DBS_TIMING_SENSE_KEY, DBS_TIMING_TYPE_KEY,
    ENABLE_SIGNAL_KEY, POWER_DOWN_FALL_POWER_KEY, POWER_DOWN_KEY, POWER_DOWN_RISE_POWER_KEY,
    POWER_DOWN_WHEN_KEY, VIRTUAL_POWER_KEY, VIRTUAL_POWER_PG_FUNCTION_KEY,
    VIRTUAL_POWER_SWITCH_FUNCTION_KEY, split_pattern_and_range,
)


def _to_float(value, field_label: str, errors: list[str]) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"'{field_label}' is not a valid number: {value!r}")
        return None


def build_output_filename(output_prefix: str, cell_name: str, dbs_filename: str) -> str:
    """
    출력 파일명 규칙(2026-08 확정):
    {output_prefix}lpv_{cell_name}_{DBS 파일명에서 .mt0 뺀 것}.lib
    """
    dbs_stem = dbs_filename
    if dbs_stem.lower().endswith(".mt0"):
        dbs_stem = dbs_stem[: -len(".mt0")]
    return f"{output_prefix}lpv_{cell_name}_{dbs_stem}.lib"


def build_job(
    pair: dict,
    voltage_condition_value: str,
    common: dict,
    pdk_folder: str,
    dbs_folder: str,
    scalars: dict,
    voltage_map_settings: dict,
    port_bit_values: list[int],
    power_ground_pins: dict,
    pins: dict,
    port_pins: list[dict],
    errors: list[str],
) -> dict | None:
    """
    pair(하나의 PDK/DK <-> DBS output 매칭) + 선택된 Voltage Condition + Port List
    관련 값들로 job dict를 만든다. 실패 시 errors에 메시지를 추가하고 None을 반환한다.
    """
    pdk_filename = pair["pdk_file"]
    dbs_filename = pair["dbs_file"]

    if voltage_condition_value not in VOLTAGE_CONDITION_OPTIONS:
        errors.append(f"[{pdk_filename}] Voltage Condition (bst/wst/tiv) is not selected.")
        return None

    cell_name = str(common.get("cell_name", "")).strip()
    if not cell_name:
        errors.append(f"[{pdk_filename}] Cell Name (Common Fields) is empty.")
        return None

    dff_cell_name = str(scalars.get("dff_cell_name", "")).strip()
    if not dff_cell_name:
        errors.append(f"[{pdk_filename}] DFF Cell Name (Step 3 Constants) is empty.")
        return None

    # primitive_cell_name: 화면 라벨은 "LUT Table" (config key만 예전 이름 유지)
    lut_table_name = str(scalars.get("primitive_cell_name", "")).strip()
    if not lut_table_name:
        errors.append(f"[{pdk_filename}] LUT Table (Step 3 Constants) is empty.")
        return None

    # lu_table_template은 이 pair의 PDK가 아니라 Step3에서 고른 worst case PDK 하나에서만
    # 읽는다 (generate_view가 실행당 한 번 읽어서 모든 job에 같은 결과를 넘겨줌).
    worst_case_pdk_filename = str(scalars.get("worst_case_pdk", "")).strip()
    if not worst_case_pdk_filename:
        errors.append(
            f"[{pdk_filename}] Worst case primitive liberty (Step 3 Constants) is not selected."
        )
        return None

    process_prefix = str(scalars.get("process_prefix", "")).strip()
    if not process_prefix:
        errors.append(f"[{pdk_filename}] process_prefix (Step 3 Constants) is empty.")
        return None

    class_value = str(scalars.get("class", "")).strip()
    if not class_value:
        errors.append(f"[{pdk_filename}] class (Step 3 Constants) is empty.")
        return None

    output_prefix = str(scalars.get("output_prefix", "")).strip()
    output_filename = build_output_filename(output_prefix, cell_name, dbs_filename)
    library_name = (
        output_filename[: -len(".lib")]
        if output_filename.lower().endswith(".lib")
        else output_filename
    )

    group_label = voltage_condition_value.upper()  # bst/wst/tiv -> BST/WST/TIV (VOLTAGE_MAP_GROUPS)

    try:
        power_type_count = int(voltage_map_settings.get(POWER_TYPE_COUNT_KEY, POWER_TYPE_COUNT_DEFAULT))
    except (TypeError, ValueError):
        power_type_count = POWER_TYPE_COUNT_DEFAULT
    voltage_map_values = voltage_map_settings.get("values", {}) or {}
    voltage_map_names = voltage_map_settings.get("names", {}) or {}

    # 이 job(pair)이 선택한 bst/wst/tiv 그룹의 Power Type1..N 값 - block2의 voltage_map
    # 줄마다 (voltage name, value) 하나씩.
    voltage_types: list[dict] = []
    for type_index in range(1, power_type_count + 1):
        value_key = voltage_map_value_key(group_label, type_index)
        name_key = voltage_map_name_key(type_index)
        value = _to_float(
            voltage_map_values.get(value_key, ""), f"{group_label} Power Type{type_index}", errors,
        )
        name = str(voltage_map_names.get(name_key, "")).strip()
        if not name:
            errors.append(
                f"[{pdk_filename}] Power Type{type_index} voltage name (Step 3 Voltage Map) is empty."
            )
        voltage_types.append({"name": name, "value": value})

    # block4가 Port List Volts 값을 Power Type에 매칭시킬 때 쓰는 고정 임계값(대표
    # 전압 0.8V/2.2V/1.8V) -> Power Type voltage name. bst/wst/tiv 구분과 무관하게
    # power type 개수만큼만 포함한다 (2026-08 확정: power type 개수가 2면 1.8V도 매칭
    # 대상에서 제외).
    voltage_name_thresholds = {
        POWER_TYPE_DEFAULT_VOLTAGE[type_index]: str(
            voltage_map_names.get(voltage_map_name_key(type_index), "")
        ).strip()
        for type_index in range(1, power_type_count + 1)
    }

    area = _to_float(common.get("area", ""), "Area (Common Fields)", errors)
    width = _to_float(common.get("width", ""), "Width (Common Fields)", errors)
    height = _to_float(common.get("height", ""), "Height (Common Fields)", errors)

    if errors:
        return None

    pdk_path = str(Path(pdk_folder) / pdk_filename)
    dbs_path = str(Path(dbs_folder) / dbs_filename)

    enable_signal_pattern, _ = split_pattern_and_range(pins.get(ENABLE_SIGNAL_KEY, ""))
    power_down_pattern, _ = split_pattern_and_range(pins.get(POWER_DOWN_KEY, ""))
    dbs_output_pattern, _ = split_pattern_and_range(pins.get(DBS_OUTPUT_KEY, ""))

    dbs_related_pins = pins.get(DBS_RELATED_PINS_KEY)
    if not isinstance(dbs_related_pins, dict):
        dbs_related_pins = {}

    return {
        "pdk_path": pdk_path,
        "pdk_filename": pdk_filename,
        "dbs_filename": dbs_filename,
        "dbs_path": dbs_path,
        "output_filename": output_filename,
        "library_name": library_name,
        "nom_voltage": pair["voltage"],
        "nom_temperature": pair["temperature"],
        "voltage_types": voltage_types,
        "voltage_name_thresholds": voltage_name_thresholds,
        "cell_name": cell_name,
        "dff_cell_name": dff_cell_name,
        "lut_table_name": lut_table_name,
        "worst_case_pdk_filename": worst_case_pdk_filename,
        "bits": list(port_bit_values),
        "process_prefix": process_prefix,
        "class_value": class_value,
        "area": area,
        "width": width,
        "height": height,
        "pwr_pins": power_ground_pins.get("pwr_pins", []),
        "gnd_pins": power_ground_pins.get("gnd_pins", []),
        "virtual_power_pin": pins.get(VIRTUAL_POWER_KEY, ""),
        "virtual_power_switch_function": pins.get(VIRTUAL_POWER_SWITCH_FUNCTION_KEY, ""),
        "virtual_power_pg_function": pins.get(VIRTUAL_POWER_PG_FUNCTION_KEY, ""),
        "enable_signal": pins.get(ENABLE_SIGNAL_KEY, ""),
        "enable_signal_pattern": enable_signal_pattern,
        "power_down_pattern": power_down_pattern,
        "power_down_rise_power": pins.get(POWER_DOWN_RISE_POWER_KEY, ""),
        "power_down_fall_power": pins.get(POWER_DOWN_FALL_POWER_KEY, ""),
        "power_down_when": pins.get(POWER_DOWN_WHEN_KEY, ""),
        "dbs_output_pattern": dbs_output_pattern,
        "dbs_related_pins": dbs_related_pins,
        "dbs_timing_sense": pins.get(DBS_TIMING_SENSE_KEY, ""),
        "dbs_timing_type": pins.get(DBS_TIMING_TYPE_KEY, ""),
        "port_pins": port_pins,
        # 다음 라운드를 위해 함께 넘겨두는 공통 필드 - 현재 block1~5에서는 직접
        # 쓰이지 않는다.
        "static_current": common.get("static_current", ""),
    }


def build_jobs(
    pairs: list[dict],
    pair_settings: dict,
    common: dict,
    pdk_folder: str,
    dbs_folder: str,
    scalars: dict,
    voltage_map_settings: dict,
    port_bit_values: list[int],
    power_ground_pins: dict,
    pins: dict,
    port_pins: list[dict],
) -> tuple[list[dict], list[str]]:
    """
    유효한 모든 pair에 대해 job을 만든다.

    Returns:
        (jobs, errors) - errors는 개별 pair 실패 메시지를 전부 모은 것. 실패한 pair는
        건너뛰고, 성공한 job들만 jobs에 담긴다(부분 실패해도 나머지는 계속 진행됨).
    """
    jobs: list[dict] = []
    errors: list[str] = []

    for pair in pairs:
        pair_errors: list[str] = []
        # Step2에서 pair별로 고른 bst/wst/tiv 선택값(voltage_map과는 다른 개념 - Step2의
        # pair_settings 저장 key는 그대로 "voltage_condition" 유지).
        voltage_condition_value = pair_settings.get(pair["pdk_file"], {}).get("voltage_condition", "")
        job = build_job(
            pair, voltage_condition_value, common, pdk_folder, dbs_folder, scalars,
            voltage_map_settings, port_bit_values, power_ground_pins, pins, port_pins, pair_errors,
        )
        if job is None:
            errors.extend(pair_errors)
        else:
            jobs.append(job)

    return jobs, errors
