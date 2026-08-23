"""
mt0_reader.py

DBS output(.mt0) 시뮬레이션 결과 파일을 파싱해서 block5의 cell_rise/cell_fall/
rise_transition/fall_transition 테이블에 쓸 tplh/tphl/tr/tf 값을 뽑아낸다.

파일 구조(HSPICE .mt0 스타일 measure 결과):
  - 상단에 $DATA1/.TITLE 같은 메타 줄
  - 그 다음 컬럼명이 여러 줄에 걸쳐 나열됨(줄바꿈 위치는 데이터 줄과 동일한 폭으로
    wrap됨). 예: "index slope cload tplh" / "tphl tr tf temper" / "alter#"
  - 그 다음부터 데이터가 같은 폭으로 반복됨.

컬럼 순서를 코드에 하드코딩하지 않고, 실제 헤더에서 동적으로(이름 기준으로, 대소문자
무관) 읽어 tplh/tphl/tr/tf를 찾는다 - 설계에 따라 컬럼 순서/개수가 달라질 수 있기
때문에, 헤더의 줄바꿈 폭(width)을 그대로 데이터의 레코드 폭으로 사용해서 순서
상관없이 토큰을 헤더 폭만큼 묶는다.

값 변환(2026-08 확정): DBS output에서 읽은 원본 값(초 단위)에 *1e9(초 -> 나노초)를
적용하고 소수점 5자리로 반올림해서 출력한다.

표의 행/열 크기(2026-08 수정 - PDK/DK 의존성 제거): 이전에는 PDK/DK 파일의
lu_table_template index_1/index_2 개수를 빌려썼는데, DBS output signal 매치 pin의
timing 값은 순전히 DBS output(.mt0) 파일에서만 오는 것이라 PDK/DK 파일을 참조할
이유가 없다는 피드백을 받아, .mt0 파일 자체의 'slope'/'cload' 컬럼 값만 보고
행/열 개수를 추론하도록(derive_table_shape) 바꿨다 - PDK/DK 파일과 완전히 무관하다.

가정(실제 데이터로 검증 필요 - 다르면 바로 맞춰서 고칠 수 있음): 값의 순서는
slope 값이 가장 바깥 루프, cload 값이 안쪽 루프로 반복된다고 가정하고 2차원 표로
재구성한다(HSPICE .STEP/.ALTER의 일반적인 스윕 순서 - row-major).

2026-08 수정: build_timing_table()이 실패 시 그냥 None만 반환하던 것을, "왜" 실패
했는지(컬럼을 못 찾음 / 값 개수가 예상과 다름 / 파일을 못 읽음 등) 구체적인 이유
문자열과 함께 반환하도록 바꿨다 - block5_writer.py가 이 이유를 생성된 liberty 파일의
주석에 그대로 적어서, 실제로 왜 결측 처리됐는지 파일을 열어보는 즉시 알 수 있게 한다.
"""

from __future__ import annotations


