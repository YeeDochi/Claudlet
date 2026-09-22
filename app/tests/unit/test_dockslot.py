import os

import pytest

from claudlet.core import dockslot


@pytest.fixture(autouse=True)
def runtime(tmp_path, monkeypatch):
    """잠금 파일을 테스트별 임시 디렉터리로 격리 — 실제로 돌고 있는 펫의 슬롯을
    건드리지 않도록. hostinfo.runtime_dir()이 XDG_RUNTIME_DIR을 먼저 본다."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def test_first_claim_gets_slot_zero():
    slot, fd = dockslot.claim()
    try:
        assert slot == 0 and fd is not None
    finally:
        dockslot.release(fd)


def test_a_second_pet_gets_the_next_free_slot():
    fds = []
    try:
        for expected in range(3):
            slot, fd = dockslot.claim()
            fds.append(fd)
            assert slot == expected
    finally:
        for fd in fds:
            dockslot.release(fd)


def test_releasing_a_slot_frees_it_for_the_next_pet():
    slot0, fd0 = dockslot.claim()
    slot1, fd1 = dockslot.claim()
    assert (slot0, slot1) == (0, 1)
    dockslot.release(fd0)
    slot, fd = dockslot.claim()
    try:
        assert slot == 0            # 빈 앞자리를 다시 준다
    finally:
        dockslot.release(fd)
        dockslot.release(fd1)


def test_claim_lower_finds_the_gap_left_by_a_departed_pet():
    _s0, fd0 = dockslot.claim()
    s1, fd1 = dockslot.claim()
    dockslot.release(fd0)           # 앞 펫 종료
    slot, fd = dockslot.claim_lower(s1)
    try:
        assert slot == 0            # 뒷펫이 당겨 선다
    finally:
        dockslot.release(fd)
        dockslot.release(fd1)


def test_claim_lower_returns_nothing_when_the_row_ahead_is_full():
    fds = [dockslot.claim()[1] for _ in range(3)]
    try:
        assert dockslot.claim_lower(2) == (None, None)
        assert dockslot.claim_lower(0) == (None, None)   # 0번 앞은 없다
    finally:
        for fd in fds:
            dockslot.release(fd)


def test_claim_returns_nothing_when_every_slot_is_taken():
    fds = [dockslot.claim(max_slots=2)[1] for _ in range(2)]
    try:
        assert dockslot.claim(max_slots=2) == (None, None)
    finally:
        for fd in fds:
            dockslot.release(fd)


def test_slot_files_land_in_the_runtime_dir(runtime):
    dockslot.release(dockslot.claim()[1])
    assert os.path.exists(os.path.join(str(runtime), "claudlet-dock-0.slot"))


def test_release_tolerates_none_and_double_release():
    dockslot.release(None)
    slot, fd = dockslot.claim()
    assert slot == 0
    dockslot.release(fd)
    dockslot.release(fd)            # 두 번 놓아도 터지지 않는다
