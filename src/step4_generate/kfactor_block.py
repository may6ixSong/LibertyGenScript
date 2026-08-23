"""
kfactor_block.py

block2의 마지막 부분인 "Global k factor" 섹션(cell delay/transition, hazard, wire).
레거시 `make_liberty.py`의 하드코딩 값을 그대로 옮겨왔다 - 사용자 데이터에 따라
바뀌는 값이 아니므로 UDC/Step2/Step3 어떤 입력과도 무관하게 항상 동일하게 쓰인다.

2026-08 수정: 레거시 script가 쓰던 tab/다양한 칸수의 정렬용 공백을 전부 없애고,
library { ... } 바로 아래(1단계) 항목이므로 항상 INDENT_1(2칸)만 쓰도록 통일했다.
값/이름 자체는 레거시와 동일.
"""

from __future__ import annotations

from step4_generate.missing_data import INDENT_1

# (key, value) 튜플 리스트. None은 "/* ... */" 섹션 제목 또는 빈 줄을 의미하며
# write_k_factor_block()이 그대로 순서대로 써넣는다.
_SECTION_1_TITLE = "/* Global k factor for cell delay and transition */"
_SECTION_1_LINES = [
    ("k_process_cell_rise", "1.0000000"),
    ("k_process_cell_fall", "1.0000000"),
    ("k_process_rise_transition", "1.0000000"),
    ("k_process_fall_transition", "1.0000000"),
    ("k_temp_cell_rise", "0.0000000"),
    ("k_temp_cell_fall", "0.0000000"),
    ("k_temp_rise_transition", "0.0000000"),
    ("k_temp_fall_transition", "0.0000000"),
    ("k_volt_cell_rise", "0.0000000"),
    ("k_volt_cell_fall", "0.0000000"),
    ("k_volt_rise_transition", "0.0000000"),
    ("k_volt_fall_transition", "0.0000000"),
]

_SECTION_2_TITLE = "/* Global k factor for hazard */"
_SECTION_2_LINES = [
    ("k_process_setup_rise", "1.0000000"),
    ("k_process_setup_fall", "1.0000000"),
    ("k_process_hold_rise", "1.0000000"),
    ("k_process_hold_fall", "1.0000000"),
    ("k_temp_setup_rise", "0.0000000"),
    ("k_temp_setup_fall", "0.0000000"),
    ("k_temp_hold_rise", "0.0000000"),
    ("k_temp_hold_fall", "0.0000000"),
    ("k_volt_setup_rise", "0.0000000"),
    ("k_volt_setup_fall", "0.0000000"),
    ("k_volt_hold_rise", "0.0000000"),
    ("k_volt_hold_fall", "0.0000000"),
    ("k_process_recovery_rise", "1.0000000"),
    ("k_process_recovery_fall", "1.0000000"),
    ("k_temp_recovery_rise", "0.0000000"),
    ("k_temp_recovery_fall", "0.0000000"),
    ("k_volt_recovery_rise", "0.0000000"),
    ("k_volt_recovery_fall", "0.0000000"),
    ("k_process_removal_rise", "1.0000000"),
    ("k_process_removal_fall", "1.0000000"),
    ("k_temp_removal_rise", "0.0000000"),
    ("k_temp_removal_fall", "0.0000000"),
    ("k_volt_removal_rise", "0.0000000"),
    ("k_volt_removal_fall", "0.0000000"),
    ("k_process_min_pulse_width_high", "1.0000000"),
    ("k_process_min_pulse_width_low", "1.0000000"),
    ("k_temp_min_pulse_width_high", "0.0000000"),
    ("k_temp_min_pulse_width_low", "0.0000000"),
    ("k_volt_min_pulse_width_high", "0.0000000"),
    ("k_volt_min_pulse_width_low", "0.0000000"),
]

_SECTION_3_TITLE = "/* Global k factor for wire */"
_SECTION_3_LINES = [
    ("k_process_wire_res", "0.0000000"),
    ("k_volt_wire_res", "0.0000000"),
    ("k_temp_wire_res", "0.0000000"),
    None,  # 레거시와 동일하게 res/cap 그룹 사이에 빈 줄 하나
    ("k_process_wire_cap", "0.0000000"),
    ("k_volt_wire_cap", "0.0000000"),
    ("k_temp_wire_cap", "0.0000000"),
]

_SECTIONS = [
    (_SECTION_1_TITLE, _SECTION_1_LINES),
    (_SECTION_2_TITLE, _SECTION_2_LINES),
    (_SECTION_3_TITLE, _SECTION_3_LINES),
]


def write_k_factor_block(f_out) -> None:
    for title, lines in _SECTIONS:
        f_out.write(title + "\n")
        f_out.write("\n")
        for entry in lines:
            if entry is None:
                f_out.write("\n")
                continue
            key, value = entry
            f_out.write(f"{INDENT_1}{key} : {value} ;\n")
        f_out.write("\n")
