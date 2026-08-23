"""
udc_validator.py

Step 2 Validate 로직 (2026-08 전면 재설계).
GUI에 의존하지 않는 순수 함수로 작성.

검사 항목:
  1. 공통 필드(area/width/height/static_current/cell_name/MC·HDA·OUT Timing State)가
     전부 채워져 있는지 (숫자 필드는 숫자로 파싱 가능한지도 확인)
  2. PDK Folder / DBS Simulation Folder를 재스캔해 계산한 pair가 1개 이상인지
  3. 각 pair마다 Voltage Condition(bst/wst/tiv)이 선택되어 있는지

1:1이 안 되는 파일(unmatched)은 여기서 에러로 취급하지 않는다 - 그건 warning으로만
표시되고 생성 대상에서 제외될 뿐이다 (compute_current_pairs가 반환하는
unmatched_pdk/unmatched_dbs 참고).
"""

from __future__ import annotations

from step1_setup.file_scanner import list_dbs_mt0_files, list_pdk_lib_files
from step2_udc.udc_field_defs import COMMON_FIELD_DEFS, VOLTAGE_CONDITION_OPTIONS, compute_pairs


def compute_current_pairs(pdk_folder: str, dbs_folder: str) -> dict:
    pdk_files = list_pdk_lib_files(pdk_folder)
    dbs_files = list_dbs_mt0_files(dbs_folder)
    return compute_pairs(pdk_files, dbs_files)


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


def validate_pairs(pairs: list[dict], pair_settings: dict) -> list[str]:
    errors: list[str] = []
    if not pairs:
        errors.append(
            "No valid 1:1 PDK/DK <-> DBS output pairs were found. "
            "Check the PDK Folder / DBS Simulation Folder from Step 1."
        )
        return errors

    for pair in pairs:
        value = pair_settings.get(pair["pdk_file"], {}).get("voltage_condition", "")
        if value not in VOLTAGE_CONDITION_OPTIONS:
            errors.append(
                f"[{pair['pdk_file']}] Voltage Condition (bst/wst/tiv) is not selected."
            )
    return errors
