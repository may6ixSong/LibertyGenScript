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
     `library (...) {` 줄부터 **첫 `cell (...)` 선언 직전까지만** 읽고, cell 선언을
     만나는 즉시 읽기를 멈춘다 - 파일의 압도적인 대부분(cell 본문 수십만 줄)은 아예
     읽지 않는다. 이 구간에서 가져오는 것은 body_lines 하나뿐이다:
       body_lines: **library{} 직속(중괄호 깊이 1)의 한 줄짜리 선언 중 첫 토큰이
           `_BODY_KEEP_PREFIXES`로 시작하는 줄만** (나머지는 전부 버림):
           - `define`(`define_group` 포함) / `delay_model` / `default` / `input_` /
             `output_` / `slew_` / `nom_`
           - `voltage_unit` / `current_unit` / `leakage_power_unit` /
             `capacitive_load_unit` / `library_features` / `time_unit` /
             `pulling_resistance_unit` / `in_place_swap_mode`
         접두어(시작 문자열) 기준이라 정확히 일치가 아니어도 잡힌다(예: `nom_`은
         nom_voltage/nom_temperature/nom_process를 모두 잡음). 단 `{`가 있는 줄(그룹을
         여는 줄)과 `_BODY_SKIP_TOKENS`(우리가 직접 쓰는 default_operating_conditions)
         는 접두어가 맞아도 버린다.
     input_voltage / output_voltage 블록은 읽지 않는다(2026-10 삭제 - block2에서 쓰지
     않아도 liberty 생성/.db 변환에 문제가 없음을 확인). `{`로 여는 그룹이므로 위 규칙에
     따라 블록 전체가 그냥 버려진다.
     판단은 원본 순서대로 한 줄씩 스캔하면서 그 자리에서 내리고, 살아남은 body_lines는
     PDK에 있던 순서 그대로 이어붙인다 - 별도로 재배열하지 않는다.

     PDK마다 형식이 제각각이라(2026-10 보강) 다음을 전제로 하지 않는다:
       - voltage_map의 존재/위치: 예전에는 body를 "첫 voltage_map 직전까지"로 읽어서
         voltage_map이 없는 PDK는 body 스캔이 cell 영역을 지나 파일 끝까지 내려갔다.
         이제는 voltage_map과 무관하게 cell 직전까지 한 번에 훑는다.
       - 그룹 내부 줄: 중괄호 깊이를 추적해서 library 직속 줄만 본다. 예전에는
         operating_conditions / lu_table_template / wire_load 같은 그룹 안의 줄이라도
         접두어만 맞으면 library 직속으로 끌려 나올 수 있었다.

  2. read_lut_table_sections(pdk_path, dff_cell_name, lut_table_name) - 실행당 한 번
     (block3용, worst case PDK 전용) cell 영역만 보므로 body_lines 같은 건 아예 모으지
     않고, index_1/index_2를 찾는 즉시 멈춘다.

