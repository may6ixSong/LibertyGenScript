"""
liberty_writter.py

liberty 파일 하나를 실제로 쓰는 최상위 진입점. Block1~5 각각의 세부 로직은 별도
모듈로 분리되어 있고(파일당 800줄을 넘지 않도록), 이 파일은 그것들을 순서대로
호출하는 오케스트레이터 역할만 한다.

  - block1_header.py    : 헤더 주석
  - pdk_stream_reader.py : PDK/DK 파일 스트리밍 파싱 (block2/3에서 쓸 데이터 추출)
  - block2_writer.py    : library ~ k factor
  - block3_writer.py    : type_bus ~ lu_table_template
  - block4_writer.py    : cell(...) { ... pg_pin(...) { ... } ... } (cell을 연 채로 끝남)
  - block5_writer.py    : cell{} 안에 이어서 pin(...)/bus(...) 작성 (여전히 cell{} 안)
  - kfactor_block.py    : block2에서 쓰는 k factor 하드코딩 값
  - missing_data.py     : 결측 데이터 표시 공통 규칙 + 공통 들여쓰기 상수

PDK/DK 파일은 pdk_stream_reader.read_pdk_file() 안에서 딱 한 번만 열어서 순차
스트리밍하며(30만 줄 이상 가능하므로 readlines() 금지), 여러 liberty를 동시에
생성하지 않는다(Step4는 pair를 1초 간격으로 하나씩 순차 처리).
"""

from __future__ import annotations

from step4_generate.block1_header import write_header_block
from step4_generate.block2_writer import write_block2
from step4_generate.block3_writer import write_block3
from step4_generate.block4_writer import write_block4
from step4_generate.block5_writer import write_block5
from step4_generate.missing_data import INDENT_1
from step4_generate.pdk_stream_reader import read_pdk_file


def write_liberty_file(job: dict, output_path: str) -> None:
    """
    job(liberty_assembler.build_job()의 결과)으로 output_path에 liberty 파일을 쓴다.
    PDK/DK 파일 하나만 열어서 순차로 읽고(동시에 여러 PDK를 열지 않음), 그 결과로
    Block1 -> Block2 -> Block3 -> Block4 -> Block5를 순서대로 작성한 뒤 cell과
    library를 닫는다.
    """
    sections = read_pdk_file(job["pdk_path"], job["dff_cell_name"], job["primitive_cell_name"])

    with open(output_path, "w", encoding="utf-8") as f_out:
        header_date_parts = write_header_block(f_out, job["library_name"])
        write_block2(f_out, job, sections, header_date_parts)
        write_block3(f_out, job, sections)
        write_block4(f_out, job)  # cell{}을 연 채로 끝남 (pg_pin까지)
        write_block5(f_out, job)  # 같은 cell{} 안에 pin()/bus() 이어서 작성
        f_out.write(f"{INDENT_1}}}\n")  # cell{} 닫기
        f_out.write("}\n")  # library{} 닫기
