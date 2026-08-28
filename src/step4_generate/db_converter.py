"""
db_converter.py

Step4에서 생성된 liberty(.lib) 파일들을 사내 EDA 배치 잡(lc_shell, lc_sub 래퍼)으로
넘겨 .db(바이너리) 파일로 변환한다. 원본 사내 스크립트 make_db.scr/run_make_db2가
하던 일(파일마다 read_lib -> write_lib -> remove_design -all 반복)을 liberty 파일명
개수만큼 그대로 재현해서 lc_sub에 넘긴다. .lib 파일은 변환 후에도 지우지 않는다 -
이 모듈은 .lib를 읽기만 하고 쓰거나 지우지 않는다.

lc_shell 자체는 로컬 PATH에 없다(라이선스/버전이 lc_sub이 제출하는 LSF 잡 안에서만
resolve됨, /appl/CAECR/scripts/lc_sub 참고) - 그래서 우리가 직접 실행하는 건 lc_sub
하나뿐이고, "lc_shell -f ./make_db.scr"는 그 잡 안에서 실행될 커맨드로 그대로 넘긴다.

GUI(Qt)에 의존하지 않는 순수 함수로 작성 - generate_view.py가 백그라운드 스레드에서
run_make_db()를 호출한다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

MAKE_DB_SCRIPT_NAME = "make_db.scr"
MAKE_DB_LOG_NAME = "make_db.log"

# `which lc_sub`는 되지만 `which lc_shell`은 안 되는 환경이 확인됨(lc_shell은 lc_sub이
# 제출하는 LSF 잡 안에서만 resolve됨) - lc_sub이 PATH에 없을 때의 fallback 경로.
_LC_SUB_FALLBACK_PATH = "/appl/CAECR/scripts/lc_sub"


def find_lc_sub() -> str:
    """lc_sub 실행 파일 경로를 찾는다. PATH에 없으면 알려진 사내 경로로 fallback."""
    found = shutil.which("lc_sub")
    if found:
        return found
    if Path(_LC_SUB_FALLBACK_PATH).exists():
        return _LC_SUB_FALLBACK_PATH
    raise FileNotFoundError(
        f"lc_sub not found on PATH or at {_LC_SUB_FALLBACK_PATH}"
    )


def build_make_db_script(library_names: list[str]) -> str:
    """
    library_names(확장자 없는 liberty base 이름 - .lib 파일명에서 .lib만 뺀 것이자
    그 안의 `library (...)` 선언 이름과 동일)로 make_db.scr 내용을 만든다.

    원본 사내 스크립트 패턴 그대로: 파일마다
        read_lib     ./{name}.lib
        write_lib    {name}  -o ./{name}.db
        remove_design -all
    세 줄 블록을 반복한다(파일마다 메모리를 비워야 다음 파일 처리 시 리소스 낭비/이름
    충돌이 없다).
    """
    lines = ["enable", ""]
    for name in library_names:
        lines.append(f"read_lib     ./{name}.lib")
        lines.append(f"write_lib                       {name}  \\")
        lines.append(f"          -o ./{name}.db")
        lines.append("remove_design -all")
        lines.append("")
    return "\n".join(lines)


def run_make_db(output_path: str, library_names: list[str]) -> tuple[int, str]:
    """
    output_path에 make_db.scr을 쓰고, `lc_sub -Is -64 lc_shell -f ./make_db.scr`을
    output_path를 cwd로 실행한다 - 스크립트의 read_lib/write_lib가 전부 상대경로(`./`)
    이므로 cwd가 liberty(.lib) 파일들이 있는 폴더와 같아야 한다.

    표준출력/에러는 output_path/make_db.log로 그대로 저장한다(원본 스크립트의
    `| tee ./make_db.log`와 같은 효과). 이 호출은 EDA 잡이 끝날 때까지 블로킹되므로
    반드시 백그라운드 스레드에서 불러야 한다(GUI 스레드에서 직접 부르면 창이 멈춘다).

    Returns:
        (returncode, log_path)
    """
    output_dir = Path(output_path)
    script_path = output_dir / MAKE_DB_SCRIPT_NAME
    log_path = output_dir / MAKE_DB_LOG_NAME

    script_path.write_text(build_make_db_script(library_names), encoding="utf-8")

    lc_sub = find_lc_sub()
    command = [lc_sub, "-Is", "-64", "lc_shell", "-f", f"./{MAKE_DB_SCRIPT_NAME}"]

    with open(log_path, "w", encoding="utf-8") as log_file:
        result = subprocess.run(
            command,
            cwd=str(output_dir),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    return result.returncode, str(log_path)
