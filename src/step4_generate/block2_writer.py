"""
block2_writer.py

Block 2 작성: `library (...) {` 선언부터 시작해서
  2-(1) library 선언 + 우리 쪽 date/revision/comment + PDK에서 정해진 접두어로 시작하는
        library 직속 한 줄 선언들(define/define_group, *_unit, default_*, nom_* 등 -
        그 외 PDK 본문 내용은 가져오지 않음, pdk_stream_reader._BODY_KEEP_PREFIXES 참고)
        + 이 생성기가 스스로 쓰는 나머지 {process_prefix}_* define/define_group
  2-(1') {process_prefix}_default_unit_area_cell : {DFF Cell Name} (voltage_map 직전 1줄)
  2-(2) voltage_map (power type 개수만큼의 VDD 줄 + VSS 1줄, Step2/Step3 값으로 항상
        전부 작성 - 2026-08 Voltage Map 재설계)
  2-(3) operating_conditions / default_operating_conditions (괄호 안 이름은 PDK가 아니라
        Step2 liberty setting의 corner/beol_inform/voltage/temperature로 조립 - 2026-08 변경)
  2-(4) Global k factor (하드코딩, kfactor_block.py)
까지를 담당한다.

PDK의 input_voltage / output_voltage 블록은 읽지도 쓰지도 않는다(2026-10 삭제 - 이
블록 없이도 liberty 생성/.db 변환에 문제가 없음을 확인).

결측 데이터(PDK에서 library 선언을 못 찾은 경우)는 missing_data.py의 규칙대로 안내
주석으로 표시하고 예외를 던지지 않는다.

2026-08 수정: 들여쓰기를 항상 2칸 단위(INDENT_1/INDENT_2)로 통일했다. PDK/DK 파일에서
읽어온 body_lines도 원본 들여쓰기를 버리고 텍스트만 가져와
INDENT_1로 다시 들여쓴다(pdk_stream_reader.py에서 이미 strip된 텍스트로 넘어옴).
레거시가 쓰던 tab 기반 정렬(예: "process    \t : ...")도 전부 "key : value ;" 형태의
단순한 한 칸 공백으로 통일했다.
"""

from __future__ import annotations

from step2_udc.udc_field_defs import (
    format_temperature_token, format_voltage_token, join_corner_beol,
)
from step4_generate.kfactor_block import write_k_factor_block
from step4_generate.missing_data import INDENT_1, INDENT_2, write_missing_comment
from step4_generate.process_prefix_defines import write_process_prefix_defines


def _format_oc_library(job: dict) -> str:
    """operating_conditions 괄호 안 이름: Step2 liberty setting 기준
    `{corner}_{beol_inform}_{voltage}_{temperature}c` (2026-08 변경 - PDK 파일 내부
    선언에서 읽어오던 값을 대체). voltage는 format_voltage_token()의 '0p{4자리}v'에서
    trailing 'v'만 뗀 형태(0.8 -> '0p8000'), temperature는 format_temperature_token()의
    'm{n}c'/'{n}c'를 그대로 쓴다(-40 -> 'm40c', 75 -> '75c'). BEOL Inform이 N/A면
    `{corner}_{voltage}_{temperature}c`로 beol 부분이 빠진다(2026-10)."""
    voltage_token = format_voltage_token(job["nom_voltage"])[:-1]
    temperature_token = format_temperature_token(job["nom_temperature"])
    # BEOL Inform이 N/A면(파일명에 BEOL 토큰이 없는 경우, 2026-10 추가) beol 부분을 뺀다.
    corner_beol = join_corner_beol(job["corner"], job["beol_inform"])
    return f"{corner_beol}_{voltage_token}_{temperature_token}"


