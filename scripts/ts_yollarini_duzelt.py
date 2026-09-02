#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`.ts` içindeki `location` yollarını gerçek kaynak dosyalara çevirir.

`pylupdate6` lambda ile yazılmış `_()` çağrılarını göremiyor, bu yüzden
`update_translations.sh` kaynakları `mktemp -d` ile açılan geçici bir dizine
kopyalayıp dönüştürüyor (gerekçe: scripts/extract_tr.py). Ama pylupdate6
`location` satırlarına OKUDUĞU yolu yazıyor ve o dizinin adı her koşuda
değişiyor:

    <location filename="../../../../../../../../tmp/tmp.UyYLWT2AAZ/desktop/main.py" ... />
    <location filename="../../../../../../../../tmp/tmp.pVVrxTAZ6h/desktop/main.py" ... />

Sonuç: her çeviri güncellemesi ~1800 satırlık anlamsız bir diff üretiyor ve
gerçek değişiklik onun içinde kayboluyor. Ölçüldü (2026-09-02): e1796f6 1811
satır, 90a3b66 1820, 7c2bea5 1801; hepsi neredeyse tamamen bu yol değişimi.

Yollar `.ts` dosyasının bulunduğu `desktop/translations/` dizinine göre
yeniden yazılıyor, yani `../gui/main_window.py`. Böylece hem kararlı hem de
Qt Linguist'ten kaynağa atlanabilir hale geliyor; geçici dizin silindikten
sonra var olmayan bir yolu göstermiyor.
"""

import io
import re
import sys

# `.../<herhangi bir kök>/desktop/<gercek yol>` -> `../<gercek yol>`
_RE_KONUM = re.compile(r'(<location filename=")([^"]*?)/desktop/([^"]+)(")')


def duzelt(metin: str) -> "tuple[str, int]":
    sayac = 0

    def _degistir(m):
        nonlocal sayac
        sayac += 1
        return "%s../%s%s" % (m.group(1), m.group(3), m.group(4))

    return _RE_KONUM.sub(_degistir, metin), sayac


def main(yollar):
    for yol in yollar:
        metin = io.open(yol, encoding="utf-8").read()
        yeni, sayac = duzelt(metin)
        if yeni != metin:
            io.open(yol, "w", encoding="utf-8", newline="").write(yeni)
        print("  %s: %d konum" % (yol.split("/")[-1], sayac))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("kullanim: ts_yollarini_duzelt.py <dosya.ts> ...")
        sys.exit(2)
    main(sys.argv[1:])
