#!/bin/sh
# run_generator.sh
#
# generator 실행 진입점.
# - PyQt5는 Anaconda Python 3.7.6 에서만 사용 가능함이 확인됨.
#   ("python3.11" 등 다른 python 에는 PyQt5 없음)
# - "python3.11 src/main.py" 를 직접 타이핑할 필요 없이 이 스크립트만 실행하면 됨: ./run_generator.sh
# - Anaconda 설치 경로가 계정/서버마다 다를 수 있어, 여러 후보 경로를 순서대로 탐색함
# - 아무 것도 못 찾으면 명확한 에러 메시지를 출력하고 종료
#
# 실행권한 없이 "허가 거부"가 뜨는 경우 (noexec 마운트 등):
#   sh run_generator.sh   로 실행 가능 (실행권한 불필요)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MAIN_SCRIPT="$SCRIPT_DIR/src/main.py"

# PyQt5가 설치된 Anaconda python 후보 경로들 (필요시 이 목록에 사내 경로 추가)
CANDIDATES="
/appl/CAEutil/LINUX/local/Anaconda/Anaconda3.7/bin/python3
"

PYTHON_BIN=""

for candidate in $CANDIDATES; do
    if [ -x "$candidate" ]; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[오류] PyQt5가 설치된 Anaconda python 을 찾을 수 없습니다."
    echo "  아래 명령으로 직접 위치를 확인한 뒤,"
    echo "    find /appl -maxdepth 4 -iname 'Anaconda*' 2>/dev/null"
    echo "  이 스크립트(run_generator.sh)의 CANDIDATES 목록에 경로를 추가해주세요."
    exit 1
fi

# Anaconda 자체 공유 라이브러리를 우선 찾도록 설정 (Qt5 등)
export LD_LIBRARY_PATH="$(dirname "$(dirname "$PYTHON_BIN")")/lib:$LD_LIBRARY_PATH"

if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "[오류] $MAIN_SCRIPT 를 찾을 수 없습니다."
    echo "  generator 폴더 구조가 올바른지 확인해주세요 (src/main.py 필요)."
    exit 1
fi

exec "$PYTHON_BIN" "$MAIN_SCRIPT" "$@"

