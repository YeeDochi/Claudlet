import os
import sys

# Make the src-layout package importable when running from a source checkout
# without `pip install` (CI / `python3 -m pytest -q`).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


import pytest


@pytest.fixture(autouse=True)
def _isolated_config(request, tmp_path, monkeypatch):
    """Never read or write the developer's own ~/.config/claudlet/config.json.

    The pet reads that file for its palette and scale, so a machine where
    someone had set scale=9 in the settings UI failed a window-size test that
    passes everywhere else. Tests that want particular settings write this
    file themselves; the rest get an empty config, i.e. the defaults.
    """
    from claudlet.core import petconfig
    if request.node.get_closest_marker("real_config_path"):
        return None                 # tests OF config_path itself need the real one
    path = tmp_path / "claudlet-config.json"
    monkeypatch.setattr(petconfig, "config_path", lambda: str(path))
    return path


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_config_path: keep petconfig.config_path() unpatched (it is the "
        "thing under test)")
