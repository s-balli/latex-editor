"""PDF'ten çıkarılan metnin onarımı: Qt'süz saf katman.

Buradaki tek iş, OT1 belgelerde AYRI glif olarak basılan aksanları harfleriyle
birleştirmek. İKİ tüketicisi var ve ikisi de aynı bilgiye muhtaç:

    pdf_viewer_mixins/_selection  seçilen metni panoya kopyalarken
    pdf_search_worker             belge içinde arama yaparken

Gövde eskiden yalnız seçim mixin'inde duruyordu; arama yolu pdfium'un kendi
``textpage.search()``ini ham sorguyla çağırıyor, yani aksanların ayrık
olduğunu HİÇ bilmiyordu. ÖLÇÜLDÜ (2026-09-12, 58 gerçek PDF + aynı adlı
kaynak): ayrık aksanlı 7 belgede kaynakta geçen 174 Türkçe kelimenin 86'sı
aramada bulunamıyordu; metin burada onarılınca 50'si bulunuyor ve pdfium'un
bulduğu tek bir kelime bile kaybolmuyor.
"""

import unicodedata

# OT1 belgelerde ayrı glif olarak basılan aksanların BİRLEŞTİRİCİ karşılığı.
# Anahtarlar ARALIKLI (spacing) karakterler; NFC onları kendiliğinden
# birleştirmiyor, o yüzden elle karşılığa çevriliyor. Ters vurgu (`) ve düz
# tırnak BİLEREK yok: kod örneklerinde ve tırnak işaretlerinde geçiyorlar ve
# metni bozardı.
_AKSAN_BIRLESIK = {
    "¸": "̧",   # ¸  sedil        -> ç, ş
    "˘": "̆",   # ˘  breve        -> ğ
    "¨": "̈",   # ¨  iki nokta    -> ö, ü
    "˙": "̇",   # ˙  üstte nokta  -> İ
    "ˆ": "̂",   # ˆ  şapka        -> â, î
    "˜": "̃",   # ˜  tilde        -> ñ
}

# Büyük harfte BİLE aksanın harften ÖNCE geldiği ölçülen aksanlar. Sedil,
# breve ve iki nokta büyük harfte harften SONRA geliyor (`S¸`, `O¨`), üstte
# nokta ise ÖNCE (`˙I` -> İ). Ayrım harf sırasından değil AKSANDAN çıkıyor ve
# ölçümden geldi: bu liste olmadan `S˙I` dizisindeki nokta S'ye bağlanıp
# `Ṡ` uyduruluyordu (U+1E60 Unicode'da var), oysa İ'ye ait.
_ONE_BAGLANAN = {"˙", "ˆ", "˜"}


def _aksan_uygula(taban: str, birlesik: str) -> str:
    """``taban`` + aksan GERÇEK bir harfse onu döndür, değilse "".

    Birleştirmenin ölçütü "sonuç TEK karakter mi": olmayan harf uydurmayı
    engelliyor ve aksanın hangi harfe ait olduğu ikilemini kendiliğinden
    çözüyor. `l¸c` dizisinde `l`+sedil diye bir harf YOK, `c`+sedil VAR.

    Noktasız `ı` LaTeX'in aksan TABANI: `\\^{\\i}` ile yazılan harf î'dir ve
    PDF'e noktasız glif + şapka olarak düşüyor (ölçüldü: "resmî" ->
    "resmˆı"). Noktasız ı ile şapkanın birleşiği Unicode'da yok, o yüzden
    taban noktalı `i`ye çevrilip yeniden deneniyor. Büyük `I` için böyle bir
    kural YOK: `I`+nokta ve `I`+şapka zaten birleşiyor, uydurma bir nokta
    eklemek kaynakta olmayan bir harf üretirdi.
    """
    if not taban:
        return ""
    for t in (taban, "i" if taban == "ı" else ""):
        if not t:
            continue
        aday = unicodedata.normalize("NFC", t + birlesik)
        if len(aday) == 1:
            return aday
    return ""


