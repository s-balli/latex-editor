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
        "@article{smith2020,\n title={X},\n}\n@book{jones_2019, author={Y}}\n", encoding="utf-8")
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


# --- collect_input_paths (\input / \include tamamlama) ---

def test_collect_input_paths_basic(tmp_path):
    (tmp_path / "main.tex").write_text("\\input{bolum1}", encoding="utf-8")
    (tmp_path / "bolum1.tex").write_text("x", encoding="utf-8")
    sub = tmp_path / "bolumler"
    sub.mkdir()
    (sub / "giris.tex").write_text("x", encoding="utf-8")
    assert latex_refs.collect_input_paths(str(tmp_path / "main.tex")) == ["bolum1", "bolumler/giris"]


def test_collect_input_paths_excludes_self_and_non_tex(tmp_path):
    main = tmp_path / "main.tex"
    main.write_text("\\input{b}", encoding="utf-8")
    (tmp_path / "b.tex").write_text("x", encoding="utf-8")
    (tmp_path / "notlar.md").write_text("x", encoding="utf-8")
    assert latex_refs.collect_input_paths(str(main)) == ["b"]


def test_collect_input_paths_skips_hidden_dirs(tmp_path):
    main = tmp_path / "main.tex"
    main.write_text("x", encoding="utf-8")
    hid = tmp_path / ".git"
    hid.mkdir()
    (hid / "t.tex").write_text("x", encoding="utf-8")
    assert latex_refs.collect_input_paths(str(main)) == []


# --- collect_image_paths (\includegraphics tamamlama) ---

def test_collect_image_paths_basic(tmp_path):
    main = tmp_path / "main.tex"
    main.write_text("x", encoding="utf-8")
    (tmp_path / "sekil.png").write_bytes(b"")
    sub = tmp_path / "media"
    sub.mkdir()
    (sub / "fig.jpg").write_bytes(b"")
    (sub / "logo.pdf").write_bytes(b"")
    (tmp_path / "main.pdf").write_bytes(b"")    # derleme çıktısı — önerilmez
    (tmp_path / "notlar.md").write_text("x", encoding="utf-8")
    paths = latex_refs.collect_image_paths(str(main))
    assert paths == ["media/fig.jpg", "media/logo.pdf", "sekil.png"]


def test_collect_image_paths_skips_hidden_dirs(tmp_path):
    main = tmp_path / "main.tex"
    main.write_text("x", encoding="utf-8")
    hid = tmp_path / ".git"
    hid.mkdir()
    (hid / "a.png").write_bytes(b"")
    assert latex_refs.collect_image_paths(str(main)) == []


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


# --- audit_references (referans denetimi) ---

