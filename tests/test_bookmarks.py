"""pdf_viewer bookmark helper'ları — pypdfium2 API sürüm uyumu testleri.

pypdfium2 get_toc() çıktısı sürümler arası değişti: eski PdfBookmark
(get_title/get_dest metodları) → yeni PdfOutlineItem (.title/.page_index).
Helper'lar her iki formu da handle etmeli.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "desktop")))

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from gui.pdf_viewer_mixins._bookmarks import _bm_title, _bm_level, _bm_page_index


class _Dest:
    def __init__(self, idx):
        self._idx = idx

    def get_index(self):
        return self._idx


class _OldApiBM:
    """Eski pypdfium2 PdfBookmark: get_title()/get_dest() metodları."""

    def __init__(self, title, level, page_idx):
        self._title = title
        self.level = level
        self._dest = _Dest(page_idx)

    def get_title(self):
        return self._title

    def get_dest(self):
        return self._dest


class _NewApiBM:
    """Yeni pypdfium2 PdfOutlineItem: .title/.level/.page_index (get_* yok)."""

    def __init__(self, title, level, page_idx):
        self.title = title
        self.level = level
        self.page_index = page_idx


class TestBookmarkHelpers:
    def test_eski_api(self):
        bm = _OldApiBM("Bölüm 1", 0, 3)
        assert _bm_title(bm) == "Bölüm 1"
        assert _bm_level(bm) == 0
        assert _bm_page_index(bm) == 3

    def test_yeni_api(self):
        bm = _NewApiBM("Section 2", 1, 7)
        assert _bm_title(bm) == "Section 2"
        assert _bm_level(bm) == 1
        assert _bm_page_index(bm) == 7

    def test_bos_baslik(self):
        assert _bm_title(_OldApiBM("", 0, 0)) == ""
        assert _bm_title(_NewApiBM(None, 0, 0)) == ""

    def test_sayfa_indeksi_yoksa_none(self):
        class NoPage:
            level = 0

            def get_title(self):
                return "x"

        assert _bm_page_index(NoPage()) is None
