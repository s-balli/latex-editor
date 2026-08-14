"""Sürüm tutarlılığı — pyproject.toml, core/version.py ile senkron kalmalı.

Çalışma zamanı sürüm kaynağı core/version.py'dir (pyproject pip paketi değil);
bu test, release sırasında ikisinden birinin güncellenmemesini yakalar.
"""

import os
import re

from core.version import VERSION

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_pyproject_version_matches_core():
    with open(os.path.join(_ROOT, "pyproject.toml"), encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "pyproject.toml'da version alanı bulunamadı"
    assert m.group(1) == VERSION
