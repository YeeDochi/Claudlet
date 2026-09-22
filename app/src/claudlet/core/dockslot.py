"""도크 자리(슬롯)를 펫끼리 겹치지 않게 나눠 갖는 프로세스 간 조율.

펫은 세션마다 독립 프로세스라 서로의 존재를 모른다. 런타임 디렉터리의 잠금 파일
``claudlet-dock-<N>.slot``을 0번부터 배타 잠금으로 집어보고, 처음 잡히는 N이 그
펫의 자리다.

잠금(파일에 pid를 적는 방식이 아니라)인 이유: 프로세스가 죽으면 OS가 잠금을
자동으로 풀어주므로, 강제 종료나 크래시가 남긴 유령 자리도 다음 펫이 그대로
회수한다. pid 파일이면 스스로 정리하지 못한 자리가 영영 비어 있게 된다.

pet.py는 여기에 더해 주기적으로 `claim_lower`를 호출한다 — 앞자리 펫이 종료해
생긴 구멍을 뒷펫이 메워서 대열이 다시 촘촘해진다.
"""
import os

from claudlet.core import hostinfo

MAX_SLOTS = 64          # 이 이상은 어차피 화면에 안 들어간다(dock이 줄을 접는다)


def slot_path(n):
    """슬롯 n의 잠금 파일 경로."""
    return os.path.join(hostinfo.runtime_dir(), "claudlet-dock-%d.slot" % n)


def lock_exclusive_nonblocking(fd):
    """플랫폼별 비차단 배타 잠금: POSIX는 fcntl.flock, Windows는 msvcrt.locking."""
    if os.name == "posix":
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:
        import msvcrt
        os.write(fd, b"\0")           # msvcrt.locking은 잠글 바이트가 있어야 한다
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)


def try_claim(n):
    """슬롯 n을 잡으면 열린 fd, 이미 다른 펫이 쓰고 있으면 None.

    잠금은 fd가 살아 있는 동안만 유지되므로 호출자가 fd를 붙들고 있어야 한다."""
    try:
        fd = os.open(slot_path(n), os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return None                   # 런타임 디렉터리가 없거나 권한 없음
    try:
        lock_exclusive_nonblocking(fd)
    except OSError:
        os.close(fd)
        return None
    return fd


def claim(start=0, max_slots=MAX_SLOTS):
    """`start`번부터 위로 훑어 첫 빈 슬롯을 잡는다 -> (slot, fd) 또는 (None, None)."""
    for n in range(start, max_slots):
        fd = try_claim(n)
        if fd is not None:
            return n, fd
    return None, None


def claim_lower(current, max_slots=MAX_SLOTS):
    """`current`보다 앞에 빈 자리가 있으면 잡아서 (slot, fd), 없으면 (None, None).

    호출자는 새 슬롯을 받은 뒤에만 옛 fd를 release해야 한다 — 먼저 놓으면 그 틈에
    다른 펫이 가로채 두 마리가 같은 자리에 설 수 있다."""
    if current is None:
        return claim(0, max_slots)
    for n in range(0, min(int(current), max_slots)):
        fd = try_claim(n)
        if fd is not None:
            return n, fd
    return None, None


def release(fd):
    """슬롯 반납(fd를 닫으면 잠금도 풀린다). 이미 닫혔으면 조용히 무시."""
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass
