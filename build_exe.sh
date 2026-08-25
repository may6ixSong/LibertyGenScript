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

# PyInstaller가 Anaconda의 site-packages(패키지 수가 많음)에서 모듈 의존성 그래프를
# 재귀적으로 훑다가 파이썬 기본 재귀 한도(1000)를 넘는 경우가 있어("RecursionError:
# maximum recursion depth exceeded"), PyInstaller 공식 안내대로 재귀 한도를 올려서
# 실행한다. `-m PyInstaller ...`로 바로 실행하면 이 한도를 미리 못 올리므로,
# run()을 직접 호출하는 짧은 파이썬 코드로 감싼다.
"$ANACONDA_PYTHON" -c "
import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

# PyInstaller 4.2의 load_ldconfig_cache()가 'ldconfig -p' 출력 중 자기 정규식과 안
# 맞는 줄을 만나면(예: 이 서버의 glibc/ldconfig 출력 형식) None에 .groups()를 호출해서
# AttributeError로 죽는 버그가 있다(이후 PyInstaller 버전에서 고쳐짐). 원본 로직은
# 그대로 두고, 매칭 안 되는 줄만 건너뛰도록 patch한다.
try:
    import os
    import re
    import PyInstaller.depend.utils as _pi_utils
    from PyInstaller import compat as _pi_compat
    from PyInstaller.exceptions import ExecCommandFailed as _PIExecCommandFailed

    def _patched_load_ldconfig_cache():
        if _pi_utils.LDCONFIG_CACHE is not None:
            return

        from distutils.spawn import find_executable
        ldconfig = find_executable('ldconfig')
        if ldconfig is None:
            ldconfig = find_executable('ldconfig', '/usr/sbin:/sbin:/usr/bin:/usr/sbin')
            if ldconfig is None:
                _pi_utils.LDCONFIG_CACHE = {}
                return

        if _pi_compat.is_freebsd or _pi_compat.is_openbsd:
            ldconfig_arg = '-r'
            splitlines_count = 2
            pattern = re.compile(r'^\s+\d+:-l(\S+)(\s.*)? => (\S+)')
        else:
            ldconfig_arg = '-p'
            splitlines_count = 1
            pattern = re.compile(r'^\s+(\S+)(\s.*)? => (\S+)')

        try:
            text = _pi_compat.exec_command(ldconfig, ldconfig_arg)
        except _PIExecCommandFailed:
            _pi_utils.LDCONFIG_CACHE = {}
            return

        cache = {}
        for line in text.strip().splitlines()[splitlines_count:]:
            m = pattern.match(line)
            if m is None:
                continue
            path = m.groups()[-1]
            if _pi_compat.is_freebsd or _pi_compat.is_openbsd:
                bname = os.path.basename(path).split('.so', 1)[0]
                name = 'lib' + m.group(1)
                if not name.startswith(bname):
                    continue
                name = bname + '.so' + name[len(bname):]
            else:
                name = m.group(1)
            if name not in cache:
                cache[name] = path

        _pi_utils.LDCONFIG_CACHE = cache

    _pi_utils.load_ldconfig_cache = _patched_load_ldconfig_cache
except Exception as e:
    sys.stderr.write('[경고] ldconfig 파싱 우회 패치를 적용하지 못했습니다: %r\n' % (e,))

sys.argv = [
    'pyinstaller',
    '--onefile',
    '--name', 'liberty_generator',
    '--distpath', '$SCRIPT_DIR/dist',
    '--workpath', '$SCRIPT_DIR/build',
    '--specpath', '$SCRIPT_DIR/build',
    'main.py',
]
from PyInstaller.__main__ import run
run()
"

status=$?
if [ $status -ne 0 ]; then
    echo "[오류] 빌드 실패 (exit code: $status). 위 로그를 확인해주세요."
    exit $status
fi

echo ""
echo "빌드 완료: $SCRIPT_DIR/dist/liberty_generator"
echo "이 실행파일 하나만 있으면 python/pip 없이 어디서든 바로 실행 가능합니다."
echo "(실행 시 옆에 config/, output/ 폴더가 자동으로 생성됩니다)"