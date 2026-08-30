"""Testlerin Windows'ta da koşabilmesi için taşınabilirlik kapıları.

Depo WSL öncelikli geliştiriliyor ve CI yalnız Linux'ta koşuyor; bu yüzden
Windows'a özgü kırılmalar sessizce birikiyordu. Somut sonuç: `encoding=`
verilmeyen dosya çağrıları Türkçe Windows'ta cp1254'e düşüyor, testler ya
mojibake ile patlıyor ya da — bir kez gerçekten olduğu gibi — ürünün
"bu dosya UTF-8 değil" modal uyarısını tetikleyip başsız koşuyu SONSUZA DEK
askıda bırakıyordu.

Buradaki test o sınıfı kapatır: yeni bir test dosyası aynı tuzağa düşerse
Linux'ta da kırmızı yanar, Windows'a gitmeye gerek kalmaz.

(POSIX mutlak yolu gömen testler de Windows'ta kırılıyor — ama onu sayım
tabanlı bir kapıyla korumayı denedim ve bıraktım: alakasız düzenlemelerde
kırılan, bakımı derde dönen bir kapı oluyor. Onun gerçek koruması testleri
arada bir Windows'ta koşmak.)
"""

import ast
import pathlib
import subprocess

_REPO = pathlib.Path(__file__).resolve().parents[1]

# İkili (binary) mod: kodlama zaten anlamsız.
_METIN_METOTLARI = {"write_text", "read_text"}
_SUREC_METOTLARI = {"run", "check_output", "Popen"}


def _test_dosyalari() -> list[pathlib.Path]:
    ciktilar = subprocess.run(["git", "ls-files", "tests"], cwd=_REPO,
                              capture_output=True, text=True,
                              encoding="utf-8", check=True).stdout.split()
    return [_REPO / r for r in ciktilar if r.endswith(".py")]


def _ikili_mod(node: ast.Call) -> bool:
    """open(..., 'rb') gibi ikili çağrı mı? Belirsizse True (kapı zorlamaz)."""
    mod = node.args[1] if len(node.args) >= 2 else None
    for kw in node.keywords:
        if kw.arg == "mode":
            mod = kw.value
    if mod is None:
        return False
    if isinstance(mod, ast.Constant) and isinstance(mod.value, str):
        return "b" in mod.value
    return True


def _kodlamasiz(yol: pathlib.Path):
    """(satır, çağrı) — encoding= almayan metin dosyası/süreç çağrıları."""
    tree = ast.parse(yol.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in _METIN_METOTLARI:
            yield node.lineno, f"{f.attr}()"
        elif isinstance(f, ast.Name) and f.id == "open" and not _ikili_mod(node):
            yield node.lineno, "open()"
        elif isinstance(f, ast.Attribute) and f.attr in _SUREC_METOTLARI:
            kw = {k.arg for k in node.keywords}
            if "text" in kw or "universal_newlines" in kw:
                yield node.lineno, f"subprocess.{f.attr}(text=True)"


def test_dosya_cagrilari_encoding_belirtir():
    """tests/ içinde encoding= vermeyen metin dosyası çağrısı olmamalı.

    Kırılırsa: ilgili satıra encoding="utf-8" ekleyin. Türkçe Windows'ta
    varsayılan cp1254'tür ve testin yazdığı içerik ürün tarafından UTF-8
    olmayan dosya sayılır.
    """
    eksik = [(y.relative_to(_REPO).as_posix(), ln, ne)
             for y in _test_dosyalari() for ln, ne in _kodlamasiz(y)]
    assert not eksik, (
        "encoding= verilmeyen çağrılar (Windows'ta cp1254'e düşer):\n"
        + "\n".join(f"  {f}:{ln}  {ne}" for f, ln, ne in eksik))
