"""
udc_validator.py

Step 2 Validate 로직 (2026-08 전면 재설계 -> 2026-08 2차 재설계).
GUI에 의존하지 않는 순수 함수로 작성.

검사 항목:
  1. 공통 필드(area/width/height/static_current/cell_name/MC·HDA·OUT Timing State)가
     전부 채워져 있는지 (숫자 필드는 숫자로 파싱 가능한지도 확인)
  2. liberty setting이 1개 이상 있는지
  3. 각 setting의 corner / beol inform / voltage / temperature / condition /
     PDK file / DBS file이 전부 빈 값 없이 채워져 있는지 (voltage/temperature는 숫자로
     읽히는지도 확인)
  4. 각 setting이 고른 PDK/DBS 파일이 현재 폴더에 실제로 존재하는지
  5. 같은 PDK/DBS 조합이 중복으로 들어가 있지 않은지 (같은 출력 파일을 두 번 쓰게 되므로)
"""

from __future__ import annotations

from step1_setup.file_scanner import list_dbs_mt0_files, list_pdk_lib_files
from step2_udc.udc_field_defs import (
    COMMON_FIELD_DEFS, CONDITION_OPTIONS, ENTRY_BEOL_KEY, ENTRY_CONDITION_KEY,
    ENTRY_CORNER_KEY, ENTRY_DBS_KEY, ENTRY_PDK_KEY, ENTRY_SELECT_FIELD_KEYS,
    ENTRY_TEMPERATURE_KEY, ENTRY_VOLTAGE_KEY, BEOL_OPTIONS, CORNER_OPTIONS,
    parse_temperature_input, parse_voltage_input,
)

_SELECT_FIELD_RULES = {
    ENTRY_CORNER_KEY: ("Corner", CORNER_OPTIONS),
    ENTRY_BEOL_KEY: ("BEOL Inform", BEOL_OPTIONS),
    ENTRY_CONDITION_KEY: ("Condition", CONDITION_OPTIONS),
}


def validate_common_fields(common: dict) -> list[str]:
    errors: list[str] = []
    for key, label, kind in COMMON_FIELD_DEFS:
        value = str(common.get(key, "")).strip()
        if not value:
            errors.append(f"{label} is empty.")
            continue
        if kind == "number":
            try:
                float(value)
            except ValueError:
                errors.append(f"{label} is not a valid number: {value!r}")
    return errors


def _entry_label(index: int, entry: dict) -> str:
    """에러 메시지 앞에 붙일 식별자. 아직 아무것도 안 골랐어도 행 번호로 구분된다."""
    pdk = str(entry.get(ENTRY_PDK_KEY, "")).strip()
    return f"Liberty #{index + 1}" + (f" ({pdk})" if pdk else "")


def validate_entries(
    entries: list[dict], pdk_files: list[str], dbs_files: list[str],
) -> list[str]:
    """
    liberty setting 목록을 검사한다.

    Args:
        entries: Step2에서 사용자가 만든 setting 목록
        pdk_files: 현재 PDK Folder에 실제로 있는 파일명 목록
        dbs_files: 현재 DBS Simulation Folder에 실제로 있는 파일명 목록
    """
    errors: list[str] = []
    if not entries:
        errors.append(
            "No liberty settings have been added. Add at least one setting "
            "(one liberty file is generated per setting)."
        )
        return errors

    pdk_set = set(pdk_files)
    dbs_set = set(dbs_files)
    seen_pairs: dict[tuple[str, str], int] = {}

    for index, entry in enumerate(entries):
        label = _entry_label(index, entry)

        for key in ENTRY_SELECT_FIELD_KEYS:
            field_label, options = _SELECT_FIELD_RULES[key]
            value = str(entry.get(key, "")).strip()
            if not value:
                errors.append(f"[{label}] {field_label} is not selected.")
            elif value not in options:
                errors.append(
                    f"[{label}] {field_label} {value!r} is not one of {'/'.join(options)}."
                )

        voltage_text = str(entry.get(ENTRY_VOLTAGE_KEY, "")).strip()
        if not voltage_text:
            errors.append(f"[{label}] Voltage is empty.")
        elif parse_voltage_input(voltage_text) is None:
            errors.append(f"[{label}] Voltage is not a valid number: {voltage_text!r}")

        temperature_text = str(entry.get(ENTRY_TEMPERATURE_KEY, "")).strip()
        if not temperature_text:
            errors.append(f"[{label}] Temperature is empty.")
        elif parse_temperature_input(temperature_text) is None:
            errors.append(
                f"[{label}] Temperature must be a whole number (filenames use e.g. 75c / m40c): "
                f"{temperature_text!r}"
            )

        pdk_file = str(entry.get(ENTRY_PDK_KEY, "")).strip()
        if not pdk_file:
            errors.append(f"[{label}] Primitive liberty file (PDK) is not selected.")
        elif pdk_file not in pdk_set:
            errors.append(
                f"[{label}] PDK file '{pdk_file}' no longer exists in the PDK Folder."
            )

        dbs_file = str(entry.get(ENTRY_DBS_KEY, "")).strip()
        if not dbs_file:
            errors.append(f"[{label}] DBS output file is not selected.")
        elif dbs_file not in dbs_set:
            errors.append(
                f"[{label}] DBS output file '{dbs_file}' no longer exists in the "
                "DBS Simulation Folder."
            )

        if pdk_file and dbs_file:
            key = (pdk_file, dbs_file)
            first_index = seen_pairs.setdefault(key, index)
            if first_index != index:
                errors.append(
                    f"[{label}] The same PDK/DBS combination is already used by "
                    f"Liberty #{first_index + 1} - both would write the same output file."
                )

    return errors


def validate_step2(state: dict, pdk_folder: str, dbs_folder: str) -> list[str]:
    """공통 필드 + liberty setting 목록을 한 번에 검사하는 편의 함수."""
    from step2_udc.udc_manager import get_entries

    errors = validate_common_fields(state.get("common", {}))
    errors += validate_entries(
        get_entries(state), list_pdk_lib_files(pdk_folder), list_dbs_mt0_files(dbs_folder),
    )
    return errors


def selected_pdk_files(state: dict) -> list[str]:
    """
    Step2 setting들이 고른 PDK 파일명 목록 (중복 제거, 입력 순서 유지).
    Step3의 'Worst case primitive liberty' 드롭다운 후보로 쓰인다.
    """
    from step2_udc.udc_manager import get_entries

    result: list[str] = []
    for entry in get_entries(state):
        pdk_file = str(entry.get(ENTRY_PDK_KEY, "")).strip()
        if pdk_file and pdk_file not in result:
            result.append(pdk_file)
    return result
