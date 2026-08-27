"""
block5_writer.py

Block 5 작성: cell{} 안에 두 가지를 이어서 쓴다 (block4가 cell{}을 연 상태로
이어지므로, 닫는 중괄호는 여기서도 쓰지 않고 liberty_writter.py가 block5까지 다 쓴
뒤에 처리한다):

  1. Port List에서 Port=="PORT"인 핀들을 pin()/bus()로 쓴다 (먼저):
  2. {process_prefix}_pdt_pin(...) - Port List에서 Port=="PWR"/"GND"인 핀들
     (pin()/bus() 다음에 이어서 씀, 2026-08 확정). PWR 먼저, 그 다음 GND, 각 그룹
     내부는 Port List에 나온 순서 그대로. pin_type은 PWR이면 "power", GND면
     "ground". related_pin은 이 핀을 Related Power(PWR) / Related ground(GND)
     컬럼 값으로 쓰고 있는 다른 행들의 Pin name을 콤마로 나열(PWR은 Related Power만,
     GND는 Related ground만 봄 - 서로 교차 X). 관련된 핀이 하나도 없으면
     related_pin 줄 자체를 쓰지 않는다(2026-08 확정).

- Bits==1: `pin({pin name}) { ... }` 하나만 쓴다.
- Bits>1 : `bus({pin name에서 [MSB:LSB] 뺀 것}) { bus_type : ... ; pin({pin name
           그대로, [MSB:LSB] 포함}) { ... } }` 형태로 감싸서 쓴다. bus_type이
           가리키는 이름은 block3의 type_bus 이름과 동일하다.
- direction은 Port List의 I/O 컬럼 값(I/O)을 보고 input/output으로 정한다.

pin() 몸체 내용은 pin name이 아래 중 어디에 매치되는지에 따라 달라진다(우선순위,
2026-08 확정 - 여러 개 동시에 매치될 수 있어 순서를 정했다. 실제로는 서로 겹치지
않는 이름을 쓰는 게 일반적이라 우선순위가 문제될 일은 거의 없을 것):
  1. Step3 Enable Signal for power gate(와일드카드) - always_on/switch_pin 포맷
  2. Step3 DBS output signal(와일드카드) - max_capacitance + timing{} 블록
     (cell_fall/cell_rise/rise_transition/fall_transition, 이 job의 DBS output
     (.mt0) 파일에서 tplh/tphl/tr/tf 값을 읽어와 채움)
  3. Step3 Power down control signal(와일드카드) - {prefix}_acore_internal_power 추가
  4. 그 외 - 표준 포맷

값이 Port List/DBS 파일에서 파싱되지 않는 경우는 예외를 던지지 않고 missing_data.py
규칙대로 표시한다.

2026-08 수정 (Step3 연계 입력 반영):
  - DBS output pin의 timing{} 안 related_bus_pins는 Step3에서 "Check DBS Output Pins"로
    인식한 pin마다 사용자가 직접 입력한 related pin을 쓴다(job["dbs_related_pins"]).
    Step3 Validate가 이 값이 Port List에 실제 존재하는 pin이고 그 pin 행의 'Related Pin'
    컬럼 값과 정확히 일치하는지까지 검사한다. 입력이 없는 예외적인 경우에만 Port List의
    'Related Pin' 컬럼 값으로 폴백한다.
  - timing_sense / timing_type도 하드코딩이 아니라 Step3 입력값(인식된 DBS output pin
    전체 공통 1쌍)을 쓴다.
  - Power down control signal 매치 pin의 {prefix}_acore_internal_power 안 rise/fall
    power와 when 역시 Step3 입력값을 쓴다(예전 하드코딩 값이 그 입력의 기본값이다).

2026-08 수정: DBS output signal 매치 pin의 timing 표(cell_fall/cell_rise/
rise_transition/fall_transition)는 PDK/DK 파일과 완전히 무관하다는 피드백을 반영해,
PDK/DK 파일의 DFF/primitive cell 검색 결과(sections)에 대한 의존을 전부 제거했다.
표의 행/열 크기는 이제 순전히 DBS output(.mt0) 파일 자체에서
derive_table_shape()로 추론한다. 이에 따라 이 파일 전체에서 더 이상 `sections`
파라미터를 받지 않는다.
"""

from __future__ import annotations

import fnmatch

from step4_generate.missing_data import (
    INDENT_2, INDENT_3, INDENT_4, PORT_LIST_NOT_FOUND_TOKEN, write_missing_comment,
)
from step4_generate.mt0_reader import build_timing_table, derive_table_shape
from step4_generate.pdk_stream_reader import parse_index_last_value

