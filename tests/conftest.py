import os
import sys

# Make the src-layout package importable when running from a source checkout
# without `pip install` (CI / `python3 -m pytest -q`).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
