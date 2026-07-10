"""Optional user art: if ``assets/<state>.gif`` (or ``.png``) exists, the pet
renders that sprite for ``<state>`` instead of the code-drawn creature.

Frames are decoded up front into a list of QPixmaps (animation is driven by the
pet's own frame counter, so a GIF's own timing is ignored — one sprite frame per
pet tick). Requires a live QApplication (Qt image plugins), so this is imported
and used from pet.py, never from the pure engine/config modules.
"""
import os

from PyQt6.QtGui import QImageReader, QPixmap

EXTS = (".gif", ".png")


def load_frames(path):
    """All frames of an image file as QPixmaps (single-element list for a still
    image; empty list if it can't be read)."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    frames = []
    count = reader.imageCount() if reader.supportsAnimation() else 1
    if count < 1:
        count = 1
    for _ in range(count):
        img = reader.read()
        if img.isNull():
            break
        frames.append(QPixmap.fromImage(img))
    return frames


def load_overrides(assets_dir, states):
    """Map ``state -> [QPixmap, ...]`` for every state that has a sprite file in
    ``assets_dir``. ``.gif`` wins over ``.png``. States with no file are absent
    (the pet falls back to the code-drawn creature)."""
    out = {}
    if not os.path.isdir(assets_dir):
        return out
    for state in states:
        for ext in EXTS:
            path = os.path.join(assets_dir, state + ext)
            if os.path.isfile(path):
                frames = load_frames(path)
                if frames:
                    out[state] = frames
                break
    return out