def aksanlari_birlestir(text: str) -> tuple[str, list[tuple[int, int]] | None]:
    """Ayrık aksanları harfleriyle birleştir; metni VE indis haritasını döndür.

    Harita, üretilen metindeki her karakter için onu üreten HAM aralığı
    ``(baş, bit)`` olarak veriyor. Arama yolu buna mecbur: pdfium vurguyu
    ham karakter indisiyle çiziyor (``get_charbox``), onarılmış metindeki
    indis ise kaymış oluyor.

    Onaracak bir şey yoksa metin OLDUĞU GİBİ ve harita ``None`` dönüyor;
    ``None`` "indisler zaten ham metnin indisleri" demek. Kısa yol ŞART:
    gövde karakter karakter dönen bir Python döngüsü ve arama HER sorguda
    HER sayfa için çağrılıyor. ÖLÇÜLDÜ (2026-09-12, beş sorgu, tüm sayfalar):

        56 sayfalık ders notu (aksansız)   kısa yol yokken 65.0 ms
                                           kısa yolla      1.8 ms
                                           pdfium'un kendi 3.7 ms
        25 sayfalık tez (AYRIK aksanlı)    onarım çalışıyor 21.5 ms
                                           pdfium'un kendi  2.1 ms

    Yani aksansız belgede pdfium'dan hızlı, aksanlı belgede sorgu başına
    ~4 ms daha yavaş; arama zaten arka plan işçisinde koşuyor.

    KURAL, ÖLÇÜMDEN ÇIKTI. Aksanın hangi harfe ait olduğu tek yönlü değil:
    küçük harflerde aksan harften ÖNCE geliyor (`¸s`), büyük harflerde SONRA
    (`S¸`). Sıraya bakarak karar vermek `¨` yüzünden yanlış harf üretiyordu
    (`UN¨` -> N + iki nokta). Onun yerine BİRLEŞTİRİLEBİLİRLİK soruluyor:
    sonuç TEK karakter değilse o bağ kurulmuyor. Böylece `l¸c` ikilemi
    kendiliğinden çözülüyor ve olmayan harf uydurulmuyor. Eşi bulunamayan
    aksan metinde artık bırakılmıyor.

    Büyük harflerin arasına giren boşluklar (`C¸ ALIS¸MA` -> `Ç ALIŞMA`)
    BURADA ÇÖZÜLMÜYOR: aksan bazen harfinden birkaç karakter uzağa düşüyor
    (`O¨GRENC ˘ ˙I`) ve boşluk silmek gerçek sözcük sınırlarını da
    birleştirirdi.

    NFC BURADA HİÇ uygulanmıyor: toplu NFC uzunluğu değiştirip haritayı
    geçersiz kılardı, karakter karakter uygulamak ise yalnız tekil
    dönüşümleri (U+212B gibi) yakalayabilirdi ve bedeli her karakterde bir
    `normalize` çağrısıydı. Ölçüldü (585 gerçek PDF sayfası): toplu NFC
    yalnız 1 sayfada bir şey değiştiriyor. Panoya kopyalanan metin NFC'ye
    ihtiyaç duyuyor ve onu `birlesik_metin` uyguluyor.
    """
    if not any(a in text for a in _AKSAN_BIRLESIK):
        return text, None
    out: list[str] = []
    harita: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        birlesik = _AKSAN_BIRLESIK.get(text[i])
        if birlesik is None:
            out.append(text[i])
            harita.append((i, i + 1))
            i += 1
            continue
        sonraki = text[i + 1] if i + 1 < n else ""
        onceki = out[-1] if out else ""
        # a) SONRAKİ harf KÜÇÜKSE ona bağla: küçük harflerde ölçülen sıra
        #    bu. Büyük harfte önceliği tersine çevirmek ŞART, yoksa
        #    `S¸EK˙IL`de sedil E'ye gidiyor (`Ȩ` Unicode'da VAR) ve `Ş`
        #    kaybediliyor. Ölçüldü: sıra denenirken bu gerileme çıktı.
        one = sonraki.islower() or text[i] in _ONE_BAGLANAN
        aday = _aksan_uygula(sonraki, birlesik) if one else ""
        if aday:
            out.append(aday)
            harita.append((i, i + 2))
            i += 2
            continue
        # b) ÖNCEKİ harfe bağla: büyük harflerde ölçülen sıra
        aday = _aksan_uygula(onceki, birlesik)
        if aday:
            out[-1] = aday
            harita[-1] = (harita[-1][0], i + 1)
            i += 1
            continue
        # c) Son deneme: sonraki harf büyük olabilir (`˙Istanbul`)
        aday = _aksan_uygula(sonraki, birlesik)
        if aday:
            out.append(aday)
            harita.append((i, i + 2))
            i += 2
            continue
        # d) Eşi yok: artık bırakma
        i += 1
    return "".join(out), harita


def birlesik_metin(text: str) -> str:
    """Panoya kopyalanacak hâl: birleştir, sonra metnin tamamını NFC'ye indir.

    Harita gerekmediği için toplu NFC burada serbest ve gerekli: kopyalanan
    metin başka programlara gidiyor, orada birleşik biçim bekleniyor.
    """
    if not any(a in text for a in _AKSAN_BIRLESIK):
        return unicodedata.normalize("NFC", text)
    return unicodedata.normalize("NFC", aksanlari_birlestir(text)[0])
