#!/bin/sh
# build_exe.sh
#
# generator를 python 없이 바로 실행 가능한 단일 실행파일로 빌드.
# (이 스크립트 자체는 빌드할 때 한 번만 필요하고, 빌드된 실행파일은
#  이 Anaconda 환경 없이도 독립적으로 동작함)
#
# 사전 조건: Anaconda Python 3.7.6 에 PyQt5, PyInstaller가 이미 설치되어 있어야 함
#   (python3 -m pip list 로 확인 가능)
#
# 사용법: ./build_exe.sh   (또는 sh build_exe.sh)

ANACONDA_PYTHON="/appl/CAEutil/LINUX/local/Anaconda/Anaconda3.7/bin/python3"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -x "$ANACONDA_PYTHON" ]; then
    echo "[오류] $ANACONDA_PYTHON 을 찾을 수 없습니다."
    echo "  Anaconda 경로가 다르다면 이 스크립트의 ANACONDA_PYTHON 값을 수정해주세요."
    exit 1
fi

# Anaconda 자체 공유 라이브러리(Qt5 포함)를 우선 찾도록 설정
export LD_LIBRARY_PATH="/appl/CAEutil/LINUX/local/Anaconda/Anaconda3.7/lib:$LD_LIBRARY_PATH"

cd "$SCRIPT_DIR/src" || exit 1

"$ANACONDA_PYTHON" -m PyInstaller \
    --onefile \
    --name liberty_generator \
    --distpath "$SCRIPT_DIR/dist" \
    --workpath "$SCRIPT_DIR/build" \
    --specpath "$SCRIPT_DIR/build" \
    main.py

status=$?
if [ $status -ne 0 ]; then
    echo "[오류] 빌드 실패 (exit code: $status). 위 로그를 확인해주세요."
    exit $status
fi

echo ""
echo "빌드 완료: $SCRIPT_DIR/dist/liberty_generator"
echo "이 실행파일 하나만 있으면 python/pip 없이 어디서든 바로 실행 가능합니다."
echo "(실행 시 옆에 config/, output/ 폴더가 자동으로 생성됩니다)"