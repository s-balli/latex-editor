"""latex_refs: \\label ve .bib anahtar toplama testleri (\\ref/\\cite tamamlama)."""

import os
import sys
import time

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from core import latex_refs


# --- collect_labels ---

def test_collect_labels_basic():
    labels = latex_refs.collect_labels("text \\label{sec:intro} more \\label{eq:1}", "/tmp/x.tex")
    assert labels == ["eq:1", "sec:intro"]   # sıralı


def test_collect_labels_dedup_and_sort():
    labels = latex_refs.collect_labels("\\label{x}\\label{x}\\label{a}", "/tmp/x.tex")
    assert labels == ["a", "x"]               # tekil + sıralı


def test_collect_labels_ignores_comment():
    labels = latex_refs.collect_labels("\\label{real}\n% \\label{commented}\n", "/tmp/x.tex")
    assert labels == ["real"]


def test_collect_labels_from_input_chain(tmp_path):
    child = tmp_path / "ch.tex"
    child.write_text("\\label{from_child}", encoding="utf-8")
    main = tmp_path / "main.tex"
    main.write_text("\\label{from_main}\n\\input{ch}\n", encoding="utf-8")
    labels = latex_refs.collect_labels(main.read_text(encoding="utf-8"), str(main))
    assert "from_main" in labels
    assert "from_child" in labels


def test_collect_labels_input_chain_cached(tmp_path):
    """Çocuk dosya değişmeyince önbellekten, değişince yeniden okunmalı."""
    child = tmp_path / "ch.tex"
    child.write_text("\\label{v1}", encoding="utf-8")
    main = tmp_path / "main.tex"
    main.write_text("\\input{ch}\n", encoding="utf-8")
    content = main.read_text(encoding="utf-8")
    assert latex_refs.collect_labels(content, str(main)) == ["v1"]
    # .tex'i değiştir + mtime'u ileri taşı (aynı mtime riskine karşı)
    child.write_text("\\label{v2}", encoding="utf-8")
    fut = time.time() + 10
    os.utime(child, (fut, fut))
    assert latex_refs.collect_labels(content, str(main)) == ["v2"]


# --- collect_cite_keys ---

def test_collect_cite_keys_basic(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{smith2020,\n title={X},\n}\n@book{jones_2019, author={Y}}\n",
        encoding="utf-8")
    tex = tmp_path / "m.tex"
    tex.write_text("\\addbibresource{refs.bib}\n", encoding="utf-8")
    keys = latex_refs.collect_cite_keys(tex.read_text(encoding="utf-8"), str(tex))
    assert keys == ["jones_2019", "smith2020"]


def test_collect_cite_keys_bibliography_cmd(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@misc{key1,}\n", encoding="utf-8")
    tex = tmp_path / "m.tex"
    tex.write_text("\\bibliography{refs}\n", encoding="utf-8")  # .bib uzantısız
    keys = latex_refs.collect_cite_keys(tex.read_text(encoding="utf-8"), str(tex))
    assert keys == ["key1"]


def test_collect_cite_keys_no_bib(tmp_path):
    tex = tmp_path / "m.tex"
    tex.write_text("burada bib yok", encoding="utf-8")
    assert latex_refs.collect_cite_keys(tex.read_text(encoding="utf-8"), str(tex)) == []


def test_collect_cite_keys_cache_invalidates(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{a,}", encoding="utf-8")
    tex = tmp_path / "m.tex"
    tex.write_text("\\addbibresource{refs.bib}\n", encoding="utf-8")
    content = tex.read_text(encoding="utf-8")
    assert latex_refs.collect_cite_keys(content, str(tex)) == ["a"]
    bib.write_text("@article{b,}", encoding="utf-8")
    fut = time.time() + 10
    os.utime(bib, (fut, fut))
    assert latex_refs.collect_cite_keys(content, str(tex)) == ["b"]
