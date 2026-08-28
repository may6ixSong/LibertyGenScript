"""
block4_writer.py

Block 4 작성: `cell ({udc cell name}) { ... }` - Step2 공통 필드/Step3 Constants/
파일명 파싱 결과(nom_voltage, nom_temperature)로 채우는 셀 속성들과, Port List의
PWR/GND 핀으로부터 만드는 pg_pin 블록들.

pg_pin 순서(2026-08 확정): Power 그룹 전체 먼저, 그 다음 Ground 그룹 전체. 각 그룹
내부는 Port List에 나온 행 순서 그대로. Pin name이 Step3에서 선택한 Virtual Power
(power gate) 핀과 같으면 internal_power 형태로 특별히 쓴다.

값이 Port List에서 파싱되지 않는 경우(Volts 컬럼이 숫자로 안 읽히는 등)는 예외를
던지지 않고 missing_data.py 규칙대로 표시한다.

2026-08 수정: block5(pin()/bus())가 이 cell{} 안에 이어서 작성되므로, 이 모듈은
더 이상 cell{}을 닫지 않는다 - 닫는 중괄호는 block5까지 다 쓴 뒤
liberty_writter.py에서 처리한다.

2026-08 수정: Virtual Power pg_pin의 switch_function / pg_function은 더 이상 코드에
하드코딩하지 않는다. Step3 Pin Settings에서 Virtual Power (power gate) 바로 아래에
연계 입력으로 받는 "Virtual Power Switch Function" / "Virtual Power PG Function" 값을
그대로 쓴다 (둘 다 와일드카드 불가, Step3 Validate에서 빈 값/와일드카드를 거른다).

2026-08 Voltage Map 재설계: pg_pin의 voltage_name은 더 이상 항상 Port List Volts 값을
그대로 포맷해서 쓰지 않는다. 그 Volts 값이 Step3 Voltage Map에서 Power Type마다 사용자가
직접 입력한 voltage(digital) 값과 일치하면 그 Power Type에 입력한 voltage name을 대신
쓰고(block2가 쓰는 voltage_map 이름과 정확히 같아야 리버티 문법상 유효하므로 둘 다 이름만
사용), 일치하는 Power Type이 없으면 기존처럼 Volts 값을 그대로 포맷해서 쓴다
(job["voltage_name_thresholds"], liberty_assembler.build_job 참고).

2026-08 추가: Power Type 개수 제한이 없어지고 voltage(digital)이 사용자 입력 필드가
되면서(예전에는 0.8V/2.2V/1.8V로 코드에 고정), 이 매칭 임계값(VOLTAGE_MATCH_TOLERANCE)
은 constants_field_defs.py로 옮겨 block5_writer.py의 input_signal_level 치환과
공유한다 - 둘 다 "Port List Volts 값이 어느 Power Type과 같다고 볼지"를 판단하는
같은 기준을 써야 하므로.
"""

from __future__ import annotations

from step3_settings.constants_field_defs import VOLTAGE_MATCH_TOLERANCE
from step4_generate.missing_data import INDENT_1, INDENT_2, INDENT_3, PORT_LIST_NOT_FOUND_TOKEN, write_missing_comment


def _voltage_name_text(
    voltage_prefix: str, voltage_value: float | None, voltage_name_thresholds: dict[float, str],
) -> str:
    if voltage_value is None:
        return f"{voltage_prefix}_{PORT_LIST_NOT_FOUND_TOKEN}"
    for threshold, name in voltage_name_thresholds.items():
        if name and abs(voltage_value - threshold) < VOLTAGE_MATCH_TOLERANCE:
            return f"{voltage_prefix}_{name}"
    return "%s_%0.5f" % (voltage_prefix, voltage_value)


def _write_standard_pg_pin(
    f_out, pin: dict, voltage_prefix: str, pg_type_suffix: str, pdk_filename: str,
    voltage_name_thresholds: dict[float, str],
) -> None:
    pin_name = pin["pin_name"]
    voltage_value = pin["voltage_value"]
    if voltage_value is None:
        write_missing_comment(f_out, f"Volts value for pin '{pin_name}' (Port List)", pdk_filename)
    voltage_name = _voltage_name_text(voltage_prefix, voltage_value, voltage_name_thresholds)

    f_out.write(f"{INDENT_2}pg_pin ({pin_name}) {{\n")
    f_out.write(f"{INDENT_3}voltage_name : {voltage_name} ;\n")
    f_out.write(f"{INDENT_3}pg_type : primary_{pg_type_suffix} ;\n")
    f_out.write(f"{INDENT_2}}}\n")