# cell_fall/cell_rise/rise_transition/fall_transition 순서와, 각각이 .mt0 파일의
# 어느 컬럼에서 오는지 매핑 (2026-08 확정: tplh->cell_rise, tphl->cell_fall,
# tr->rise_transition, tf->fall_transition). 쓰는 순서는 사용자 예시와 동일하게
# cell_fall을 먼저 쓴다.
_TIMING_ENTRIES = [
    ("cell_fall", "tphl"),
    ("cell_rise", "tplh"),
    ("rise_transition", "tr"),
    ("fall_transition", "tf"),
]


def _strip_bit_range_suffix(pin_name: str) -> str:
    """'BUS0[3:0]' -> 'BUS0'. 대괄호가 없으면 그대로 반환."""
    idx = pin_name.find("[")
    return pin_name if idx == -1 else pin_name[:idx]


def _matches_pattern(pin_name: str, pattern: str) -> bool:
    if not pattern:
        return False
    return fnmatch.fnmatchcase(pin_name, pattern)


def _text_or_missing(f_out, value: str, description: str, pdk_filename: str) -> str:
    value = (value or "").strip()
    if not value:
        write_missing_comment(f_out, description, pdk_filename)
        return PORT_LIST_NOT_FOUND_TOKEN
    return value


def _cap_text(value: float | None) -> str:
    return PORT_LIST_NOT_FOUND_TOKEN if value is None else "%0.6f" % value


def _volts_text(value: float | None) -> str:
    return PORT_LIST_NOT_FOUND_TOKEN if value is None else "%0.5f" % value


def _direction_text(f_out, pin: dict, pdk_filename: str) -> str:
    io_value = (pin.get("io") or "").strip().upper()
    if io_value.startswith("I"):
        return "input"
    if io_value.startswith("O"):
        return "output"
    write_missing_comment(f_out, f"I/O value for pin '{pin['pin_name']}' (Port List)", pdk_filename)
    return PORT_LIST_NOT_FOUND_TOKEN


def _write_values_table(f_out, table: list[list[str]] | None, indent: str) -> None:
    f_out.write(f"{indent}values (")
    if table is None:
        f_out.write(f'"{PORT_LIST_NOT_FOUND_TOKEN}");\n')
        return
    row_texts = ['"' + " " + ", ".join(row) + '"' for row in table]
    for i, row_text in enumerate(row_texts):
        is_last = i == len(row_texts) - 1
        f_out.write(row_text if i == 0 else f"{indent}         {row_text}")
        f_out.write(");\n" if is_last else ",\\\n")


def _write_timing_block(f_out, pin: dict, job: dict, indent_decl: str) -> None:
    """
    DBS output signal과 매치된 pin의 timing() { ... } 블록. 값은 전부 이 job의 DBS
    output(.mt0) 파일에서만 읽어온다 - PDK/DK 파일은 전혀 참조하지 않는다(표의
    행/열 크기도 .mt0 파일 자체의 slope/cload 컬럼에서 derive_table_shape()로
    추론함).
    """
    cell_name = job["cell_name"]
    pdk_filename = job["pdk_filename"]
    dbs_filename = job["dbs_filename"]
    dbs_path = job["dbs_path"]
    template_name = f"{cell_name}_{cell_name}_out"

    body_indent = indent_decl + "  "
    table_indent = body_indent + "  "

    # Step3에서 이 pin에 대해 직접 입력받은 related pin이 우선 (Step3 Validate가 Port
    # List와의 일치까지 이미 확인함). 값이 없으면 Port List의 'Related Pin' 컬럼으로 폴백.
    related_pin_value = (job.get("dbs_related_pins") or {}).get(pin["pin_name"], "")
    if not str(related_pin_value).strip():
        related_pin_value = pin.get("related_pin", "")
    related_pin = _text_or_missing(
        f_out, related_pin_value, f"Related Pin for pin '{pin['pin_name']}' (Step 3 / Port List)", pdk_filename,
    )

    row_count, col_count, shape_error = derive_table_shape(dbs_path)

    f_out.write(f"{indent_decl}timing () {{\n")
    f_out.write(f'{body_indent}related_bus_pins : "{related_pin}";\n')
    f_out.write(f"{body_indent}timing_sense : {job['dbs_timing_sense']};\n")
    f_out.write(f"{body_indent}timing_type : {job['dbs_timing_type']};\n")

    for liberty_key, mt0_column in _TIMING_ENTRIES:
        if shape_error:
            table, reason = None, shape_error
        else:
            table, reason = build_timing_table(dbs_path, mt0_column, row_count, col_count)

        if table is None:
            f_out.write(
                f"{body_indent}####### {mt0_column} timing table (DBS output "
                f"'{dbs_filename}') is missing - reason: {reason} #########\n"
            )
        f_out.write(f"{body_indent}{liberty_key}({template_name}) {{\n")
        _write_values_table(f_out, table, table_indent)
        f_out.write(f"{body_indent}}}\n")

    f_out.write(f"{indent_decl}}}\n")


