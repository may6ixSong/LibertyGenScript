"""
pdk_stream_reader.py

PDK/DK(template_lib) 파일을 줄 단위로 순차 스트리밍(`for line in f:` / `next(iterator)`)
하면서 필요한 것만 뽑아내는 모듈. PDK/DK 파일은 30만 줄이 넘는 대용량이므로 절대
readlines()로 전체를 메모리에 올리지 않으며, 더 이상 읽을 필요가 없어지는 순간 즉시
읽기를 멈춘다.

2026-08 재설계 (성능): 예전에는 파일 하나를 끝까지 훑으면서 block2용 데이터와 block3의
lu_table_template(index_1/index_2)을 한 번에 뽑았다. 이제 lu_table_template은 pair마다
각자의 PDK에서 찾는 게 아니라 Step3에서 고른 "Worst case primitive liberty" PDK 하나
에서만 찾아 모든 liberty에 재사용하므로, 두 가지 읽기를 완전히 분리했다:

  1. read_pdk_library_sections(pdk_path)  - liberty 하나당 한 번 (block2용)
     library 선언 ~ voltage_map ~ input_voltage / output_voltage까지만 필요하다. 이
     값들은 전부 첫 `cell (...)` 선언보다 앞에 있으므로, 첫 cell 선언을 만나는 즉시
     읽기를 멈춘다 - 파일의 압도적인 대부분(cell 본문 수십만 줄)은 아예 읽지 않는다.
     **`library (...) {` ~ 첫 `voltage_map` 줄 사이는 `define`/`define_group` 줄만
     골라서 가져오고 나머지는 전부 버린다**(2026-08 변경 - 예전에는 이 구간 전체를
     그대로 복사했는데, PDK/DK 파일마다 이 구간에 무엇이 있는지가 제각각이라 우리가
     모르는/불필요한 내용까지 그대로 딸려 들어오는 문제가 있었다. 이 구간에서 우리가
     실제로 쓰는 건 `{process_prefix}_*` custom attribute의 `define`/`define_group`
     문뿐이므로 그것만 남긴다 - process_prefix_defines.py가 "PDK가 이미 정의해둔
     이름은 건너뛴다" 판단에 이 결과를 그대로 쓴다).

  2. read_lut_table_sections(pdk_path, dff_cell_name, lut_table_name) - 실행당 한 번
     (block3용, worst case PDK 전용) cell 영역만 보므로 body_lines 같은 건 아예 모으지
     않고, index_1/index_2를 찾는 즉시 멈춘다.

결측 데이터 처리: 어떤 마커든 못 찾으면 예외를 던지지 않고 해당 필드를 비운 채
(None / 빈 리스트 / False) 반환한다. 실제 "결측 표시" 주석/토큰은 이 값들을 사용하는
block2_writer.py / block3_writer.py에서 작성한다.
"""

from __future__ import annotations

import re

# library 선언 ~ 첫 voltage_map 줄 사이에서 실제로 가져올 줄의 첫 토큰. 이 두 가지가
# 아니면(date/revision/comment 포함, PDK마다 뭐가 더 있을지 모르는 그 외 전부) 버린다.
_BODY_KEEP_TOKENS = {"define", "define_group"}
_PAREN_CONTENT_PATTERN = re.compile(r"\(([^)]*)\)")

# index_1/index_2 검색을 무한정 계속하지 않도록 하는 안전장치(비정상적으로 큰
# cell_rise/cell_fall 블록을 만나도 멈추도록).
_MAX_INDEX_SEARCH_LINES = 2000
# LUT Table을 못 찾았을 때 "실제로 어떤 cell 이름들이 있었는지" 진단 메시지에 보여줄
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


