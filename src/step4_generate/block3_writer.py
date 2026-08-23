"""
block3_writer.py

Block 3 작성:
  3-(1) type_bus: Port List에서 Port=="PORT"인 핀들의 Bits 값을 모아 중복 제거한
        값들로 `type(bus_0_{bit-1}_{bit}_{cell_name})` 블록을 쓴다. 단, Bits 값이
        1인 경우는 제외한다(2026-08 확정 - 1비트짜리는 bus 타입이 필요 없음).
  3-(2) lu_table_template: variable_1/variable_2는 레거시 스크립트와 동일하게
        하드코딩(input_net_transition / total_output_net_capacitance)하고,
        index_1/index_2는 PDK/DK 파일에서 "cell (DFF Cell Name)" 선언 이후 처음
        등장하는 Primitive Cell Name 블록(cell_rise/cell_fall)의 index_1/index_2
        줄에서 값(텍스트)만 가져와 우리 들여쓰기로 다시 쓴다.

결측 데이터(DFF cell 못 찾음 / primitive cell 못 찾음 / index_1·index_2 못 찾음)는
missing_data.py 규칙대로 표시하고 예외를 던지지 않는다.

2026-08 수정: 들여쓰기를 항상 2칸 단위(INDENT_1/INDENT_2)로 통일했다.
"""

from __future__ import annotations

from step4_generate.missing_data import INDENT_1, INDENT_2, NOT_FOUND_TOKEN, write_missing_comment

# 레거시 make_liberty.py의 lu_table_template 하드코딩과 동일
# (y_index_var == "input_slope" -> "input_net_transition",
#  x_index_var == "output_load_cap" -> "total_output_net_capacitance")
_VARIABLE_1 = "input_net_transition"
_VARIABLE_2 = "total_output_net_capacitance"


def _write_type_bus_entries(f_out, bits: list[int], cell_name: str) -> None:
    for bit in bits:
        if bit == 1:
            continue  # 2026-08 확정: 1비트는 bus 타입 생성에서 제외
        type_name = f"bus_0_{bit - 1}_{bit}_{cell_name}"
        f_out.write(f"{INDENT_1}type({type_name}) {{\n")
        f_out.write(f"{INDENT_2}base_type : array;\n")
        f_out.write(f"{INDENT_2}data_type : bit;\n")
        f_out.write(f"{INDENT_2}bit_width : {bit};\n")
        f_out.write(f"{INDENT_2}bit_from  : {bit - 1};\n")
        f_out.write(f"{INDENT_2}bit_to    : 0;\n")
        f_out.write(f"{INDENT_2}downto    : true;\n")
        f_out.write(f"{INDENT_1}}}\n")


def _write_lu_table_template(f_out, job: dict, sections: dict) -> None:
    cell_name = job["cell_name"]
    pdk_filename = job["pdk_filename"]
    dff_cell_name = job["dff_cell_name"]
    primitive_cell_name = job["primitive_cell_name"]

    template_name = f"{cell_name}_{cell_name}_out"
    f_out.write(f"{INDENT_1}lu_table_template ({template_name}) {{\n")
    f_out.write(f"{INDENT_2}variable_1 : {_VARIABLE_1} ;\n")
    f_out.write(f"{INDENT_2}variable_2 : {_VARIABLE_2} ;\n")

    if not sections["dff_found"]:
        seen = sections.get("cell_names_seen") or []
        if seen:
            shown = ", ".join(seen[:10])
            more = f", ... ({len(seen)} shown, more may exist)" if len(seen) >= 10 else ""
            write_missing_comment(
                f_out, f"cell '{dff_cell_name}' (cell names actually seen: {shown}{more})", pdk_filename,
            )
        else:
            write_missing_comment(
                f_out,
                f"cell '{dff_cell_name}' (no 'cell (...)' declarations were seen at all after voltage_map)",
                pdk_filename,
            )
    elif not sections["primitive_found"]:
        write_missing_comment(
            f_out,
            f"primitive cell '{primitive_cell_name}' (after cell '{dff_cell_name}')",
            pdk_filename,
        )

    for key, index_line in (("index_1", sections.get("index_1_line")), ("index_2", sections.get("index_2_line"))):
        if index_line is not None:
            f_out.write(f"{INDENT_2}{index_line}\n")
        else:
            if sections["dff_found"] and sections["primitive_found"]:
                write_missing_comment(f_out, key, pdk_filename)
            f_out.write(f"{INDENT_2}{key} ({NOT_FOUND_TOKEN}) ;\n")

    f_out.write(f"{INDENT_1}}}\n")
    f_out.write("\n")


def write_block3(f_out, job: dict, sections: dict) -> None:
    """
    Args:
        job: liberty_assembler.build_job()의 결과 (cell_name, bits,
             dff_cell_name, primitive_cell_name, pdk_filename 포함).
        sections: pdk_stream_reader.read_pdk_file()의 결과.
    """
    _write_type_bus_entries(f_out, job["bits"], job["cell_name"])
    _write_lu_table_template(f_out, job, sections)