def _max_capacitance_value(lut_sections: dict) -> str | None:
    """
    max_capacitance 값 = worst case PDK에서 읽어 온 lu_table_template index_2의
    **맨 끝 값** (2026-08 확정). index_2를 못 찾았으면 None.
    """
    return parse_index_last_value((lut_sections or {}).get("index_2_line"))


def _write_max_capacitance(f_out, job: dict, lut_sections: dict, body_indent: str) -> None:
    value = _max_capacitance_value(lut_sections)
    if value is None:
        # index_2를 못 찾은 경우에만 예전처럼 주석으로 남긴다 - 값을 지어내지 않는다.
        write_missing_comment(
            f_out,
            "index_2 (max_capacitance source) of the lu_table_template",
            job.get("worst_case_pdk_filename", job["pdk_filename"]),
        )
        f_out.write(f"{body_indent}#max_capacitance : No Answer;\n")
        return
    f_out.write(f"{body_indent}max_capacitance : {value} ;\n")


def _write_pin_body(
    f_out, pin: dict, job: dict, lut_sections: dict, body_indent: str, pin_type_value: str,
) -> None:
    pdk_filename = job["pdk_filename"]
    process_prefix = job["process_prefix"]
    pin_name = pin["pin_name"]

    is_enable_signal = _matches_pattern(pin_name, job["enable_signal_pattern"])
    is_dbs_output = (not is_enable_signal) and _matches_pattern(pin_name, job["dbs_output_pattern"])
    is_power_down = (
        not is_enable_signal and not is_dbs_output
        and _matches_pattern(pin_name, job["power_down_pattern"])
    )

    direction = _direction_text(f_out, pin, pdk_filename)
    cap_text = _cap_text(pin["cap"])
    related_power = _text_or_missing(
        f_out, pin["related_power"], f"Related Power for pin '{pin_name}' (Port List)", pdk_filename,
    )
    related_ground = _text_or_missing(
        f_out, pin["related_ground"], f"Related ground for pin '{pin_name}' (Port List)", pdk_filename,
    )
    volts_text = _volts_text(pin["volts"])

    f_out.write(f"{body_indent}{process_prefix}_pin_type : {pin_type_value} ;\n")
    f_out.write(f"{body_indent}direction : {direction} ;\n")

    if is_enable_signal:
        f_out.write(f"{body_indent}always_on : true ;\n")
        f_out.write(f"{body_indent}switch_pin : true ;\n")
        f_out.write(f"{body_indent}capacitance : {cap_text} ;\n")
        f_out.write(f"{body_indent}related_power_pin : {related_power} ;\n")
        f_out.write(f"{body_indent}related_ground_pin : {related_ground} ;\n")
        f_out.write(f"{body_indent}{process_prefix}_input_signal_level : {volts_text} ;\n")
        return

    if is_dbs_output:
        f_out.write(f"{body_indent}capacitance : {cap_text} ;\n")
        # 2026-08 확정: max_capacitance는 worst case PDK의 lu_table_template index_2
        # 마지막 값을 그대로 쓴다 (예전엔 값을 몰라 "No Answer" 주석이었다).
        _write_max_capacitance(f_out, job, lut_sections, body_indent)
        f_out.write(f"{body_indent}related_power_pin : {related_power} ;\n")
        f_out.write(f"{body_indent}related_ground_pin : {related_ground} ;\n")
        f_out.write(f"{body_indent}{process_prefix}_input_signal_level : {volts_text} ;\n")
        f_out.write("\n")
        _write_timing_block(f_out, pin, job, body_indent)
        return

    f_out.write(f"{body_indent}capacitance : {cap_text} ;\n")
    f_out.write(f"{body_indent}related_power_pin : {related_power} ;\n")
    f_out.write(f"{body_indent}related_ground_pin : {related_ground} ;\n")
    f_out.write(f"{body_indent}{process_prefix}_input_signal_level : {volts_text} ;\n")

    if is_power_down:
        inner_body = body_indent + "  "
        f_out.write(f'{body_indent}{process_prefix}_acore_internal_power("{pin_name}") {{\n')
        f_out.write(f"{inner_body}{process_prefix}_acore_rise_power : {job['power_down_rise_power']} ;\n")
        f_out.write(f"{inner_body}{process_prefix}_acore_fall_power : {job['power_down_fall_power']} ;\n")
        f_out.write(f'{inner_body}{process_prefix}_acore_when : "{job["power_down_when"]}" ;\n')
        f_out.write(f"{body_indent}}}\n")