def _read_voltage_block(it, first_line: str) -> dict:
    """
    'input_voltage(NAME) {' 또는 'output_voltage(NAME) {' 줄(first_line) 바로 다음
    4줄(vil/vih/vimax/vimin 또는 vol/voh/vomax/vomin)을 읽어 dict로 반환.
    (기존 make_liberty.py의 4줄 고정 판독 방식과 동일)

    2026-08 버그 수정: 이 블록을 닫는 '}' 줄까지 여기서 같이 소비한다. 예전에는
    안 그래서 그 '}'가 그대로 iterator에 남아 스트리밍을 이어가는 다음 단계(예:
    첫 voltage_map 줄 이후 구간을 읽는 3단계)로 넘어가 버렸는데, 그 단계가
    "input_voltage/output_voltage/cell이 아닌 줄은 본문으로 옮긴다"로 바뀌면서
    이 남은 '}'까지 본문에 그대로 섞여 들어가 library{} 전체의 중괄호 균형이
    깨지는 문제가 있었다.
    """
    entry: dict = {"param": _paren_content(first_line)}
    for _ in range(4):
        sub_line = next(it, None)
        if sub_line is None:
            break
        _apply_voltage_subline(entry, sub_line)
    next(it, None)  # 이 블록을 닫는 '}' 줄 소비
    return entry


