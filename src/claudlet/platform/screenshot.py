"""화면 캡처 어댑터 — 포인터로 고른 영역을 PNG 바이트로.

얇은 플랫폼 래퍼다. 좌표 변환은 core/shot.crop_rect(순수)가 하고, 여기는
찍기만 한다. 실기로 확인한다(모킹해서 호출 순서를 검사하지 않는다).

- 리눅스(KDE): XWayland 에서는 Qt 의 grabWindow 가 검은 화면을 준다(실측).
  spectacle 로 가상 데스크톱 전체를 찍고 자른다. 1~2초 걸려 QProcess 로 비동기.
  KWin ScreenShot2 는 제한 인터페이스라 우리 프로세스는 못 부른다.
- 윈도우/macOS: Qt grabWindow(0) 로 그 화면에서 잘라 찍는다.
  ponytail: 둘 다 실기 미확인. macOS 는 화면 기록 권한이 없으면 바탕화면만 찍힌다.
"""
import os
import shutil
import sys

from claudlet.core import hostinfo, shot


def available():
    """이 머신에서 찍을 수 있는가(doctor·설정 안내용)."""
    if sys.platform.startswith("linux"):
        return shutil.which("spectacle") is not None
    return True


def _png(img):
    from PyQt6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def capture(rect, on_done, parent=None):
    """`rect`(가상 데스크톱 좌표 dict) 를 찍어 `on_done(png_bytes | None)`.

    리눅스는 나중에(프로세스가 끝나면), 그 밖은 곧바로 부른다. 어떤 실패도
    예외로 새지 않고 None 이 된다 — 캡처는 덤이라 질문을 막으면 안 된다.
    """
    try:
        if sys.platform.startswith("linux"):
            return _spectacle(rect, on_done, parent)
        return on_done(_qt_grab(rect))
    except Exception:
        return on_done(None)


def _qt_grab(rect):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QGuiApplication
    cx, cy = int(rect["x"] + rect["w"] / 2), int(rect["y"] + rect["h"] / 2)
    scr = QGuiApplication.screenAt(QPoint(cx, cy)) or QGuiApplication.primaryScreen()
    g = scr.geometry()
    pm = scr.grabWindow(0, int(rect["x"]) - g.x(), int(rect["y"]) - g.y(),
                        int(rect["w"]), int(rect["h"]))
    return None if pm.isNull() else _png(pm.toImage())


def _spectacle(rect, on_done, parent):
    from PyQt6.QtCore import QProcess
    from PyQt6.QtGui import QGuiApplication, QImage
    exe = shutil.which("spectacle")
    if not exe:
        return on_done(None)
    # 전체 화면이 잠깐이라도 디스크에 닿는다 — 사용자 전용 tmpfs(runtime_dir)에
    # 두고 읽자마자 지운다.
    tmp = os.path.join(hostinfo.runtime_dir(), "claudlet-grab-%d.png" % os.getpid())
    virt = QGuiApplication.primaryScreen().virtualGeometry()
    proc = QProcess(parent)
    fired = []

    def _finished(*_):
        if fired:           # errorOccurred 와 finished 가 둘 다 올 수 있다
            return
        fired.append(1)
        png = None
        try:
            img = QImage(tmp)
            if not img.isNull():
                box = shot.crop_rect(rect, (virt.x(), virt.y(), virt.width(),
                                            virt.height()),
                                     (img.width(), img.height()))
                if box is not None:
                    png = _png(img.copy(*box))
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            proc.deleteLater()
        on_done(png)

    proc.finished.connect(_finished)
    proc.errorOccurred.connect(lambda *_: _finished())
    # -b 창 없이, -n 알림 없이, -f 가상 데스크톱 전체
    proc.start(exe, ["-b", "-n", "-f", "-o", tmp])
    return proc
