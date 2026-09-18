"""Platform path dönüşümleri — Windows/WSL köprüsü."""

import logging
import os
import re

# Bu modül bilerek Qt'süz: core.log PyQt6'ya bağımlı, paths ise saf kalmalı.
_logger = logging.getLogger("latex_editor.paths")


def clean_child_env() -> dict:
    """AppImage gömülü kütüphane yollarından arındırılmış çocuk süreç ortamı.

    AppImage çalışma zamanı LD_LIBRARY_PATH/LD_PRELOAD ile kendi (eski)
    kütüphanelerini ortama yazar; bu ortamla başlayan sistem ikilileri
    (xelatex, pandoc, synctex) gömülü libstdc++'yi bulur ve
    "GLIBCXX_3.4.32 not found" ile düşer. Sistem aracı başlatan her
    subprocess'a env=clean_child_env() verilmeli.
    """
    return {k: v for k, v in os.environ.items()
            if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD")}


def dizin_altinda_mi(dizin: str, kok: str) -> bool:
    r"""``dizin`` gerçekten ``kok``un altında mı; kararı DOSYA SİSTEMİ verir.

    Yol dizgilerini karşılaştırmak yetmiyor: aynı dizin birden çok yazımla
    gösterilebiliyor. Harf duyarsız bir birimde ``TEZ`` ile ``tez``, sembolik
    bağ ya da kavşak varken de iki ayrı yol AYNI dizindir.

    NEDEN PLATFORM ADINA BAKILMIYOR. Standart çözüm ``os.path.normcase``
    ama o harfi YALNIZ Windows'ta indiriyor, POSIX'te kimlik işlevi. macOS
    POSIX olduğu hâlde öntanımlı APFS birimi harf DUYARSIZ, yani
    ``commonpath`` karşılaştırması orada yanlış cevap veriyor. ÖLÇÜLDÜ
    (2026-09-18, macos-15 koşucusu; iki ayrı çağrı yerinde birden):

        dosya sistemi harf duyarsız mı : True
        kök BÜYÜK yazımla sorulunca    : "kapsamıyor"  (oysa AYNI dizin)

    ``os.path.samefile`` aygıt + inode karşılaştırıyor, yani cevabı dosya
    sisteminin kendisi veriyor ve tahmine gerek kalmıyor. Dizinden köke
    doğru yürünüyor; kök bulunursa içeride demektir.

    İKİ ÇAĞRI YERİ VAR ve ikisi de aynı kusuru taşıyordu: "Klasörde Ara"nın
    kök uyarısı ve kabuk erişimi (minted) izninin yazıldığı anahtar. Ortak
    yer burası, çünkü iki kopya tutulsa biri düzeltilip öbürü unutulurdu.
    """
    try:
        if not os.path.isdir(kok):
            return False
        gecerli = os.path.abspath(dizin)
        onceki = None
        while gecerli and gecerli != onceki:
            try:
                if os.path.samefile(gecerli, kok):
                    return True
            except OSError:                 # okunamayan/silinmiş ara dizin
                pass
            onceki, gecerli = gecerli, os.path.dirname(gecerli)
    except OSError:
        return False
    return False


# Homebrew kendini `/etc/paths.d`e YAZMIYOR; PATH'e kullanıcının profiline
# eklediği `brew shellenv` satırıyla giriyor ve o da yalnız kabukta koşuyor.
# pandoc ile biber buradan geliyor. İkisi de: Apple Silicon, sonra Intel.
_MAC_EK_YOLLAR = ("/opt/homebrew/bin", "/usr/local/bin")


def _paths_d_girdileri(kok: str = "") -> list:
    """`/etc/paths` ve `/etc/paths.d/*` içindeki yollar, dosya sırasıyla.

    macOS'un `path_helper`ı PATH'i tam olarak bu dosyalardan kuruyor;
    burada yapılan onun okuduğu yerleri okumak. Böylece MacTeX'e özel bir
    ad gömülmüyor: oraya kaydolan her araç (TeX Live, MacPorts, ...)
    kendiliğinden geliyor.
    """
    import glob
    yollar = []
    for dosya in [kok + "/etc/paths"] + sorted(
            glob.glob(kok + "/etc/paths.d/*")):
        try:
            with open(dosya, encoding="utf-8", errors="replace") as f:
                for satir in f:
                    s = satir.strip()
                    if s and not s.startswith("#"):
                        yollar.append(s)
        except OSError:
            continue
    return yollar


def macos_path_tamamla(ortam=None, kok: str = "") -> str:
    r"""macOS'ta Finder'dan açılan uygulamanın PATH'ini tamamlar.

    MacTeX ikilileri `/Library/TeX/texbin`de duruyor ve o yol PATH'e
    `/etc/paths.d/TeX` üzerinden giriyor. O dosyaları `path_helper`
    okuyor ve path_helper YALNIZ GİRİŞ KABUKLARINDA koşuyor. Finder'dan
    ya da Dock'tan açılan bir `.app` launchd ortamını devralıyor, yani
    PATH `/usr/bin:/bin:/usr/sbin:/sbin` oluyor ve TeX görünmüyor.

    ÖLÇÜLDÜ (2026-09-18, macos-15 + BasicTeX, uygulamanın kendi arama
    mantığıyla `shutil.which`):

        giriş kabuğu                pdflatex -> /Library/TeX/texbin/pdflatex
        Finder'ın asgari PATH'i     pdflatex, lualatex, biber, synctex
                                    dördü de BULUNAMADI

    Kullanıcı MacTeX'i kurmuş olduğu hâlde "pdflatex kurulu değil" görüyor.

    Yollar SONA ekleniyor, başa değil: kullanıcının kendi PATH'indeki bir
    araç gölgelenmesin. Terminal'den açılışta girdiler zaten PATH'te
    olduğu için işlev hiçbir şey değiştirmiyor.

    Yalnız var olan dizinler ekleniyor: olmayan bir yol PATH'i
    şişirmekten başka bir şey yapmaz.
    """
    import sys
    ortam = os.environ if ortam is None else ortam
    mevcut = ortam.get("PATH", "")
    if sys.platform != "darwin":
        return mevcut
    var = [p for p in mevcut.split(os.pathsep) if p]
    eklenen = []
    for yol in _paths_d_girdileri(kok) + list(_MAC_EK_YOLLAR):
        tam = kok + yol if kok else yol
        if yol and yol not in var and os.path.isdir(tam):
            var.append(yol)
            eklenen.append(yol)
    yeni = os.pathsep.join(var)
    ortam["PATH"] = yeni
    if eklenen:
        _logger.info("macOS PATH tamamlandi: %s", ", ".join(eklenen))
    return yeni


# \\wsl.localhost\Ubuntu\... veya \\wsl$\Ubuntu\...  (dağıtım adı yutulur)
_RE_WSL_UNC = re.compile(r'^\\\\wsl(?:\$|\.localhost)\\[^\\]+(\\.*)?$', re.IGNORECASE)


def windows_to_wsl(windows_path: str) -> str:
    """Windows yolunu WSL yoluna çevir.

    C:\\Users\\...              -> /mnt/c/Users/...
    \\\\wsl.localhost\\Ubuntu\\ev -> /ev        (dağıtımın kendi dosya sistemi)
    \\\\sunucu\\paylasim\\...     -> DEĞİŞTİRİLMEDEN döner + uyarı loglanır

    Eskiden yalnız "X:" biçimi tanınıyordu; her UNC yolu ters eğik çizgiler
    düz çizgiye çevrilip olduğu gibi geçiyordu (\\\\sunucu\\paylasim\\tez.tex
    -> /sunucu/paylasim/tez.tex). Bu WSL'de var olmayan bir yol; hata da
    verilmediği için derleme "dosya bulunamadı" ile sessizce düşüyordu.
    Ağ paylaşımının WSL'de doğru bir karşılığı YOK (mount edilmedikçe), o
    yüzden uydurmak yerine yol korunuyor ve teşhis için log'a yazılıyor.
    """
    m = _RE_WSL_UNC.match(windows_path)
    if m:
        # WSL'in kendi dosya sistemi: \\wsl.localhost\Ubuntu\home\s -> /home/s
        return (m.group(1) or "\\").replace("\\", "/")

    if windows_path.startswith("\\\\") or windows_path.startswith("//"):
        _logger.warning(
            "Ağ (UNC) yolunun WSL karşılığı yok, olduğu gibi geçiliyor: %s",
            windows_path)
        return windows_path

    p = windows_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        return f"/mnt/{p[0].lower()}{p[2:]}"
    return p


# `\\wsl.localhost\<dağıtım>` kökü. `windows_to_wsl` bu öneki ATIYOR
# (dağıtımın kendi kökü `/`), yani geri çevrim onu tek başına üretemiyor;
# `ornek` bu yüzden gerekiyor.
_RE_WSL_KOK = re.compile(
    r'^(\\\\wsl(?:\$|\.localhost)\\[^\\]+)(?=\\|$)', re.IGNORECASE)


def wsl_to_windows(wsl_path: str, *, ornek: str = "") -> str:
    """/mnt/c/Users/... -> C:\\Users\\...

    ``ornek``: AYNI derlemeden bilinen bir Windows yolu (uygulamada PDF'in
    yolu). Verilirse `/mnt/` DIŞINDAKİ biçimler de geri çevrilebiliyor.

    Neden gerekli: proje WSL'in KENDİ dosya sisteminde durabiliyor
    (`\\\\wsl.localhost\\Ubuntu\\home\\x`) ve WSL belgeleri bunu zaten
    öneriyor, çapraz dosya sistemi erişimi yavaş olduğu için. İleri çevrim
    o biçimi biliyor, geri çevrim BİLMİYORDU: SyncTeX ters araması
    synctex'ten `/home/x/tez.tex` alıp Windows'a öyle veriyordu ve
    `main_window._goto_line` o yolu açamayıp sessizce vazgeçiyordu.
    ÜRETİLDİ (2026-09-12, WSL'in kendi dosya sisteminde derlenmiş gerçek
    bir belgeyle): ileri arama çalışıyor, satır numarası da doğru geliyor,
    ama kullanıcı PDF'te tıklayınca editörde hiçbir şey olmuyordu.

    Dağıtım adı ileri çevrimde atıldığı için burada ÖRNEKTEN alınıyor;
    uydurmak yanlış olurdu (kullanıcının birden çok dağıtımı olabilir).
    """
    m = re.match(r'^/mnt/([a-zA-Z])(/.*)$', wsl_path)
    if m:
        win_path = m.group(2).replace('/', '\\')
        return f"{m.group(1).upper()}:{win_path}"
    if ornek and wsl_path.startswith("/"):
        kok = _RE_WSL_KOK.match(ornek)
        if kok:
            return kok.group(1) + wsl_path.replace("/", "\\")
    return wsl_path