결측 데이터 처리: 어떤 마커든 못 찾으면 예외를 던지지 않고 해당 필드를 비운 채
(None / 빈 리스트 / False) 반환한다. 실제 "결측 표시" 주석/토큰은 이 값들을 사용하는
block2_writer.py / block3_writer.py에서 작성한다.
"""

from __future__ import annotations

import re

# library 선언 ~ 첫 cell 선언 사이의 library 직속 줄 중 실제로 가져올 줄의 첫 토큰이 이 중
# 하나로 *시작*하면 포함한다(정확히 일치가 아니라 prefix 기준 - 예: "nom_"은 nom_voltage/
# nom_temperature/nom_process를 전부 잡는다). 2026-08 사용자 지정. 이 목록에 없으면
# (date/revision/comment 포함, PDK마다 뭐가 더 있을지 모르는 그 외 전부) 버린다.
_BODY_KEEP_PREFIXES = (
    "define",  # define(...) / define_group(...) - define_group도 "define"으로 시작
    "delay_model",
    "default",  # default_max_transition, default_fanout_load, ...
    "voltage_unit",
    "current_unit",
    "leakage_power_unit",
    "capacitive_load_unit",
    "library_features",
    "time_unit",
    "pulling_resistance_unit",
    "in_place_swap_mode",
    "input_",  # input_threshold_pct_rise, input_threshold_pct_fall, ...
    "output_",  # output_threshold_pct_rise, output_threshold_pct_fall, ...
    "slew_",  # slew_derate_from_library, slew_lower_threshold_pct_rise, ...
    "nom_",  # nom_process, nom_voltage, nom_temperature
)
# 접두어가 맞아도 버리는 토큰(정확히 일치). default_operating_conditions는 block2가
# Step2 값으로 직접 쓰고, 그 대상인 PDK의 operating_conditions 그룹은 가져오지 않으므로
# PDK 원본을 옮기면 중복 선언 + 존재하지 않는 operating_conditions를 가리키게 된다.
_BODY_SKIP_TOKENS = {"default_operating_conditions"}
_PAREN_CONTENT_PATTERN = re.compile(r"\(([^)]*)\)")


def _should_keep_body_line(token: str, line: str) -> bool:
    """
    library 직속(중괄호 깊이 1)의 한 줄을 body_lines로 가져올지 판단한다 (깊이 판단은
    호출 측). `_BODY_KEEP_PREFIXES` 중 하나로 시작하는 토큰만 대상이고, 그 중에서도
    그룹을 여는 줄(`{`가 있는 줄)과 `_BODY_SKIP_TOKENS`는 제외한다 - 여기서 가져오는 건
    전부 한 줄짜리 선언이라는 전제이므로, 혹시라도 여러 줄짜리 그룹의 첫 줄만 집으면
    닫는 `}`가 없어 전체 중괄호 균형이 깨진다.
    """
    if "{" in line or token in _BODY_SKIP_TOKENS:
        return False
    return token.startswith(_BODY_KEEP_PREFIXES)


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
    }


def read_pdk_library_sections(pdk_path: str) -> dict:
    """
    block2 작성에 필요한 것만 뽑아낸다 (library 선언 / library 직속의
    _BODY_KEEP_PREFIXES로 시작하는 한 줄 선언들). 이 값들은 전부 첫 `cell (...)` 선언 앞에 있으므로, 첫 cell 선언을 만나는 즉시 읽기를
    멈춘다. 자세한 기준은 모듈 docstring 참고.

    Returns: 위 new_library_sections()가 정의하는 형태의 dict.
    """
    result = new_library_sections()

    with open(pdk_path, "r", encoding="utf-8", errors="replace") as f:
        it = iter(f)

        # 1단계: `library (...) {` 줄을 찾을 때까지 건너뛴다
        depth = 0
        for line in it:
            if _first_token(line) == "library":
                result["found_library_decl"] = True
                # '{'가 다음 줄에 따로 있는 형식이면 0으로 시작해 그 줄에서 1이 된다.
                depth = line.count("{") - line.count("}")
                break
        if not result["found_library_decl"]:
            return result

        # 2단계: 첫 cell 선언 직전까지 한 번에 훑는다. library 직속(depth == 1) 줄만
        # 보고, 그룹 안쪽 줄(operating_conditions/lu_table_template/wire_load 등의 내용)은
        # 깊이만 추적하고 버린다. indent는 우리가 항상 2칸 기준으로 새로 입힐 것이므로
        # PDK 원본의 들여쓰기는 버리고 내용(텍스트)만 strip해서 저장한다.
        for line in it:
            token = _first_token(line)

            # cell 영역이 시작되면 block2에 필요한 건 전부 지나간 것이므로 즉시 중단.
            # PDK 파일의 대부분(수십만 줄)이 여기부터이므로, 이 조기 중단이 성능의
            # 핵심이다.
            if token == "cell" and "(" in line:
                break

            if depth == 1:
                # PDK 자체의 voltage_map 줄은 가져오지 않는다 - block2가 Step2/Step3
                # 값으로 직접 쓴다. 존재 여부만 진단용으로 남긴다.
                if token == "voltage_map":
                    result["found_voltage_map"] = True
                elif _should_keep_body_line(token, line):
                    stripped = line.strip()
                    if stripped:
                        result["body_lines"].append(stripped)

            depth += line.count("{") - line.count("}")

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


def parse_index_values(index_line: str | None) -> list[float]:
    """index 줄의 괄호 안 숫자를 전부 float 리스트로 뽑는다 (없으면 빈 리스트)."""
    if not index_line:
        return []
    start = index_line.find("(")
    end = index_line.rfind(")")
    body = index_line[start + 1: end] if start != -1 and end > start else index_line
    return [float(m) for m in _INDEX_VALUE_PATTERN.findall(body)]


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