def _write_virtual_power_pg_pin(
    f_out, pin: dict, voltage_prefix: str, pdk_filename: str,
    switch_function: str, pg_function: str, voltage_name_thresholds: dict[float, str],
) -> None:
    pin_name = pin["pin_name"]
    voltage_value = pin["voltage_value"]
    if voltage_value is None:
        write_missing_comment(f_out, f"Volts value for pin '{pin_name}' (Port List)", pdk_filename)
    voltage_name = _voltage_name_text(voltage_prefix, voltage_value, voltage_name_thresholds)

    f_out.write(f"{INDENT_2}pg_pin ({pin_name}) {{\n")
    f_out.write(f"{INDENT_3}voltage_name : {voltage_name} ;\n")
    f_out.write(f"{INDENT_3}pg_type : internal_power ;\n")
    f_out.write(f"{INDENT_3}direction : output ;\n")
    f_out.write(f'{INDENT_3}switch_function : "{switch_function}" ;\n')
    f_out.write(f'{INDENT_3}pg_function : "{pg_function}" ;\n')
    f_out.write(f"{INDENT_2}}}\n")


def write_block4(f_out, job: dict) -> None:
    """
    Args:
        job: liberty_assembler.build_job()의 결과 (cell_name, process_prefix,
             class_value, area/width/height, nom_voltage/nom_temperature,
             pwr_pins/gnd_pins, virtual_power_pin, enable_signal,
             virtual_power_switch_function, virtual_power_pg_function 포함).
    """
    pdk_filename = job["pdk_filename"]
    cell_name = job["cell_name"]
    process_prefix = job["process_prefix"]

    f_out.write(f"{INDENT_1}cell ({cell_name}) {{\n")
    f_out.write(f"{INDENT_2}is_macro_cell : true ;\n")
    f_out.write(f"{INDENT_2}switch_cell_type : fine_grain ;\n")
    f_out.write(f"{INDENT_2}{process_prefix}_class : {job['class_value']} ;\n")
    f_out.write(f"{INDENT_2}{process_prefix}_cell_type : core ;\n")
    f_out.write(f"{INDENT_2}area : %0.5f ;\n" % job["area"])
    f_out.write(f"{INDENT_2}{process_prefix}_width : %0.5f ;\n" % job["width"])
    f_out.write(f"{INDENT_2}{process_prefix}_height : %0.5f ;\n" % job["height"])
    f_out.write(f"{INDENT_2}dont_use : true ;\n")
    f_out.write(f"{INDENT_2}dont_touch : true ;\n")
    f_out.write(f'{INDENT_2}{process_prefix}_voltage : "%0.5f" ;\n' % job["nom_voltage"])
    f_out.write(f'{INDENT_2}{process_prefix}_temperature : "%0.5f" ;\n' % job["nom_temperature"])
    f_out.write(f"{INDENT_2}cell_leakage_power : 0.00000 ;\n")
    f_out.write("\n")

    virtual_power_pin = job["virtual_power_pin"]
    voltage_name_thresholds = job["voltage_name_thresholds"]

    for pin in job["pwr_pins"]:
        if pin["pin_name"] == virtual_power_pin:
            _write_virtual_power_pg_pin(
                f_out, pin, "VDD", pdk_filename,
                job["virtual_power_switch_function"], job["virtual_power_pg_function"],
                voltage_name_thresholds,
            )
        else:
            _write_standard_pg_pin(f_out, pin, "VDD", "power", pdk_filename, voltage_name_thresholds)

    for pin in job["gnd_pins"]:
        _write_standard_pg_pin(f_out, pin, "VSS", "ground", pdk_filename, voltage_name_thresholds)

    # cell{}은 아직 닫지 않는다 - block5(pin()/bus())가 이어서 이 안에 써진다.
