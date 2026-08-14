"""latex_refs: \\label ve .bib anahtar toplama testleri (\\ref/\\cite tamamlama)."""

import os
import time

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


# --- find_label_location / find_cite_location (Alt+tık tanıma git) ---

def test_find_label_location_in_main(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("baslik\n\\label{fig:x}\n", encoding="utf-8")
    loc = latex_refs.find_label_location(main.read_text(encoding="utf-8"), str(main), "fig:x")
    assert loc == (str(main), 2)


def test_find_label_location_in_input_child(tmp_path):
    child = tmp_path / "ch.tex"
    child.write_text("\\section{X}\n\\label{eq:1}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\input{ch}\n", encoding="utf-8")
    loc = latex_refs.find_label_location(main.read_text(encoding="utf-8"), str(main), "eq:1")
    assert loc == (str(child), 2)


def test_find_label_location_not_found(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{a}\n", encoding="utf-8")
    assert latex_refs.find_label_location(main.read_text(encoding="utf-8"), str(main), "yok") is None


def test_find_label_location_ignores_commented(tmp_path):
    # yorumdaki \label sayılmamalı; gerçek satır no'su dönmeli
    main = tmp_path / "m.tex"
    main.write_text("% \\label{a}\n\\label{a}\n", encoding="utf-8")
    loc = latex_refs.find_label_location(main.read_text(encoding="utf-8"), str(main), "a")
    assert loc == (str(main), 2)


def test_find_cite_location(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("preamble\n@article{karaca2024,\n author={K},\n}\n", encoding="utf-8")
    tex = tmp_path / "m.tex"
    tex.write_text("\\bibliography{refs}\n\\cite{karaca2024}\n", encoding="utf-8")
    loc = latex_refs.find_cite_location(tex.read_text(encoding="utf-8"), str(tex), "karaca2024")
    assert loc == (str(bib), 2)


def test_find_cite_location_no_bib_or_key(tmp_path):
    tex = tmp_path / "m.tex"
    tex.write_text("\\bibliography{refs}\n", encoding="utf-8")
    # .bib yok
    assert latex_refs.find_cite_location(tex.read_text(encoding="utf-8"), str(tex), "k") is None
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{baska,}\n", encoding="utf-8")
    # anahtar yok
    assert latex_refs.find_cite_location(tex.read_text(encoding="utf-8"), str(tex), "yok") is None


# --- find_cite_usage (.bib girdisinden makalede \cite yerine, ters yön) ---

def test_find_cite_usage_in_tex(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{k,\n author={A},\n}\n", encoding="utf-8")
    tex = tmp_path / "m.tex"
    tex.write_text("baslik\nMetin \\citep{k} burada.\n", encoding="utf-8")
    assert latex_refs.find_cite_usage(str(bib), "k") == (str(tex), 2)


def test_find_cite_usage_multi_key(tmp_path):
    # \cite{a, b, c} — anahtarlardan biri eşleşmeli
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{b,}\n", encoding="utf-8")
    tex = tmp_path / "m.tex"
    tex.write_text("\\cite{a, b, c}\n", encoding="utf-8")
    assert latex_refs.find_cite_usage(str(bib), "b") == (str(tex), 1)


def test_find_cite_usage_in_subdir_tex(tmp_path):
    # .bib ana dizinde, .tex alt dizinde — os.walk bulmalı
    sub = tmp_path / "ch"
    sub.mkdir()
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{k,}\n", encoding="utf-8")
    tex = sub / "c.tex"
    tex.write_text("\\cite{k}\n", encoding="utf-8")
    assert latex_refs.find_cite_usage(str(bib), "k") == (str(tex), 1)


def test_find_cite_usage_not_found(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{k,}\n", encoding="utf-8")
    tex = tmp_path / "m.tex"
    tex.write_text("\\cite{baska}\n", encoding="utf-8")
    assert latex_refs.find_cite_usage(str(bib), "yok") is None


# --- find_bibitem_location (\cite için .bib yoksa el ile kaynakça fallback) ---

def test_find_bibitem_location(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("Metin \\cite{k}.\n\\begin{thebibliography}{}\n\\bibitem{k} Yazar.\n\\end{thebibliography}\n", encoding="utf-8")
    assert latex_refs.find_bibitem_location(main.read_text(encoding="utf-8"), str(main), "k") == (str(main), 3)


def test_find_bibitem_location_with_label(tmp_path):
    # \bibitem[Author(2020)]{key} — opsiyonel etiket
    main = tmp_path / "m.tex"
    main.write_text("\\bibitem[Author(2020)]{karaca2024} Karaca.\n", encoding="utf-8")
    assert latex_refs.find_bibitem_location(main.read_text(encoding="utf-8"), str(main), "karaca2024") == (str(main), 1)


def test_find_bibitem_location_in_input_child(tmp_path):
    child = tmp_path / "ch.tex"
    child.write_text("\\bibitem{c}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\input{ch}\n", encoding="utf-8")
    assert latex_refs.find_bibitem_location(main.read_text(encoding="utf-8"), str(main), "c") == (str(child), 1)


def test_find_bibitem_location_not_found(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\bibitem{baska}\n", encoding="utf-8")
    assert latex_refs.find_bibitem_location(main.read_text(encoding="utf-8"), str(main), "yok") is None