def write_block2(f_out, job: dict, sections: dict, header_date_parts: tuple) -> None:
    """
    Args:
        job: liberty_assembler.build_job()의 결과.
        sections: pdk_stream_reader.read_pdk_file()의 결과.
        header_date_parts: block1_header.write_header_block()이 반환한
            (day, month, date, time, year) - block2의 date 줄에도 동일한 시각을 쓴다.
    """
    _day, month, date_, _time, year = header_date_parts
    library_name = job["library_name"]
    pdk_filename = job["pdk_filename"]

    # ---- Block 2-(1): library 선언 + 우리 쪽 date/revision/comment + PDK의 정해진 줄들 ----
    f_out.write("library (%s) {\n" % library_name)
    f_out.write(f'{INDENT_1}date : "{month}  {date_}  {year}" ;\n')
    f_out.write(f'{INDENT_1}revision : "V1.000 (TECH. FILE : V1.000)" ;\n')
    f_out.write(f'{INDENT_1}comment : "Copyright {year}, SAMSUNG Electronics" ;\n')

    if not sections["found_library_decl"]:
        write_missing_comment(f_out, "PDK body (library declaration)", pdk_filename)
    # sections["body_lines"]는 PDK 본문 전체가 아니라 정해진 접두어로 시작하는 library
    # 직속 한 줄 선언들만 담고 있다(pdk_stream_reader._BODY_KEEP_PREFIXES 참고) - 그 외
    # 내용은 PDK마다 제각각이라 우리가 쓸 필요가 없는데 그대로 딸려 들어오는 문제가 있었다.
    for line in sections["body_lines"]:
        f_out.write(f"{INDENT_1}{line}\n")

    # 이 생성기가 block4/block5에서 실제로 쓰는 {process_prefix}_* custom attribute는
    # 전부 여기서 스스로 define한다 (process_prefix_defines.py 모듈 docstring 참고 -
    # PDK가 일부만 define해두면 나머지 attribute를 cell{}/pin{}에서 쓰는 순간 Liberty
    # 컴파일러가 "attribute/group name cannot be specified here"로 거부해서 .db 변환이
    # 실패했다). 위에서 이미 옮겨 쓴 PDK의 define/define_group(sections["body_lines"])과
    # 이름이 같으면 건너뛰고 없는 것만 새로 쓴다 - PDK가 우리가 모르는 설정으로 이미
    # 정의해둔 걸 덮어쓰지 않기 위함. PDK의 define들 바로 다음, 우리 쪽 voltage_map보다
    # 앞에 둔다(PDK 자체의 define들과 한데 모여 있어 비교하기 쉽도록).
    write_process_prefix_defines(f_out, job["process_prefix"], sections["body_lines"])

    # default unit area cell - Step3의 DFF Cell Name을 그대로 쓴다. PDK 본문/define들
    # 다음, voltage_map 직전 위치(define은 process_prefix_defines.py의 library 그룹 항목).
    f_out.write(f"{INDENT_1}{job['process_prefix']}_default_unit_area_cell : {job['dff_cell_name']} ;\n")

    # ---- Block 2-(2): voltage_map - pg_pin 존재 여부와 무관하게 항상 전부 작성.
    # power type 개수만큼의 VDD 줄(이름은 Step3에서 입력한 Power Type voltage name,
    # 값은 이 job이 선택한 bst/wst/tiv 그룹의 해당 Power Type 값) + VSS 1줄(그대로).
    for voltage_type in job["voltage_types"]:
        f_out.write(
            f"{INDENT_1}voltage_map (VDD_%s, %0.5f) ;\n" % (voltage_type["name"], voltage_type["value"])
        )
    f_out.write(f"{INDENT_1}voltage_map (VSS_%0.5f, %0.5f) ;\n" % (0.0, 0.0))
    f_out.write("\n")

    # ---- Block 2-(3): operating_conditions / default_operating_conditions ----
    oc_library = _format_oc_library(job)

    f_out.write(f"{INDENT_1}operating_conditions ({oc_library}) {{\n")
    f_out.write(f"{INDENT_2}process : 1.000 ;\n")
    f_out.write(f"{INDENT_2}temperature : %0.3f ;\n" % job["nom_temperature"])
    f_out.write(f"{INDENT_2}voltage : %0.5f ;\n" % job["nom_voltage"])
    f_out.write(f'{INDENT_2}tree_type : "worst_case_tree" ;\n')
    f_out.write(f"{INDENT_1}}}\n")
    f_out.write(f"{INDENT_1}default_operating_conditions : {oc_library};\n")
    f_out.write("\n")

    # ---- Block 2-(4): Global k factor (하드코딩) ----
    write_k_factor_block(f_out)
