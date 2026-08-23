"""
pdk_stream_reader.py

PDK/DK(template_lib) 파일 하나를 처음부터 끝까지 딱 한 번, 줄 단위로 순차
스트리밍(`for line in f:` / `next(iterator)`)하면서 block2/block3 작성에 필요한
모든 것을 뽑아내는 모듈. PDK/DK 파일이 30만 줄을 넘을 수 있으므로 readlines()로 전체를
메모리에 올리지 않으며, 더 이상 읽을 필요가 없어지는 순간(마지막으로 필요한
index_1/index_2를 찾는 즉시) 읽기를 멈춘다.

한 번의 순차 스트리밍 안에서 아래 순서대로 진행한다 (실제 PDK/DK 파일 구조와 동일한
순서):
  1. `library (...) {` 줄을 찾는다.
  2. 그 다음 줄부터 `voltage_map`이 처음 등장하기 직전까지를 body_lines로 모은다
     (PDK 자체의 date/revision/comment 줄은 위치 상관없이 개별적으로 스킵).
  3. voltage_map 이후, 아래를 계속 찾아 나간다(전부 한 번의 순회 안에서):
     - 자신의 `operating_conditions(library명) {` 선언에서 library명
     - `input_voltage(...)  { vil; vih; vimax; vimin; }` 블록들 (등장하는 순서대로 전부)
     - `output_voltage(...) { vol; voh; vomax; vomin; }` 블록들 (등장하는 순서대로 전부)
     - `cell (DFF_CELL_NAME)` 로 시작하는 첫 줄
     - 그 이후 처음으로 PRIMITIVE_CELL_NAME이 등장하는 줄(보통
       `cell_rise(PRIMITIVE_CELL_NAME) {` 또는 `cell_fall(...)` 형태) - 찾으면 그
       블록 안에서 index_1/index_2 줄을 원문 그대로 캡처하고 즉시 스트리밍을 멈춘다.

결측 데이터 처리: 어떤 마커든 못 찾으면 예외를 던지지 않고 해당 필드를 비운 채
(None / 빈 리스트 / False) 반환한다. 실제 "결측 표시" 주석/토큰은 이 값들을 사용하는
block2_writer.py / block3_writer.py에서 작성한다.
"""

from __future__ import annotations

import re

_SKIP_TOKENS_IN_BODY = {"date", "revision", "comment"}
_OPERATING_CONDITIONS_PATTERN = re.compile(r"operating_conditions\s*\(([^)]*)\)")
_PAREN_CONTENT_PATTERN = re.compile(r"\(([^)]*)\)")

# index_1/index_2 검색을 무한정 계속하지 않도록 하는 안전장치(비정상적으로 큰
# cell_rise/cell_fall 블록을 만나도 멈추도록).
_MAX_INDEX_SEARCH_LINES = 2000
# DFF cell을 못 찾았을 때 "실제로 어떤 cell 이름들이 있었는지" 진단 메시지에 보여줄
# 목적으로만 기록 - 너무 많이 쌓이지 않도록 상한을 둔다(30만 줄짜리 파일에 cell이
# 수천 개 있어도 메모리에 문제 없도록).
_MAX_CELL_NAMES_TRACKED = 30


def _first_token(line: str) -> str:
    cleaned = line.replace("(", " ").replace(")", " ").replace(":", " ").replace(";", " ")
    tokens = cleaned.split()
    return tokens[0] if tokens else ""


def _paren_content(line: str) -> str:
    match = _PAREN_CONTENT_PATTERN.search(line)
    return match.group(1).strip() if match else ""


def _apply_voltage_subline(entry: dict, line: str) -> None:
    """'vil : 0.80000 ;' 형태의 줄에서 key/value를 뽑아 entry에 채운다."""
    cleaned = line.replace(":", " ").replace(";", " ")
    tokens = cleaned.split()
    if len(tokens) < 2:
        return
    try:
        entry[tokens[0]] = float(tokens[1])
    except ValueError:
        pass


def _new_result() -> dict:
    return {
        "found_library_decl": False,
        "body_lines": [],
        "found_voltage_map": False,
        "operating_conditions_library": None,
        "input_voltage_entries": [],
        "output_voltage_entries": [],
        "dff_found": False,
        "primitive_found": False,
        "index_1_line": None,
        "index_2_line": None,
        "cell_names_seen": [],
    }


def _read_voltage_block(it, first_line: str) -> dict:
    """
    'input_voltage(NAME) {' 또는 'output_voltage(NAME) {' 줄(first_line) 바로 다음
    4줄(vil/vih/vimax/vimin 또는 vol/voh/vomax/vomin)을 읽어 dict로 반환.
    (기존 make_liberty.py의 4줄 고정 판독 방식과 동일)
    """
    entry: dict = {"param": _paren_content(first_line)}
    for _ in range(4):
        sub_line = next(it, None)
        if sub_line is None:
            break
        _apply_voltage_subline(entry, sub_line)
    return entry