def _capture_index_lines(it, opening_line: str) -> tuple[str | None, str | None]:
    """
    LUT Table명이 처음 등장한 줄(opening_line, 보통 'cell_rise(LUT) {' 형태)부터
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


# ---------------------------------------------------------------------------
# 1) block2용: liberty 하나당 한 번. 첫 cell 선언을 만나면 즉시 멈춘다.
# ---------------------------------------------------------------------------
def new_library_sections() -> dict:
    return {
        "found_library_decl": False,
        "body_lines": [],
        "found_voltage_map": False,
        "input_voltage_entries": [],
        "output_voltage_entries": [],
    }


def read_pdk_library_sections(pdk_path: str) -> dict:
    """
    block2 작성에 필요한 것만 뽑아낸다 (library 선언 / define·define_group 줄 /
    input_voltage / output_voltage). 이 값들은 전부 첫 `cell (...)` 선언 앞에 있으므로,
    첫 cell 선언을 만나는 즉시 읽기를 멈춘다.

    Returns: 위 new_library_sections()가 정의하는 형태의 dict.
    """
    result = new_library_sections()

    with open(pdk_path, "r", encoding="utf-8", errors="replace") as f:
        it = iter(f)

        # 1단계: `library (...) {` 줄을 찾을 때까지 건너뛴다
        for line in it:
            if _first_token(line) == "library":
                result["found_library_decl"] = True
                break
        if not result["found_library_decl"]:
            return result

        # 2단계: voltage_map 직전까지, define/define_group 줄만 골라서 가져온다
        # (2026-08 변경 - 위 모듈 docstring 참고. 그 외 줄은 date/revision/comment를
        # 포함해 전부 버린다). indent는 우리가 항상 2칸 기준으로 새로 입힐 것이므로,
        # PDK 원본의 들여쓰기는 버리고 내용(텍스트)만 strip해서 저장한다.
        for line in it:
            token = _first_token(line)
            if token == "voltage_map":
                result["found_voltage_map"] = True
                break
            if token not in _BODY_KEEP_TOKENS:
                continue
            stripped = line.strip()
            if stripped:
                result["body_lines"].append(stripped)
        if not result["found_voltage_map"]:
            return result

        # 3단계: input_voltage / output_voltage 를 찾는다.
        #
        # 주의: input_voltage/output_voltage는 "블록 선언"(예: input_voltage(NAME) {)
        # 과 핀 안에서의 "단순 값 대입"(예: input_voltage : NAME ;, 핀 개수만큼 반복)
        # 둘 다 첫 토큰이 동일하므로, 그 줄에 '{'가 있어야만(=진짜 블록 선언일 때만)
        # 블록으로 취급한다. '{'가 없는 단순 대입 줄은 그냥 건너뛴다.
        #
        # 이 구간(첫 voltage_map 줄 ~ 첫 cell 선언)의 나머지 줄(PDK 자체의 추가
        # voltage_map 줄, operating_conditions/default_operating_conditions 등)은
        # 의도적으로 버린다 - operating_conditions는 우리가 Step2 값으로 따로 조립해서
        # 쓰므로(block2_writer._format_oc_library, "Step 4 - Block 2-(3)" 참고) PDK
        # 원본을 그대로 옮기면 같은 라이브러리 안에 중복 선언된다.
        for line in it:
            token = _first_token(line)

            # cell 영역이 시작되면 block2에 필요한 건 전부 지나간 것이므로 즉시 중단.
            # PDK 파일의 대부분(수십만 줄)이 여기부터이므로, 이 조기 중단이 성능의
            # 핵심이다 (2026-08: lu_table_template을 worst case PDK 하나에서만 읽도록
            # 바뀌면서 가능해짐).
            if token == "cell" and "(" in line:
                break

            if token == "input_voltage" and "{" in line:
                result["input_voltage_entries"].append(_read_voltage_block(it, line))
                continue

            if token == "output_voltage" and "{" in line:
                result["output_voltage_entries"].append(_read_voltage_block(it, line))
                continue

    return result


# ---------------------------------------------------------------------------
# 2) block3용: 실행당 한 번, Step3에서 고른 worst case PDK에 대해서만.
# ---------------------------------------------------------------------------
def new_lut_sections() -> dict:
    return {
        "dff_found": False,
        "primitive_found": False,
        "index_1_line": None,
        "index_2_line": None,
        "cell_names_seen": [],
    }


_INDEX_VALUE_PATTERN = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def parse_index_last_value(index_line: str | None) -> str | None:
    """
    index 줄에서 **맨 끝 값**을 원문 표기 그대로 뽑는다 (2026-08 추가).

        index_2 ("0.0001, 0.0005, 0.0025");        -> "0.0025"
        index_2 ("0.0001", "0.0005", "0.0025") ;   -> "0.0025"

    block5의 max_capacitance는 worst case PDK에서 읽은 index_2의 마지막 값을 쓴다
    (2026-08 확정 - 예전에는 값을 몰라서 `#max_capacitance : No Answer;` 주석이었다).
    숫자를 하나도 못 찾으면 None(호출 측에서 결측 처리).
    """
    if not index_line:
        return None
    # 'index_2' 자체에 붙은 숫자(2)가 값으로 잡히지 않도록 괄호 안쪽만 본다.
    start = index_line.find("(")
    end = index_line.rfind(")")
    body = index_line[start + 1: end] if start != -1 and end > start else index_line
    matches = _INDEX_VALUE_PATTERN.findall(body)
    return matches[-1] if matches else None


def read_lut_table_sections(pdk_path: str, dff_cell_name: str, lut_table_name: str) -> dict:
    """
    block3의 lu_table_template에 쓸 index_1/index_2 줄을 뽑아낸다. "cell (DFF Cell
    Name)" 선언을 먼저 찾고, 그 이후 처음으로 LUT Table명이 등장하는 줄(보통
    `cell_rise(LUT) {` / `cell_fall(...)`)의 블록에서 index_1/index_2를 원문 그대로
    캡처한 뒤 즉시 스트리밍을 멈춘다.

    2026-08 확정: 이 결과는 pair마다 다시 읽지 않고, Step3에서 고른 worst case PDK
    하나에 대해 실행당 한 번만 읽어서 생성하는 모든 liberty에 동일하게 재사용한다.

    Returns: 위 new_lut_sections()가 정의하는 형태의 dict.
    """
    result = new_lut_sections()

    with open(pdk_path, "r", encoding="utf-8", errors="replace") as f:
        it = iter(f)
        looking_for_primitive = False

        for line in it:
            token = _first_token(line)

            if not result["dff_found"]:
                if token != "cell":
                    continue
                cell_name_here = _paren_content(line)
                if cell_name_here and len(result["cell_names_seen"]) < _MAX_CELL_NAMES_TRACKED:
                    result["cell_names_seen"].append(cell_name_here)
                if cell_name_here == dff_cell_name:
                    result["dff_found"] = True
                    looking_for_primitive = True
                continue

            if looking_for_primitive and lut_table_name and lut_table_name in line:
                result["primitive_found"] = True
                idx1, idx2 = _capture_index_lines(it, line)
                result["index_1_line"] = idx1
                result["index_2_line"] = idx2
                # index_1/index_2를 찾았으니(또는 못 찾았어도) 이 파일에서 필요한
                # 마지막 정보였으므로 여기서 스트리밍을 멈춘다.
                break

    return result
