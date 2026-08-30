"""pdfium çağrılarını serileştiren tek kilit.

pdfium THREAD-SAFE DEĞİLDİR. Bu uygulama ona ÜÇ ayrı thread'den dokunuyor:

    UI thread            — metin seçme, arama vurgusu, sayfa boyutu, bağlantı
                           altındaki imleç, sunum modu render'ı
    pdf_render_worker    — sayfa render'ı
    pdf_search_worker    — metin araması

Ayrı ``PdfDocument`` nesneleri kullanmak yetmiyor: kütüphane küresel durum
tutuyor, iki thread aynı anda içeri girince süreç segfault ile ölüyor.
CI'da gerçekten görüldü (run 33329685864, Python 3.10): render işçisi
``get_page`` içindeyken UI ``get_textpage`` içindeydi.

Kural: pdfium API'sine dokunan HER blok bu kilidi almalı — belge açma/kapama
dahil. Kilit RLock, çünkü iç içe çağrılar var (ör. _show_search_result
kendi bloğunu alır, sonra _draw_search_highlight'ı çağırır).

DİKKAT — kilidi TUTARKEN bir işçinin bitmesini BEKLEME. ``shutdown()``
thread'e join atıyor; kilit elde tutulursa işçi kendi pdfium çağrısını
tamamlayamaz ve kilitlenme olur. Bekleme yolları bilerek kilitsizdir.

Blokta tutulan süre kısa olmalı: işçiler kilidi SAYFA BAŞINA alır, parti
başına değil — yoksa UI uzun bir render partisi boyunca donardı.
"""

import threading

pdfium_lock = threading.RLock()
