#!/bin/sh
# build_exe.sh
#
# generator를 python 없이 바로 실행 가능한 형태로 빌드한다.
# 결과물은 dist/liberty_generator/ 폴더 하나이고, 그 안에 실행파일과 필요한
# 라이브러리가 전부 들어있다. 이 폴더째로 복사해주면 받는 쪽은 Anaconda도
# python도 없이 폴더 안의 liberty_generator 를 실행하기만 하면 된다.
#
# (예전에는 --onefile로 단일 실행파일을 만들었지만, 수백 MB를 매번 통째로
#  압축하느라 빌드가 오래 걸리고 실행할 때마다 /tmp에 다시 푸느라 시작도
#  느려서 --onedir 폴더 배포로 바꿨다.)
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

# --noconfirm 때문에 PyInstaller가 dist/liberty_generator/ 를 통째로 지우고 다시 만든다.
# 그 폴더에서 앱을 실행해봤다면 config/ 에 설정이 들어있으므로, 빌드 전에 옆으로
# 빼뒀다가 빌드 후 되돌려놓는다. (output/ 은 매 실행마다 새로 채워지므로 그냥 버림)
DIST_APP_DIR="$SCRIPT_DIR/dist/liberty_generator"
CONFIG_BACKUP="$SCRIPT_DIR/dist/.liberty_generator_config_backup"

rm -rf "$CONFIG_BACKUP"
if [ -d "$DIST_APP_DIR/config" ]; then
    echo "[안내] 기존 $DIST_APP_DIR/config 를 임시 보관합니다 (빌드 후 복원)."
    mv "$DIST_APP_DIR/config" "$CONFIG_BACKUP" || exit 1
fi

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

# 이 앱이 실제로 쓰는 서드파티는 PyQt5(QtCore/QtGui/QtWidgets), openpyxl, xlrd 뿐인데,
# Anaconda에는 numpy/scipy/pandas/matplotlib/mkl 등이 전부 깔려 있다. exclude를 안 주면
# PyInstaller가 이것들까지 의존성 그래프에 끌고 들어와서 분석/수집 시간이 몇 배로 늘어난다.
# (위 setrecursionlimit을 올려야 했던 것도 그래프가 그만큼 비대하기 때문)
# 빌드된 실행파일이 'No module named XXX'로 죽는다면, 그 모듈만 아래 목록에서 빼면 된다.
EXCLUDES = [
    # 수치/과학 스택 (이 앱은 안 씀. mkl 때문에 용량이 특히 큼)
    'numpy', 'scipy', 'pandas', 'matplotlib', 'numba', 'sympy', 'sklearn',
    'h5py', 'tables', 'bottleneck', 'numexpr',
    # 노트북/개발 도구
    'IPython', 'ipykernel', 'jupyter', 'notebook', 'nbconvert', 'nbformat',
    'zmq', 'tornado', 'jedi', 'pygments', 'sphinx', 'pytest',
    # 다른 GUI 툴킷
    'tkinter', 'Tkinter', 'wx', 'gtk',
    # openpyxl이 이미지 처리에 optional하게 쓰지만 우리는 셀 값만 읽으므로 불필요.
    # (혹시 xlsx 읽기에서 문제가 생기면 이 줄부터 지워볼 것)
    'PIL', 'Pillow',
    # 이 앱이 import하지 않는 PyQt5 서브모듈. 파이썬 바인딩만 빠지고,
    # Qt 본체가 링크한 .so는 바이너리 의존성 분석으로 여전히 따라오므로 안전하다.
    'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore', 'PyQt5.QtWebEngine',
    'PyQt5.QtWebKit', 'PyQt5.QtWebKitWidgets', 'PyQt5.QtQml', 'PyQt5.QtQuick',
    'PyQt5.QtQuickWidgets', 'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets',
    'PyQt5.QtBluetooth', 'PyQt5.QtNfc', 'PyQt5.QtPositioning', 'PyQt5.QtLocation',
    'PyQt5.QtSql', 'PyQt5.QtTest', 'PyQt5.QtDesigner', 'PyQt5.QtHelp',
    'PyQt5.QtOpenGL', 'PyQt5.QtSerialPort', 'PyQt5.QtXmlPatterns',
]

sys.argv = [
    'pyinstaller',
    # --onefile은 수집한 수백 MB를 단일 스레드 zlib으로 통째로 압축하느라 빌드 시간의
    # 상당 부분을 잡아먹고, 실행할 때마다 /tmp에 다시 푸느라 앱 시작도 느리다.
    # --onedir은 폴더째 배포해야 하는 대신 빌드도 실행도 훨씬 빠르다.
    '--onedir',
    # dist/liberty_generator/ 가 이미 있어도 물어보지 않고 덮어쓴다.
    # (이게 없으면 PyInstaller가 y/N 프롬프트에서 멈춘다)
    '--noconfirm',
    # upx가 PATH에 있으면 바이너리마다 UPX 압축이 걸려 매우 느려진다
    '--noupx',
    '--name', 'liberty_generator',
    '--distpath', '$SCRIPT_DIR/dist',
    '--workpath', '$SCRIPT_DIR/build',
    '--specpath', '$SCRIPT_DIR/build',
]
for _mod in EXCLUDES:
    sys.argv += ['--exclude-module', _mod]
sys.argv.append('main.py')

from PyInstaller.__main__ import run
run()
"

status=$?

# 빌드 성공/실패와 무관하게, 빼뒀던 config는 되돌려놓는다.
if [ -d "$CONFIG_BACKUP" ]; then
    if [ -d "$DIST_APP_DIR" ] && [ ! -d "$DIST_APP_DIR/config" ]; then
        mv "$CONFIG_BACKUP" "$DIST_APP_DIR/config"
        echo "[안내] 임시 보관했던 config/ 를 복원했습니다."
    else
        echo "[안내] 임시 보관한 config/ 는 $CONFIG_BACKUP 에 남아있습니다."
    fi
fi

if [ $status -ne 0 ]; then
    echo "[오류] 빌드 실패 (exit code: $status). 위 로그를 확인해주세요."
    exit $status
fi

echo ""
echo "빌드 완료: $DIST_APP_DIR/"
echo ""
echo "이 폴더 '전체'를 복사해서 배포하면 됩니다. 받는 쪽은 python/PyQt5 없이"
echo "폴더 안의 liberty_generator 를 실행하기만 하면 됩니다:"
echo "    ./liberty_generator"
echo ""
echo "실행하면 그 폴더 안에 config/, output/ 이 자동으로 생성됩니다."
echo "폴더 안의 다른 파일들은 실행에 필요한 라이브러리이니 지우거나 옮기지 마세요."
echo ""
echo "묶어서 전달하려면:"
echo "    tar czf liberty_generator.tar.gz -C \"$SCRIPT_DIR/dist\" liberty_generator"