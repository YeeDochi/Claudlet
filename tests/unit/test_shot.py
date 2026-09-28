"""포인터 캡처 폴백의 판단·좌표·파일 수명 — 순수 함수와 대표 데이터로."""
import os

from claudlet.core import inspect as inspectmod
from claudlet.core import shot
from claudlet.cli import install_hooks


def test_crop_maps_a_region_on_the_third_monitor():
    # 이 머신: 1920+1920+1920 가로, 가상 데스크톱 5760x1200, 캡처도 같은 크기
    r = {"x": 4000.0, "y": 100.0, "w": 300.0, "h": 200.0}
    assert shot.crop_rect(r, (0, 0, 5760, 1200), (5760, 1200)) == (4000, 100, 300, 200)


def test_crop_scales_for_hidpi_and_a_shifted_origin():
    r = {"x": -900.0, "y": 50.0, "w": 100.0, "h": 100.0}
    assert shot.crop_rect(r, (-1920, 0, 3840, 1080), (7680, 2160)) == (2040, 100, 200, 200)


def test_crop_clips_to_the_screen_and_gives_up_off_it():
    assert shot.crop_rect({"x": 5700.0, "y": 0.0, "w": 200.0, "h": 50.0},
                          (0, 0, 5760, 1200), (5760, 1200)) == (5700, 0, 60, 50)
    assert shot.crop_rect({"x": 9000.0, "y": 0.0, "w": 10.0, "h": 10.0},
                          (0, 0, 5760, 1200), (5760, 1200)) is None


def test_saved_shots_are_private_and_cleared_together(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    a = shot.save("s1", b"png-a")
    b = shot.save("s1", b"png-b")
    other = shot.save("s2", b"png-c")
    assert a != b and open(a, "rb").read() == b"png-a"
    assert oct(os.stat(a).st_mode & 0o777) == "0o600"
    assert shot.clear("s1") == 2
    assert not os.path.exists(a) and not os.path.exists(b)
    assert os.path.exists(other)                # 다른 세션 것은 그대로


def test_the_prompt_names_the_capture_only_when_there_is_one():
    ctx = inspectmod.build_context(None, "뭐야?")
    assert "화면 캡처" not in inspectmod.render_prompt(ctx)
    ctx["image"] = "/run/user/1000/claudlet-x-shot-1.png"
    assert "/run/user/1000/claudlet-x-shot-1.png" in inspectmod.render_prompt(ctx)


def test_the_allow_rule_uses_claude_codes_absolute_path_form():
    # 실측: 이 규칙 하나로 -p 세션이 권한 창 없이 읽었다
    assert shot.allow_rule("/run/user/1000") == "Read(//run/user/1000/claudlet-*-shot-*.png)"
    assert shot.allow_rule("C:\\Users\\me\\AppData\\Local\\Temp") == \
        "Read(//c/Users/me/AppData/Local/Temp/claudlet-*-shot-*.png)"


def test_the_installer_adds_one_rule_and_keeps_the_users():
    s = {"permissions": {"allow": ["Bash(ls)"], "deny": ["Read(.env)"]}}
    once = install_hooks.with_shot_rule(s, directory="/run/user/1000")
    twice = install_hooks.with_shot_rule(once, directory="/run/user/1000")
    assert twice == once
    assert once["permissions"]["allow"] == [
        "Bash(ls)", "Read(//run/user/1000/claudlet-*-shot-*.png)"]
    assert once["permissions"]["deny"] == ["Read(.env)"]


def test_removing_leaves_no_empty_permissions_behind():
    s = install_hooks.with_shot_rule({}, directory="/run/user/1000")
    assert install_hooks.with_shot_rule(s, remove=True) == {}
