"""
liberty_writter.py

liberty 파일 하나를 실제로 쓰는 최상위 진입점. Block1~5 각각의 세부 로직은 별도
모듈로 분리되어 있고(파일당 800줄을 넘지 않도록), 이 파일은 그것들을 순서대로
호출하는 오케스트레이터 역할만 한다.

  - block1_header.py    : 헤더 주석
  - pdk_stream_reader.py : PDK/DK 파일 스트리밍 파싱 (block2에서 쓸 데이터 추출)
  - block2_writer.py    : library ~ k factor
  - block3_writer.py    : type_bus ~ lu_table_template
  - block4_writer.py    : cell(...) { ... pg_pin(...) { ... } ... } (cell을 연 채로 끝남)
  - block5_writer.py    : cell{} 안에 이어서 pin(...)/bus(...) 작성 (여전히 cell{} 안)
  - kfactor_block.py    : block2에서 쓰는 k factor 하드코딩 값
  - missing_data.py     : 결측 데이터 표시 공통 규칙 + 공통 들여쓰기 상수

PDK/DK 파일은 pdk_stream_reader.read_pdk_library_sections() 안에서 딱 한 번만 열어서
순차 스트리밍하며(30만 줄 이상 가능하므로 readlines() 금지), 여러 liberty를 동시에
생성하지 않는다(Step4는 pair를 1초 간격으로 하나씩 순차 처리).

2026-08 재설계 (성능): block3의 lu_table_template은 Step3에서 고른 worst case PDK
하나에서만 실행당 한 번 읽어(generate_view가 read_lut_table_sections()로 읽어서 이
함수에 lut_sections로 넘겨줌) 모든 liberty에 재사용한다. 그래서 이 함수가 이 job의
PDK에서 읽는 범위는 첫 `cell (...)` 선언 앞까지로 줄었고(=파일의 극히 일부),
block2를 다 쓴 직후에는 그 결과(특히 body_lines)를 즉시 비워서 메모리를 놓아준다 -
block5의 timing 표 작성이 그 뒤에 이어지므로 그때까지 붙들고 있을 이유가 없다.
"""

from __future__ import annotations

from step4_generate.block1_header import write_header_block
from step4_generate.block2_writer import write_block2
from step4_generate.block3_writer import write_block3
from step4_generate.block4_writer import write_block4
from step4_generate.block5_writer import write_block5
from step4_generate.missing_data import INDENT_1
from step4_generate.pdk_stream_reader import read_pdk_library_sections


def write_liberty_file(job: dict, output_path: str, lut_sections: dict) -> None:
    """
    job(liberty_assembler.build_job()의 결과)으로 output_path에 liberty 파일을 쓴다.
    이 job의 PDK/DK 파일 하나만 열어서 첫 cell 선언 앞까지 순차로 읽고(동시에 여러
    PDK를 열지 않음), 그 결과로 Block1 -> Block2 -> Block3 -> Block4 -> Block5를
    순서대로 작성한 뒤 cell과 library를 닫는다.

    Args:
        lut_sections: pdk_stream_reader.read_lut_table_sections()의 결과. Step3에서
            고른 worst case PDK 하나에서 실행당 한 번만 읽어, 생성하는 모든 liberty에
            그대로 재사용하는 값이다(pair마다 다시 읽지 않는다).
    """
    sections = read_pdk_library_sections(job["pdk_path"])

    with open(output_path, "w", encoding="utf-8") as f_out:
        header_date_parts = write_header_block(f_out, job["library_name"])
        write_block2(f_out, job, sections, header_date_parts)
        # block2를 다 썼으면 PDK에서 읽어온 값은 더 이상 필요 없다 - block3~5(특히
        # block5의 timing 표)를 쓰기 전에 즉시 메모리에서 놓아준다.
        sections.clear()
        write_block3(f_out, job, lut_sections)
        write_block4(f_out, job)  # cell{}을 연 채로 끝남 (pg_pin까지)
        write_block5(f_out, job)  # 같은 cell{} 안에 pin()/bus() 이어서 작성
        f_out.write(f"{INDENT_1}}}\n")  # cell{} 닫기
        f_out.write("}\n")  # library{} 닫기
