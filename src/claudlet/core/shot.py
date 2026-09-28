"""포인터 스크린샷 폴백 — 글자를 못 읽은 창은 화면을 찍어 넘긴다.

포인터로 고른 순간 찍어 메모리에 둔다. 창 글자를 충분히 읽었으면 그 버퍼는
버리고(디스크에 안 남는다), 부족할 때만 runtime_dir 에 PNG 로 저장해 경로를
쪽지에 싣는다. 파일은 그 턴이 끝나면(turn_end) 지운다.

판단·좌표는 순수 함수, 파일 수명은 이름 규칙 하나(claudlet-<sid>-shot-<n>.png)로
묶어 glob 한 번에 지운다. 캡처 자체는 platform/screenshot.py.
"""
import glob
import os

from claudlet.core import hostinfo

# 창 제목·툴바 한두 줄만 읽혔다면 본문은 못 읽은 것이다. Chrome 기본 설정은
# 제목 1줄이 전부였다(2026-09-28 실측).
# ponytail: 줄 수 기준은 거칠다. 메뉴만 잔뜩 읽힌 창은 놓친다 — 걸리면
# "제목·앱 이름 외 줄 N 개 미만" 으로 좁힌다.
MIN_LINES = 3


def needs_image(ctx):
    """읽은 글자가 부족해 화면을 같이 보내야 하는가. 순수."""
    if ctx.get("open"):
        return False        # 편집기: 본문은 디스크에서 읽으라고 이미 알려준다
    return bool(ctx.get("note")) or ctx.get("lines", 0) < MIN_LINES


def crop_rect(rect, virt, shot_size):
    """가상 데스크톱 좌표의 사각형 -> 전체 화면 캡처 이미지 안의 픽셀 사각형.

    `virt` = (x, y, w, h) 가상 데스크톱, `shot_size` = (w, h) 캡처 이미지.
    HiDPI 면 이미지가 논리 좌표보다 크다 — 비율로 맞춘다. 화면 밖은 잘라내고,
    남는 게 없으면 None. 순수.
    """
    vx, vy, vw, vh = virt
    sw, sh = shot_size
    if vw <= 0 or vh <= 0:
        return None
    kx, ky = sw / float(vw), sh / float(vh)
    x0 = max(0, int(round((rect["x"] - vx) * kx)))
    y0 = max(0, int(round((rect["y"] - vy) * ky)))
    x1 = min(sw, int(round((rect["x"] + rect["w"] - vx) * kx)))
    y1 = min(sh, int(round((rect["y"] + rect["h"] - vy) * ky)))
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def _prefix(session_id):
    return os.path.join(hostinfo.runtime_dir(),
                        "claudlet-{}-shot-".format(session_id or "default"))


def save(session_id, png):
    """PNG 바이트를 이 세션의 새 캡처 파일로 쓴다(0600). 경로, 실패면 None."""
    base = _prefix(session_id)
    for n in range(1, 1000):
        path = "%s%d.png" % (base, n)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        except OSError:
            return None
        with os.fdopen(fd, "wb") as f:
            f.write(png)
        return path
    return None


def clear(session_id):
    """이 세션의 캡처를 전부 지운다. 지운 개수."""
    n = 0
    for path in glob.glob(glob.escape(_prefix(session_id)) + "*.png"):
        try:
            os.unlink(path)
            n += 1
        except OSError:
            pass
    return n


def allow_rule(directory):
    """Claude Code 가 이 폴더의 캡처를 권한 창 없이 Read 하게 하는 규칙. 순수.

    작업 폴더 밖 파일은 Read 가 권한을 묻는다(실측: -p 에서 거부, 대화형에선
    창이 뜬다). 절대 경로 규칙은 `//` 로 시작한다. 윈도우 경로는 `//c/Users/..`
    꼴로 적는다 — ponytail: 윈도우 표기는 실기 미확인.
    """
    d = directory.replace("\\", "/").rstrip("/")
    if len(d) >= 2 and d[1] == ":":
        d = "/" + d[0].lower() + d[2:]
    return "Read(/%s/claudlet-*-shot-*.png)" % d