def _looks_like_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def read_mt0_columns(mt0_path: str) -> dict:
    """
    .mt0 파일을 파싱해서 컬럼명 목록과, 각 행을 {컬럼명: 원본 텍스트 값} 딕셔너리로
    담은 리스트를 반환한다.

    Returns:
        {"columns": [str, ...], "rows": [{col_name: raw_text_value, ...}, ...]}
        파싱 실패(파일이 없거나 헤더를 못 찾음 등)하면 {"columns": [], "rows": []}
        (예외를 던지지 않음).
    """
    header_tokens: list[str] = []
    data_tokens: list[str] = []
    header_done = False

    try:
        with open(mt0_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("$") or stripped.startswith("."):
                    continue  # $DATA1 ... / .TITLE ... 같은 메타 줄은 건너뜀

                parts = stripped.split()
                is_numeric_line = all(_looks_like_number(p) for p in parts)

                if not header_done:
                    if is_numeric_line:
                        header_done = True
                    else:
                        header_tokens.extend(parts)
                        continue

                if is_numeric_line:
                    data_tokens.extend(parts)
    except OSError:
        return {"columns": [], "rows": []}

    if not header_tokens:
        return {"columns": [], "rows": []}

    width = len(header_tokens)
    rows: list[dict] = []
    for i in range(0, len(data_tokens) - width + 1, width):
        group = data_tokens[i:i + width]
        if len(group) < width:
            break
        rows.append(dict(zip(header_tokens, group)))

    return {"columns": header_tokens, "rows": rows}


def _distinct_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            ordered.append(v)
    return ordered


# .mt0 파일 자체에서 표의 행/열 축으로 쓸 컬럼명 (2026-08 확정 - 사용자가 준 예시
# 파일 구조의 실제 컬럼명 그대로: slope가 바깥 루프/행, cload가 안쪽 루프/열).
ROW_AXIS_COLUMN = "slope"
COL_AXIS_COLUMN = "cload"


def derive_table_shape(
    mt0_path: str, row_axis_column: str = ROW_AXIS_COLUMN, col_axis_column: str = COL_AXIS_COLUMN,
) -> tuple[int | None, int | None, str | None]:
    """
    PDK/DK 파일과 무관하게, .mt0 파일 자체의 row_axis_column(기본 'slope')/
    col_axis_column(기본 'cload') 컬럼 값만 보고 표의 행/열 개수를 추론한다.
    (2026-08 수정: 예전에는 PDK/DK 파일의 lu_table_template index_1/index_2 개수를
    빌려썼는데, DBS output signal 매치 pin의 timing 값은 순전히 DBS output(.mt0)
    파일에서만 오는 것이므로 PDK/DK 파일을 참조할 필요가 없다는 피드백을 반영해
    PDK 의존성을 완전히 제거했다.)

    row_count = row_axis_column의 서로 다른 값 개수(파일에 등장한 순서 기준).
    col_count = 전체 레코드 수 / row_count (딱 나누어떨어져야 함).

    Returns:
        (row_count, col_count, error) - 실패하면 (None, None, 이유 문자열).
    """
    parsed = read_mt0_columns(mt0_path)
    if not parsed["columns"]:
        return None, None, f"could not parse a header from '{mt0_path}' (file missing or empty?)"

    normalized_lookup = {c.strip().lower(): c for c in parsed["columns"]}
    row_key = normalized_lookup.get(row_axis_column.strip().lower())
    col_key = normalized_lookup.get(col_axis_column.strip().lower())
    if row_key is None or col_key is None:
        missing = [n for n, k in [(row_axis_column, row_key), (col_axis_column, col_key)] if k is None]
        found = ", ".join(parsed["columns"])
        return None, None, f"axis column(s) not found in DBS output header: {', '.join(missing)} (found: {found})"

    total_records = len(parsed["rows"])
    if total_records == 0:
        return None, None, "DBS output has a header but no data records"

    row_count = len(_distinct_ordered([row[row_key] for row in parsed["rows"]]))
    if row_count == 0 or total_records % row_count != 0:
        return None, None, (
            f"{total_records} records could not be evenly divided by {row_count} "
            f"distinct '{row_axis_column}' values"
        )
    col_count = total_records // row_count
    return row_count, col_count, None


def build_timing_table(
    mt0_path: str, column_name: str, row_count: int, col_count: int,
) -> tuple[list[list[str]] | None, str | None]:
    """
    .mt0 파일에서 column_name(tplh/tphl/tr/tf 등) 값을 순서대로 뽑아 *100 후 소수점
    5자리로 반올림해서 row_count x col_count 2차원 표로 재구성한다.

    실패해도 예외를 던지지 않고, 대신 "왜" 실패했는지 구체적인 이유를 함께 반환한다
    (block5_writer.py가 이 이유를 생성된 liberty 파일의 주석에 그대로 적음).

    Returns:
        (table, error) - 성공하면 (표, None), 실패하면 (None, 실패 이유 문자열).
    """
    if not row_count or not col_count:
        return None, "row/column count is unknown (see index_1/index_2 above)"

    parsed = read_mt0_columns(mt0_path)
    if not parsed["columns"]:
        return None, f"could not parse a header from '{mt0_path}' (file missing or empty?)"

    # 컬럼명은 대소문자 무관하게 찾는다 (실제 DBS output 파일의 표기가 tplh/TPLH/Tplh
    # 등 다를 수 있으므로).
    normalized_lookup = {c.strip().lower(): c for c in parsed["columns"]}
    actual_key = normalized_lookup.get(column_name.strip().lower())
    if actual_key is None:
        found = ", ".join(parsed["columns"])
        return None, f"column '{column_name}' not found in DBS output header (found: {found})"

    raw_values = [row[actual_key] for row in parsed["rows"] if actual_key in row]
    expected = row_count * col_count
    if len(raw_values) != expected:
        return None, (
            f"expected {expected} values ({row_count} x {col_count}, from PDK/DK "
            f"index_1/index_2) but found {len(raw_values)} records in DBS output"
        )

    try:
        transformed = ["%0.5f" % (float(v) * 1e9) for v in raw_values]
    except ValueError as e:
        return None, f"non-numeric value in DBS output column '{column_name}': {e}"

    table = [transformed[r * col_count:(r + 1) * col_count] for r in range(row_count)]
    return table, None