def _write_pin_block(
    f_out, pin: dict, job: dict, lut_sections: dict, decl_indent: str, body_indent: str,
    pin_type_value: str,
) -> None:
    f_out.write(f"{decl_indent}pin({pin['pin_name']}) {{\n")
    _write_pin_body(f_out, pin, job, lut_sections, body_indent, pin_type_value)
    f_out.write(f"{decl_indent}}}\n")


def _write_pdt_pin_block(f_out, pin: dict, pin_type: str, process_prefix: str) -> None:
    """
    {process_prefix}_pdt_pin(...) 블록 하나. PWR pin은 "power", GND pin은 "ground"
    로 pin_type을 쓴다. related_pin은 이 핀을 Related Power(PWR)/Related ground
    (GND) 컬럼 값으로 쓰고 있는 다른 Port List 행들의 Pin name을 콤마로 나열한다.
    나열할 때 'A[1:0]'처럼 bit range가 붙은 이름은 그 [MSB:LSB] 부분을 잘라내고
    순수 pin name만 적는다(2026-08 확정 - related_pin 표시에서만 그렇고, bus 핀
    자체의 pin()/bus() 선언에 쓰이는 전체 이름(bit range 포함)은 그대로 유지됨 -
    port_list_reader.py의 원본 데이터는 건드리지 않고 여기서 표시할 때만 잘라냄).
    관련된 핀이 하나도 없으면 related_pin 줄 자체를 아예 쓰지 않는다.
    """
    related_pins = [_strip_bit_range_suffix(name) for name in (pin.get("related_pins") or [])]
    f_out.write(f"{INDENT_2}{process_prefix}_pdt_pin({pin['pin_name']}) {{\n")
    f_out.write(f"{INDENT_3}{process_prefix}_pdt_pin_type : {pin_type} ;\n")
    if related_pins:
        related_text = ", ".join(related_pins)
        f_out.write(f'{INDENT_3}{process_prefix}_pdt_related_pin : "{related_text}" ;\n')
    f_out.write(f"{INDENT_2}}}\n")


def write_block5(f_out, job: dict, lut_sections: dict) -> None:
    """
    Args:
        job: liberty_assembler.build_job()의 결과 (cell_name, process_prefix,
             port_pins, pwr_pins, gnd_pins, enable_signal_pattern,
             power_down_pattern, power_down_rise_power/fall_power/when,
             dbs_output_pattern, dbs_related_pins, dbs_timing_sense/timing_type,
             dbs_path 포함).
        lut_sections: pdk_stream_reader.read_lut_table_sections()의 결과(worst case
             PDK에서 실행당 한 번 읽음). DBS output pin의 max_capacitance 값을 여기
             index_2의 마지막 값에서 가져온다.
    """
    cell_name = job["cell_name"]
    process_prefix = job["process_prefix"]

    # 2026-08 확정: pin()/bus() 를 먼저 전부 쓰고, 그 다음에
    # {process_prefix}_pdt_pin(...) (PWR 먼저, 그 다음 GND, 각 그룹 내부는 Port
    # List에 나온 순서 그대로)을 이어서 쓴다.
    for pin in job["port_pins"]:
        bits = pin["bits"]
        if bits == 1:
            _write_pin_block(f_out, pin, job, lut_sections, INDENT_2, INDENT_3, "data")
            continue

        base_name = _strip_bit_range_suffix(pin["pin_name"])
        bus_type = f"bus_0_{bits - 1}_{bits}_{cell_name}"
        f_out.write(f"{INDENT_2}bus({base_name}) {{\n")
        f_out.write(f"{INDENT_3}bus_type : {bus_type} ;\n")
        _write_pin_block(f_out, pin, job, lut_sections, INDENT_3, INDENT_4, "data_bus")
        f_out.write(f"{INDENT_2}}}\n")

    for pin in job["pwr_pins"]:
        _write_pdt_pin_block(f_out, pin, "power", process_prefix)
    for pin in job["gnd_pins"]:
        _write_pdt_pin_block(f_out, pin, "ground", process_prefix)