def test_audit_clean(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{k,}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n\\ref{fig:a}\n\\cite{k}\n\\bibliography{refs}\n", encoding="utf-8")
    r = latex_refs.audit_references(main.read_text(encoding="utf-8"), str(main))
    assert r.undefined_refs == []
    assert r.undefined_cites == []
    assert r.unused_bib_keys == []


def test_audit_undefined_ref_and_cite(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\ref{fig:yok}\n\\cite{yok2024}\n", encoding="utf-8")
    r = latex_refs.audit_references(main.read_text(encoding="utf-8"), str(main))
    assert r.undefined_refs == ["fig:yok"]
    assert r.undefined_cites == ["yok2024"]


def test_audit_unused_bib_keys(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{a,}\n@book{b,}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\cite{a}\n\\bibliography{refs}\n", encoding="utf-8")
    r = latex_refs.audit_references(main.read_text(encoding="utf-8"), str(main))
    assert r.unused_bib_keys == ["b"]


def test_audit_input_chain(tmp_path):
    # label ve \cite çocuk dosyada, ref ana dosyada — zincir iki yönde de sayılır
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{a,}\n@book{b,}\n", encoding="utf-8")
    child = tmp_path / "ch.tex"
    child.write_text("\\label{fig:x}\n\\cite{a}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\input{ch}\n\\ref{fig:x}\n\\bibliography{refs}\n", encoding="utf-8")
    r = latex_refs.audit_references(main.read_text(encoding="utf-8"), str(main))
    assert r.undefined_refs == []
    assert r.undefined_cites == []
    assert r.unused_bib_keys == ["b"]


def test_audit_nocite_all_disables_unused(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{a,}\n@book{b,}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\nocite{*}\n\\bibliography{refs}\n", encoding="utf-8")
    r = latex_refs.audit_references(main.read_text(encoding="utf-8"), str(main))
    assert r.unused_bib_keys == []


def test_audit_ignores_commented_usage(tmp_path):
    # yorumdaki \ref tanımsız sayılmaz; yorumdaki \cite kullanıldı sayılmaz
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{a,}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("% \\ref{fig:yok}\n% \\cite{a}\n\\bibliography{refs}\n", encoding="utf-8")
    r = latex_refs.audit_references(main.read_text(encoding="utf-8"), str(main))
    assert r.undefined_refs == []
    assert r.unused_bib_keys == ["a"]


def test_audit_bibitem_fallback(tmp_path):
    # .bib yok, thebibliography + \bibitem var → cite tanımlı sayılır
    main = tmp_path / "m.tex"
    main.write_text("\\cite{k}\n\\begin{thebibliography}{}\n\\bibitem{k} Yazar.\n\\end{thebibliography}\n", encoding="utf-8")
    r = latex_refs.audit_references(main.read_text(encoding="utf-8"), str(main))
    assert r.undefined_cites == []


def test_audit_cref_multi_key(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\cref{a,b}\n\\label{a}\n", encoding="utf-8")
    r = latex_refs.audit_references(main.read_text(encoding="utf-8"), str(main))
    assert r.undefined_refs == ["b"]


# --- find_key_usage (denetim bulgusundan kullanım yerine atlama) ---

def test_find_key_usage_ref_in_main(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("baslik\nMetin \\ref{fig:x} burada.\n", encoding="utf-8")
    loc = latex_refs.find_key_usage(main.read_text(encoding="utf-8"), str(main), "fig:x", "ref")
    assert loc == (str(main), 2)


def test_find_key_usage_cite_in_chain_child(tmp_path):
    child = tmp_path / "ch.tex"
    child.write_text("\\cite{k2024}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\input{ch}\n", encoding="utf-8")
    loc = latex_refs.find_key_usage(main.read_text(encoding="utf-8"), str(main), "k2024", "cite")
    assert loc == (str(child), 1)


def test_find_key_usage_ignores_commented(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("% \\ref{fig:x}\n\\ref{fig:x}\n", encoding="utf-8")
    loc = latex_refs.find_key_usage(main.read_text(encoding="utf-8"), str(main), "fig:x", "ref")
    assert loc == (str(main), 2)


def test_find_key_usage_multi_key_cite(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\cite{a, hedef, b}\n", encoding="utf-8")
    loc = latex_refs.find_key_usage(main.read_text(encoding="utf-8"), str(main), "hedef", "cite")
    assert loc == (str(main), 1)


def test_find_key_usage_not_found(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\ref{baska}\n", encoding="utf-8")
    assert latex_refs.find_key_usage(main.read_text(encoding="utf-8"), str(main), "yok", "ref") is None


# --- audit_references: kullanılmayan label ---

def test_audit_unused_labels(tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{kullanilan}\n\\ref{kullanilan}\n\\label{bos}\n", encoding="utf-8")
    r = latex_refs.audit_references(main.read_text(encoding="utf-8"), str(main))
    assert r.unused_labels == ["bos"]


def test_audit_unused_labels_chain_usage(tmp_path):
    # label ana dosyada, \ref çocukta → kullanılmış sayılır
    child = tmp_path / "ch.tex"
    child.write_text("\\ref{fig:x}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:x}\n\\input{ch}\n", encoding="utf-8")
    r = latex_refs.audit_references(main.read_text(encoding="utf-8"), str(main))
    assert r.unused_labels == []


# --- label_rename_spans / rename_label_in_text (F2 yeniden adlandırma) ---

def test_label_rename_spans_label_and_refs():
    text = "\\label{fig:a}\nbkz \\cref{fig:a, tab:b} ve \\ref{fig:a}\n\\label{fig:ax}"
    spans = latex_refs.label_rename_spans(text, "fig:a")
    assert len(spans) == 3
    for s, e in spans:
        assert text[s:e] == "fig:a"          # fig:ax yakalanmaz


def test_label_rename_spans_segment_with_space():
    text = "\\cref{a, tab:b}"
    spans = latex_refs.label_rename_spans(text, "tab:b")
    assert len(spans) == 1
    assert text[spans[0][0]:spans[0][1]] == "tab:b"


def test_rename_label_in_text_multi_segment():
    t = "\\label{fig:a} x\n\\cref{fig:a, tab:b} y\n"
    r = latex_refs.rename_label_in_text(t, "fig:a", "fig:yeni")
    assert r == "\\label{fig:yeni} x\n\\cref{fig:yeni, tab:b} y\n"


def test_rename_label_no_match_unchanged():
    t = "\\label{baska}\n"
    assert latex_refs.rename_label_in_text(t, "fig:a", "x") == t


# --- cite_rename_spans / bib_key_rename_spans (F2 cite) ---

def test_cite_rename_spans_multi_segment():
    text = "\\cite{a, hedef, b} ve \\citep[see][]{hedef}"
    spans = latex_refs.cite_rename_spans(text, "hedef")
    assert len(spans) == 2
    for s, e in spans:
        assert text[s:e] == "hedef"


def test_cite_rename_spans_exact_segment():
    # 'a' segmenti 'ab' ile karışmaz
    text = "\\cite{a, ab}"
    spans = latex_refs.cite_rename_spans(text, "a")
    assert len(spans) == 1 and text[spans[0][0]:spans[0][1]] == "a"


def test_bib_key_rename_spans():
    text = "@article{hedef,\n title={X},\n}\n@book{baska,}\n"
    spans = latex_refs.bib_key_rename_spans(text, "hedef")
    assert spans == [(9, 14)]          # '@article{' 9 karakter; 'hedef' 9..13


def test_bib_key_rename_spans_no_match():
    assert latex_refs.bib_key_rename_spans("@book{baska,}", "yok") == []


# --- bibitem_rename_spans (F2, el ile kaynakça) ---

def test_bibitem_rename_spans_with_label():
    text = "\\bibitem[Yazar(2020)]{hedef} Açıklama.\n\\bibitem{baska} X.\n"
    spans = latex_refs.bibitem_rename_spans(text, "hedef")
    assert len(spans) == 1 and text[spans[0][0]:spans[0][1]] == "hedef"


def test_bibitem_rename_spans_no_match():
    assert latex_refs.bibitem_rename_spans("\\bibitem{baska}\n", "yok") == []


# =====================================================================
# Önbellek sınırları: uzun oturumda sınırsız birikme yok (LRU)
# =====================================================================


class TestCacheBounds:
    def test_cache_put_siniri_asarsa_en_eski_duser(self):
        from core import latex_refs as lr
        lr._label_file_cache.clear()
        for i in range(lr._CACHE_MAX + 10):
            lr._cache_put(lr._label_file_cache, f"f{i}.tex", (1.0, [f"lab{i}"]))
        assert len(lr._label_file_cache) == lr._CACHE_MAX
        # en eski girdiler düştü, en yeniler duruyor
        assert "f0.tex" not in lr._label_file_cache
        assert f"f{lr._CACHE_MAX + 9}.tex" in lr._label_file_cache

    def test_cache_get_isabet_tazelestirir(self):
        from core import latex_refs as lr
        lr._bib_cache.clear()
        for i in range(lr._CACHE_MAX):
            lr._cache_put(lr._bib_cache, f"b{i}.bib", (1.0, []))
        # en eskiye isabet: tazelenir; yeni ekleme artik ikinci en eskiyi düşürür
        assert lr._cache_get(lr._bib_cache, "b0.bib") == (1.0, [])
        lr._cache_put(lr._bib_cache, "yeni.bib", (2.0, []))
        assert "b0.bib" in lr._bib_cache
        assert "b1.bib" not in lr._bib_cache

    def test_collect_labels_cok_dosyada_sinirda_kalir(self, tmp_path):
        from core import latex_refs as lr
        ana = tmp_path / "ana.tex"
        satirlar = ["\\begin{document}"] + [
            f"\\input{{c{i}}}" for i in range(lr._CACHE_MAX + 5)
        ] + ["\\end{document}"]
        ana.write_text("\n".join(satirlar), encoding="utf-8")
        for i in range(lr._CACHE_MAX + 5):
            (tmp_path / f"c{i}.tex").write_text(f"\\label{{l{i}}}\n", encoding="utf-8")
        lr._label_file_cache.clear()
        lr.collect_labels(ana.read_text(encoding="utf-8"), str(ana))
        assert len(lr._label_file_cache) <= lr._CACHE_MAX
        lr._label_file_cache.clear()


# --- \nocite{*}: '*' anahtar değil ---

def _nocite_projesi(tmp_path, govde):
    (tmp_path / "k.bib").write_text(
        "@article{einstein1905, title={X}}\n@book{bohr1913, title={Y}}\n",
        encoding="utf-8")
    icerik = ("\\documentclass{article}\n\\begin{document}\n"
              + govde + "\\bibliography{k}\n\\end{document}\n")
    ana = tmp_path / "main.tex"
    ana.write_text(icerik, encoding="utf-8")
    return icerik, str(ana)


def test_nocite_yildizi_tanimsiz_cite_sayilmaz(tmp_path):
    """\\nocite{*} 'hepsini al' demek; '*' bir kaynak anahtarı değil.

    _RE_CITEUSE \\nocite'ı da kapsadığı için '*' kullanılan anahtarlar
    kümesine giriyor, hiçbir .bib girdisiyle eşleşmiyor ve denetim panelinde
    kalıcı "Tanımsız \\cite: *" uyarısı üretiyordu — \\nocite{*} kullanan HER
    belgede, üstelik derleme sonrası denetim açıksa her derlemede.
    """
    icerik, ana = _nocite_projesi(tmp_path, "Metin \\cite{einstein1905}.\n\\nocite{*}\n")
    rapor = latex_refs.audit_references(icerik, ana)
    assert rapor.undefined_cites == []
    # \nocite{*} her girdiyi kullanılmış sayar (eski davranış korunmalı)
    assert rapor.unused_bib_keys == []


def test_nocite_yildizsiz_denetim_bozulmadi(tmp_path):
    """'*' filtresi gerçek bulguları elememeli."""
    icerik, ana = _nocite_projesi(
        tmp_path, "Metin \\cite{einstein1905,yokolan}.\n")
    rapor = latex_refs.audit_references(icerik, ana)
    assert rapor.undefined_cites == ["yokolan"]
    assert rapor.unused_bib_keys == ["bohr1913"]


# --- Toplu konum çıkarımı: tekil aramayla aynı sonuç, tek okuma ---

def _zincir_projesi(tmp_path, n_bolum=4, n_etiket=3):
    (tmp_path / "k.bib").write_text(
        "".join("@article{a%d, title={T}}\n" % i for i in range(6)), encoding="utf-8")
    ana = ["\\documentclass{book}", "\\bibliography{k}", "\\begin{document}",
           "\\label{sec:ana}", "Atif \\cite{a0} ve \\ref{sec:b0-0}."]
    for b in range(n_bolum):
        satir = []
        for j in range(n_etiket):
            satir.append("Metin %d" % j)
            satir.append("\\label{sec:b%d-%d}" % (b, j))
        satir.append("\\ref{sec:ana} ve \\cite{a1}")
        (tmp_path / ("b%d.tex" % b)).write_text("\n".join(satir), encoding="utf-8")
        ana.append("\\input{b%d}" % b)
    ana.append("\\end{document}")
    icerik = "\n".join(ana)
    yol = tmp_path / "main.tex"
    yol.write_text(icerik, encoding="utf-8")
    return icerik, str(yol)


def test_toplu_konumlar_tekil_aramayla_ayni(tmp_path):
    """label_locations/bib_key_locations/key_usage_locations = tekil karşılıkları.

    Toplu sürümler hız için var; sonuç farklılaşırsa denetim panelindeki
    'dosya:satır' bağlantıları yanlış yere atlar.
    """
    icerik, ana = _zincir_projesi(tmp_path)
    latex_refs._label_file_cache.clear()

    etiketler = latex_refs.label_locations(icerik, ana)
    assert etiketler, "hiç label bulunamadı — proje kurulumu bozuk"
    for k in etiketler:
        assert etiketler[k] == latex_refs.find_label_location(icerik, ana, k), k

    bibler = latex_refs.bib_key_locations(icerik, ana)
    assert bibler
    for k in bibler:
        assert bibler[k] == latex_refs.find_cite_location(icerik, ana, k), k

    for aile in ("ref", "cite"):
        kullanim = latex_refs.key_usage_locations(icerik, ana, aile)
        assert kullanim
        for k in kullanim:
            assert kullanim[k] == latex_refs.find_key_usage(icerik, ana, k, aile), k


def test_toplu_konum_ilk_eslesmeyi_dondurur(tmp_path):
    """Aynı anahtar iki dosyada varsa tekil arama gibi İLKİ kazanmalı."""
    (tmp_path / "c.tex").write_text("\\label{ayni}\n", encoding="utf-8")
    icerik = "\\label{ayni}\n\\input{c}\n"
    ana = tmp_path / "main.tex"
    ana.write_text(icerik, encoding="utf-8")
    latex_refs._label_file_cache.clear()
    assert latex_refs.label_locations(icerik, str(ana))["ayni"] == (str(ana), 1)


def test_toplu_konum_yorumdaki_label_i_atlar(tmp_path):
    icerik = "% \\label{yorumda}\n\\label{gercek}\n"
    ana = tmp_path / "main.tex"
    ana.write_text(icerik, encoding="utf-8")
    konumlar = latex_refs.label_locations(icerik, str(ana))
    assert "yorumda" not in konumlar
    assert konumlar["gercek"] == (str(ana), 2)


# --- find_bib_path: \input/\include ZİNCİRİ ---
#
# Çok dosyalı tezlerde \bibliography bildirimi ana dosyada değil bir bölüm
# dosyasında oluyor. Zincir taranmadığında uygulama "kaynakça yok" sanıyor ve
# ÜÇ şey birden bozuluyordu: \cite tamamlama hiçbir anahtar önermiyor,
# referans denetimi her \cite'ı "tanımsız" sayıyor, Kaynakça sekmesi boş
# kalıyor. Gerçek örnek: template33-tez, 0main.tex -> \include{17kaynaklar}
# -> orada \bibliography{referans}. Denetim o projede 7 sahte "tanımsız
# cite" üretiyordu; zincir eklendikten sonra 1'e indi (ölçüldü).


def _cok_dosyali_proje(tmp_path, bildirim_nerede: str):
    """bildirim_nerede: 'ana' | 'bolum' | 'yok'."""
    (tmp_path / "referans.bib").write_text(
        "@article{a2020, author={A}, title={T}, journal={J}, year={2020}}\n",
        encoding="utf-8")
    bolum = "Bölüm metni.\n"
    if bildirim_nerede == "bolum":
        bolum += "\\bibliography{referans}\n"
    (tmp_path / "bolum1.tex").write_text(bolum, encoding="utf-8")
    ana = "\\documentclass{book}\n\\begin{document}\n\\include{bolum1}\n"
    if bildirim_nerede == "ana":
        ana += "\\bibliography{referans}\n"
    ana += "\\end{document}\n"
    yol = tmp_path / "0main.tex"
    yol.write_text(ana, encoding="utf-8")
    return ana, str(yol)


def test_find_bib_path_ana_dosyada(tmp_path):
    icerik, yol = _cok_dosyali_proje(tmp_path, "ana")
    assert latex_refs.find_bib_path(icerik, yol) == str(tmp_path / "referans.bib")


def test_find_bib_path_zincirdeki_bolumde(tmp_path):
    """Bildirim \\include edilen dosyada: ZİNCİR taranmalı."""
    icerik, yol = _cok_dosyali_proje(tmp_path, "bolum")
    assert latex_refs.find_bib_path(icerik, yol) == str(tmp_path / "referans.bib")


def test_find_bib_path_hicbir_yerde_yoksa_bos(tmp_path):
    icerik, yol = _cok_dosyali_proje(tmp_path, "yok")
    assert latex_refs.find_bib_path(icerik, yol) == ""


def test_zincirdeki_bildirimle_cite_anahtarlari_toplaniyor(tmp_path):
    """Otomatik tamamlamanın gördüğü yol: bildirim zincirdeyse de çalışmalı."""
    icerik, yol = _cok_dosyali_proje(tmp_path, "bolum")
    latex_refs._bib_chain_cache.clear()
    assert latex_refs.collect_cite_keys(icerik, yol) == ["a2020"]


def test_zincirdeki_bildirimle_denetim_sahte_uyari_uretmiyor(tmp_path):
    """Asıl bozulan buydu: .bib görünmeyince HER \\cite tanımsız sayılıyordu."""
    icerik, yol = _cok_dosyali_proje(tmp_path, "bolum")
    icerik = icerik.replace("\\end{document}", "\\cite{a2020}\n\\end{document}")
    latex_refs._bib_chain_cache.clear()
    rapor = latex_refs.audit_references(icerik, yol)
    assert rapor.undefined_cites == []


def test_ana_dosyadaki_bildirim_zincire_bakmadan_bulunuyor(tmp_path):
    """Sıcak yol korunmalı: 22 şablonun 19'unda bildirim ana dosyada.

    Zincir çözümlemesi 15 dosyalık bir tezde 16 ms (ölçüldü); \\cite
    tamamlaması her tuş vuruşunda çağırıyor. Ana dosyada bulunca zincire
    HİÇ inilmemeli.
    """
    icerik, yol = _cok_dosyali_proje(tmp_path, "ana")
    latex_refs._bib_chain_cache.clear()
    assert latex_refs.find_bib_path(icerik, yol)
    assert not latex_refs._bib_chain_cache, "ana dosyada bulundu ama zincir tarandı"


def test_zincir_sonucu_onbelleklenıyor(tmp_path):
    icerik, yol = _cok_dosyali_proje(tmp_path, "bolum")
    latex_refs._bib_chain_cache.clear()
    latex_refs.find_bib_path(icerik, yol)
    assert yol in latex_refs._bib_chain_cache

    # Önbellek TTL içinde diskteki değişikliği görmüyor; bu bilinçli bir
    # ödünç (zincirin mtime'ını anahtar yapmak zincirin kendisini çözmeyi
    # gerektirirdi). Süresi dolunca yeniden taranmalı.
    os.remove(tmp_path / "referans.bib")
    assert latex_refs.find_bib_path(icerik, yol) != ""      # bayat, beklenen
    latex_refs._bib_chain_cache[yol] = (
        time.time() - latex_refs._BIB_CHAIN_TTL - 1,
        latex_refs._bib_chain_cache[yol][1])
    assert latex_refs.find_bib_path(icerik, yol) == ""      # tazelendi
