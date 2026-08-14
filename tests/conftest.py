"""Test bootstrap — QT offscreen platform + import yolları.

Daha önce her test dosyasında tekrarlanan sys.path bloğu burada toplandı;
conftest, test modülleri toplanmadan önce yüklendiği için herkese yeter.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DESKTOP = os.path.join(_REPO, "desktop")
for _p in (_REPO, _DESKTOP):
    if _p not in sys.path:
        sys.path.insert(0, _p)