def _capture_index_lines(it, opening_line: str) -> tuple[str | None, str | None]:
    """
    primitive cell명이 처음 등장한 줄(opening_line, 보통 'cell_rise(PRIM) {' 형태)부터
    시작해서 그 블록이 닫힐 때까지(중괄호 깊이 추적) index_1 / index_2 줄을 찾아
    반환한다. 둘 다 찾으면 블록이 끝나기 전이라도 즉시 멈춘다.

    2026-08 수정: indent는 우리가 항상 2칸 기준으로 새로 입힐 것이므로, PDK 원본의
    들여쓰기는 버리고 내용(텍스트)만 완전히 strip해서 저장한다(줄 앞뒤 공백 제거).
    """
    index_1_line: str | None = None
    index_2_line: str | None = None

    depth = opening_line.count("{") - opening_line.count("}")
    scan_line = opening_line
    scanned = 0

    while True:
        stripped = scan_line.strip()
        if index_1_line is None and stripped.startswith("index_1"):
            index_1_line = stripped
        elif index_2_line is None and stripped.startswith("index_2"):
            index_2_line = stripped

        if index_1_line is not None and index_2_line is not None:
            break
        if depth <= 0 and scanned > 0:
            break
        if scanned >= _MAX_INDEX_SEARCH_LINES:
            break

        nxt = next(it, None)
        if nxt is None:
            break
        scan_line = nxt
        depth += scan_line.count("{") - scan_line.count("}")
        scanned += 1

    return index_1_line, index_2_line


def read_pdk_file(pdk_path: str, dff_cell_name: str, primitive_cell_name: str) -> dict:
    """
    PDK/DK 파일을 한 번만 순차 스트리밍하며 block2/block3 작성에 필요한 모든 것을
    뽑아낸다. 파일 전체를 메모리에 올리지 않고, 필요한 만큼만 읽는다.

    Returns: 위 _new_result()가 정의하는 형태의 dict.
    """
    result = _new_result()

    with open(pdk_path, "r", encoding="utf-8", errors="replace") as f:
        it = iter(f)

        # 1단계: `library (...) {` 줄을 찾을 때까지 건너뛴다
        for line in it:
            if _first_token(line) == "library":
                result["found_library_decl"] = True
                break
        if not result["found_library_decl"]:
            return result

        # 2단계: voltage_map 직전까지 본문 복사 (자체 date/revision/comment는 스킵).
        # 2026-08 수정: indent는 우리가 항상 2칸 기준으로 새로 입힐 것이므로, PDK
        # 원본의 들여쓰기는 버리고 내용(텍스트)만 strip해서 저장한다. 빈 줄도
        # "text가 적힌 부분만 가져온다"는 원칙에 따라 그대로 버린다.
        for line in it:
            token = _first_token(line)
            if token == "voltage_map":
                result["found_voltage_map"] = True
                break
            if token in _SKIP_TOKENS_IN_BODY:
                continue
            stripped = line.strip()
            if stripped:
                result["body_lines"].append(stripped)
        if not result["found_voltage_map"]:
            return result

        # 3단계: operating_conditions / input_voltage / output_voltage / DFF cell /
        # primitive cell(index_1, index_2)을 한 번의 순회로 계속 찾는다.
        #
        # 주의: input_voltage/output_voltage는 "블록 선언"(예: input_voltage(NAME) {)
        # 과 핀 안에서의 "단순 값 대입"(예: input_voltage : NAME ;, 핀 개수만큼 반복)
        # 둘 다 첫 토큰이 동일하므로, 그 줄에 '{'가 있어야만(=진짜 블록 선언일 때만)
        # 블록으로 취급한다. '{'가 없는 단순 대입 줄은 그냥 건너뛴다.
        looking_for_primitive = False
        for line in it:
            token = _first_token(line)

            if result["operating_conditions_library"] is None:
                match = _OPERATING_CONDITIONS_PATTERN.search(line)
                if match:
                    result["operating_conditions_library"] = match.group(1).strip()
                    continue

            if token == "input_voltage" and "{" in line:
                result["input_voltage_entries"].append(_read_voltage_block(it, line))
                continue

            if token == "output_voltage" and "{" in line:
                result["output_voltage_entries"].append(_read_voltage_block(it, line))
                continue

            if not result["dff_found"] and token == "cell":
                cell_name_here = _paren_content(line)
                if cell_name_here and len(result["cell_names_seen"]) < _MAX_CELL_NAMES_TRACKED:
                    result["cell_names_seen"].append(cell_name_here)
                if cell_name_here == dff_cell_name:
                    result["dff_found"] = True
                    looking_for_primitive = True
                continue

            if looking_for_primitive and not result["primitive_found"]:
                if primitive_cell_name and primitive_cell_name in line:
                    result["primitive_found"] = True
                    idx1, idx2 = _capture_index_lines(it, line)
                    result["index_1_line"] = idx1
                    result["index_2_line"] = idx2
                    # index_1/index_2를 찾았으니(또는 못 찾았어도) 더 읽을 필요가 없음 -
                    # 이 파일에서 필요한 마지막 정보였으므로 여기서 스트리밍을 멈춘다.
                    break
                continue

    return result
