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
#
# 2026-10: 기본은 백그라운드 실행 - 터미널을 바로 돌려준다(터미널 창 하나로 다른 작업을
# 계속할 수 있도록). 앱 출력은 터미널 대신 logs/run_generator.log로 간다.
#   ./run_generator.sh            이미 떠 있는 앱이 있으면 먼저 종료하고, 새로 백그라운드 실행
#   ./run_generator.sh --stop     떠 있는 앱을 강제 종료만 한다
#   ./run_generator.sh --status   떠 있는지/PID 확인
#   ./run_generator.sh --fg       예전처럼 포그라운드 실행(터미널 Ctrl+C로 종료 가능)
# 백그라운드 실행 중에는 그 터미널의 Ctrl+C가 앱에 전달되지 않는다 - 대신 --stop을 쓴다.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MAIN_SCRIPT="$SCRIPT_DIR/src/main.py"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/run_generator.log"
PID_FILE="$LOG_DIR/run_generator.pid"

# ---------------------------------------------------------------------------
# 실행 중인 앱 찾기 / 종료
# ---------------------------------------------------------------------------

# PID 파일의 프로세스가 아직 살아 있고, 정말 이 앱(src/main.py)인지 확인한다 - PID가
# 재사용돼 엉뚱한 프로세스를 죽이는 일이 없도록. 맞으면 PID를 출력한다.
running_pid() {
    [ -f "$PID_FILE" ] || return 1
    pid="$(cat "$PID_FILE" 2>/dev/null)"
    case "$pid" in ''|*[!0-9]*) return 1 ;; esac
    kill -0 "$pid" 2>/dev/null || return 1
    ps -p "$pid" -o args= 2>/dev/null | grep -qF "$MAIN_SCRIPT" || return 1
    echo "$pid"
}

# 정상 종료(TERM)를 먼저 보내고, 3초 안에 안 꺼지면 강제 종료(KILL)한다. 앱은 setsid로
# 자기 프로세스 그룹의 리더로 떠 있으므로 그룹 전체(앱이 띄운 하위 프로세스 포함)에 보낸다.
stop_app() {
    pid="$(running_pid)" || { echo "[run_generator] not running."; rm -f "$PID_FILE"; return 0; }
    echo "[run_generator] stopping running app (PID $pid)..."
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
    i=0
    while [ $i -lt 30 ] && kill -0 "$pid" 2>/dev/null; do
        sleep 0.1
        i=$((i + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
        echo "[run_generator] not responding - force killing (PID $pid)."
        kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
        sleep 0.2
    fi
    rm -f "$PID_FILE"
    echo "[run_generator] stopped."
}

MODE="bg"
case "$1" in
    --stop)
        stop_app
        exit 0
        ;;
    --status)
        if pid="$(running_pid)"; then
            echo "[run_generator] running (PID $pid). Log: $LOG_FILE"
        else
            echo "[run_generator] not running."
        fi
        exit 0
        ;;
    --fg)
        MODE="fg"
        shift
        ;;
esac

# ---------------------------------------------------------------------------
# python 찾기
# ---------------------------------------------------------------------------

# PyQt5가 설치된 Anaconda python 후보 경로들 (필요시 이 목록에 사내 경로 추가).
# 환경변수 GENERATOR_PYTHON에 python 경로를 주면 그걸 가장 먼저 쓴다.
CANDIDATES="
${GENERATOR_PYTHON}
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

# ---------------------------------------------------------------------------
# 실행 - 이미 떠 있는 앱이 있으면 먼저 종료한다(같은 config 파일을 두 창이 동시에
# 고치지 않도록).
# ---------------------------------------------------------------------------
mkdir -p "$LOG_DIR"
if running_pid >/dev/null; then
    stop_app
fi

if [ "$MODE" = "fg" ]; then
    echo "$$" > "$PID_FILE"
    exec "$PYTHON_BIN" "$MAIN_SCRIPT" "$@"
fi

{
    echo ""
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') start ====="
} >> "$LOG_FILE"

# setsid: 터미널과 분리된 새 세션/프로세스 그룹으로 띄운다(터미널을 닫아도 계속 실행,
# --stop 때 그룹 전체를 종료할 수 있음). setsid가 없는 환경이면 nohup만 쓴다.
if command -v setsid >/dev/null 2>&1; then
    nohup setsid "$PYTHON_BIN" "$MAIN_SCRIPT" "$@" >> "$LOG_FILE" 2>&1 < /dev/null &
else
    nohup "$PYTHON_BIN" "$MAIN_SCRIPT" "$@" >> "$LOG_FILE" 2>&1 < /dev/null &
fi
APP_PID=$!
echo "$APP_PID" > "$PID_FILE"

# 시작 직후 바로 죽는 경우($DISPLAY 없음, Qt 플러그인/라이브러리 오류 등)는 터미널에 바로
# 알려준다. PyQt import에 1~2초 걸리므로 최대 3초까지 지켜본다.
i=0
while [ $i -lt 30 ] && kill -0 "$APP_PID" 2>/dev/null; do
    sleep 0.1
    i=$((i + 1))
done
if kill -0 "$APP_PID" 2>/dev/null; then
    echo "[run_generator] started in background (PID $APP_PID)."
    echo "  log : $LOG_FILE"
    echo "  stop: $0 --stop"
else
    rm -f "$PID_FILE"
    echo "[오류] 앱이 시작 직후 종료되었습니다. 로그 마지막 부분:"
    tail -n 20 "$LOG_FILE"
    exit 1
fi
