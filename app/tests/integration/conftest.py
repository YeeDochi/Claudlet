import os

import pytest


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """모든 통합 테스트를 임시 config/runtime 디렉터리 안에서 돌린다.

    펫은 도크 위치를 사용자 config.json에 저장하고 슬롯 잠금 파일을 런타임
    디렉터리에 만든다 — 격리하지 않으면 드래그를 흉내 내는 테스트가 실제 사용자
    설정을 덮어쓰고, 지금 돌고 있는 진짜 펫과 슬롯을 다투게 된다.
    """
    cfg = tmp_path / "config"
    run = tmp_path / "run"
    os.makedirs(str(cfg), exist_ok=True)
    os.makedirs(str(run), exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    return tmp_path
