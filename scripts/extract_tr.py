#!/usr/bin/env python3
"""Çevrilebilir dizgeleri AST ile çıkar; pylupdate6'nın okuyabileceği dosya üret.

Neden gerekli
-------------
Kod tabanı çeviriyi ``_ = lambda s: QCoreApplication.translate("Ctx", s)``
kısayoluyla yapıyor. pylupdate6 lambda'nın arkasını göremediği için ``_()``
çağrılarını tanımaz; bu yüzden kaynak dosyalar kataloğa verilmeden önce
``_("x")`` → ``QCoreApplication.translate("Ctx", "x")`` biçimine çevrilir.

Bu dönüşüm eskiden tek satırlık bir regex'ti::

    _\\("((?:[^"\\\\]|\\\\.)*)"\\)

Regex satır sonunda durduğu için ÇOK SATIRLI çağrılar (örtük dizge
birleştirme) hiç eşleşmiyordu::

    msg = _(
        "{fname} dosyası diskte değiştirildi.\\n\\n"
        "Kaydedilmemiş yerel değişiklikleriniz var."
    )

Bu çağrılar dönüştürülmeyince pylupdate6 onları görmüyor, katalogdan
``type="vanished"`` olarak düşüyorlardı: uygulama İngilizceye alınsa bile o
dialoglar Türkçe kalıyordu. Sessizdi — CI yalnız ``unfinished`` sayıyor,
``vanished``'ı görmüyordu. (Kaybolan 4 dizge: kodlama uyarısı, "dosya diskte
değişti" istemi ve sürüm geri yükleme onayı.)

Nasıl çalışıyor
---------------
Metin üzerinde oynamak yerine kaynak ``ast`` ile ayrıştırılır ve tek dizge
sabiti alan her ``_()`` çağrısı toplanır. Örtük birleştirme ayrıştırıcı
tarafından zaten tek bir ``Constant`` düğümüne indirgendiği için çok satırlı
çağrı ek iş gerektirmez.

Çıktı, kaynağın metinsel bir kopyası DEĞİL: yalnız ``translate()``
çağrılarından oluşan sentetik bir modül. Böylece f-string içindeki çağrılarda
tırnak çakışması (regex sürümünün "Invalid syntax" verdiği durum) ve iç içe
parantez sorunları baştan imkânsız hâle gelir; ``repr()`` her dizgeyi geçerli
tek satırlık bir Python sabitine çevirir.

Her çağrı ÖZGÜN satır numarasına yazılır (aradaki satırlar boş bırakılır);
böylece .ts dosyasındaki ``<location line="...">`` bilgisi kaynakla
eşleşmeye devam eder ve çevirmen bağlamı bulabilir.

Kullanım:
    python3 scripts/extract_tr.py <kaynak.py> <hedef.py>

Çıktı (stderr): çıkarılamayan ``_()`` çağrıları uyarı olarak listelenir —
değişken alan çağrılar (``_(mesaj)``) çeviriye giremez.
"""

import ast
import sys

# Bağlam adını taşıyan kalıp: _ = lambda s: QCoreApplication.translate("Ctx", s)
_LAMBDA_ADI = "_"


def bul_baglam(tree: ast.Module) -> str:
    """``_ = lambda s: QCoreApplication.translate("Ctx", s)`` içinden "Ctx"i al."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == _LAMBDA_ADI for t in node.targets):
            continue
        if not isinstance(node.value, ast.Lambda):
            continue
        govde = node.value.body
        if (isinstance(govde, ast.Call) and govde.args
                and isinstance(govde.args[0], ast.Constant)
                and isinstance(govde.args[0].value, str)):
            return govde.args[0].value
    return ""


def topla(tree: ast.Module) -> tuple[list[tuple[int, str]], list[int]]:
    """(satır, metin) çiftleri ve çıkarılamayan çağrıların satırları."""
    bulunan: list[tuple[int, str]] = []
    atlanan: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == _LAMBDA_ADI):
            continue
        if (len(node.args) == 1 and not node.keywords
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            bulunan.append((node.lineno, node.args[0].value))
        else:
            # _(degisken) / _(a, b): sabit olmadığı için kataloğa giremez.
            atlanan.append(node.lineno)
    return bulunan, atlanan


def uret(baglam: str, bulunan: list[tuple[int, str]]) -> str:
    """Sentetik modül: her çağrı kendi özgün satırında."""
    if not bulunan:
        return ""
    satirlar: dict[int, list[str]] = {}
    for lineno, metin in bulunan:
        satirlar.setdefault(lineno, []).append(
            f"QCoreApplication.translate({baglam!r}, {metin!r})")
    son = max(satirlar)
    # Aynı satırda birden çok çağrı olabilir; ';' ile ayrılmış ifadeler geçerli.
    return "\n".join("; ".join(satirlar.get(i, [])) for i in range(1, son + 1)) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"kullanım: {argv[0]} <kaynak.py> <hedef.py>", file=sys.stderr)
        return 2
    kaynak_yolu, hedef_yolu = argv[1], argv[2]
    with open(kaynak_yolu, encoding="utf-8") as f:
        kaynak = f.read()
    try:
        tree = ast.parse(kaynak, filename=kaynak_yolu)
    except SyntaxError as e:
        print(f"{kaynak_yolu}: ayrıştırılamadı: {e}", file=sys.stderr)
        return 1

    baglam = bul_baglam(tree)
    if not baglam:
        # Çeviri kısayolu tanımlanmamış: çıkarılacak bir şey yok.
        with open(hedef_yolu, "w", encoding="utf-8") as f:
            f.write("")
        return 0

    bulunan, atlanan = topla(tree)
    with open(hedef_yolu, "w", encoding="utf-8") as f:
        f.write(uret(baglam, bulunan))

    for lineno in atlanan:
        print(f"{kaynak_yolu}:{lineno}: uyarı: _() çağrısı sabit dizge almıyor, "
              f"çeviriye giremez", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
