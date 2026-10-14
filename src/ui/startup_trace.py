"""
startup_trace.py

앱 시작이 어디서 멈추는지 진단하기 위한 도구 (2026-10 추가). PyQt를 import하지
않으므로 main.py 맨 앞에서 가장 먼저 불러도 된다.

배경: HPC에서 src를 바꾼 직후 run_generator.sh로 실행하면 창이 안 뜨고 멈춰 있다가,
강제 종료 후 다시 실행하면 뜨는 현상이 있었다. 재현 환경이 사내망뿐이라 어디서
멈추는지를 로그로 남기게 했다:
  - mark(): 시작 단계마다 "[startup HH:MM:SS.mmm +경과초] ..." 한 줄을 stderr(백그라운드
    실행이면 logs/run_generator.log)에 남긴다. 마지막으로 찍힌 줄 다음 단계에서 멈춘 것.
  - install(): faulthandler를 켜고 SIGUSR1에 "모든 스레드의 현재 파이썬 스택 덤프"를
    걸어 둔다. 멈춘 프로세스에 `kill -USR1 <PID>`(또는 run_generator.sh --dump)를 보내면
    그 순간 어느 파일 몇 번째 줄에서 기다리고 있는지가 로그에 찍힌다. C 레벨 시그널
    핸들러라 메인 스레드가 X11/NFS 호출 안에서 막혀 있어도 동작한다.
  - notify_ready(): 창이 실제로 화면에 뜬 뒤(이벤트 루프 첫 tick) 환경변수
    GENERATOR_READY_FILE이 가리키는 파일을 만든다. run_generator.sh가 이 파일로 "창이
    떴는지"를 판단한다(프로세스가 살아 있는 것만으로는 창이 떴는지 알 수 없으므로).
"""

import faulthandler
import os
import signal
import sys
import time

_T0 = time.time()


def mark(message: str) -> None:
    now = time.time()
    stamp = time.strftime("%H:%M:%S", time.localtime(now)) + ".%03d" % int((now % 1) * 1000)
    try:
        sys.stderr.write("[startup %s +%.2fs] %s\n" % (stamp, now - _T0, message))
        sys.stderr.flush()
    except Exception:
        pass


def install() -> None:
    try:
        faulthandler.enable(file=sys.stderr, all_threads=True)
        if hasattr(signal, "SIGUSR1"):
            faulthandler.register(signal.SIGUSR1, file=sys.stderr, all_threads=True, chain=False)
    except Exception:
        # 진단 도구가 앱 실행 자체를 막으면 안 된다.
        pass
    mark("python started (pid %d, %s)" % (os.getpid(), sys.executable))


def notify_ready() -> None:
    mark("window shown - startup complete")
    path = os.environ.get("GENERATOR_READY_FILE", "")
    if not path:
        return
    try:
        with open(path, "w") as handle:
            handle.write("%d\n" % os.getpid())
    except OSError:
        pass
