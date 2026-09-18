r"""Testlerin kullanabilecegi GERCEKTEN calisan bir `bash` bul.

NEDEN AYRI DOSYA. Bu bilgi `test_paketleme.py` icinde dogmustu ve orada
kaldi; `test_derle_sh.py` ile `test_synctex_live.py` duz `"bash"` cagirmaya
devam etti. Sonuc, WSL kurulu bir Windows makinesinde (yani onerdigimiz
kurulumda) OLCULDU (2026-09-18, MiKTeX + WSL):

    test_derle_sh.py       57 dusen
    test_synctex_live.py    7 hata

Hicbiri gercek bir kusur degildi: hepsi ayni satirdan geliyordu,

    /bin/bash: C:UserssechoDesktop...derle.sh: No such file or directory

Ayni makinede betik Git Bash ile SORUNSUZ derliyor (PDF ve .synctex.gz
uretiliyor). Yani kapilar kirmizi yaniyordu ve gercek bir gerileme bu
gurultunun icinde gorunmezdi.

WINDOWS'TA NEDEN PATH YETMIYOR. `subprocess.run(["bash", ...])` sonunda
`CreateProcess` cagriliyor ve onun arama sirasinda System32, PATH'ten
ONCE geliyor. `C:\WINDOWS\system32\bash.exe` (WSL'in shim'i) orada
durdugu icin PATH'in basina Git Bash konsa bile "bash" yine WSL'e
gidiyor (olculdu: Git\bin PATH'in basindayken de ayni 57 test dustu).
Bu yuzden ikilinin TAM YOLU verilmek zorunda.
"""

import functools
import os
import shutil
import subprocess
import tempfile


def _bash_adaylari():
    adaylar = []
    bulunan = shutil.which("bash")
    if bulunan:
        adaylar.append(bulunan)
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    adaylar += [os.path.join(pf, "Git", "bin", "bash.exe"),
                os.path.join(pf, "Git", "usr", "bin", "bash.exe")]
    return adaylar


def _bash_calisiyor_mu(aday: str) -> bool:
    """Aday bash, testlerin ondan İSTEDİĞİ şeyi yapabiliyor mu.

    Eskiden `-c "echo ok"` sınanıyordu ve bu YETMİYOR: WSL'in bash'i
    (C:\\WINDOWS\\system32\\bash.exe) dağıtım kuruluyken bunu sorunsuz
    geçiyor, ama testlerin verdiği `C:\\...` biçimli betik yolunu açamıyor:
    `/mnt/c/...` bekliyor, sonuç exit 127 "No such file or directory".
    Yani aday seçiliyor, sonra üç TestYayinNotu testi düşüyordu; WSL kurulu
    HER Windows makinesinde. CI bunu yapısal olarak göremiyor çünkü runner
    imajında dağıtım yok (bkz. ci.yml'deki "WSL durumu" adımı).

    Bu yüzden sonda artık gerçek bir betiği YERLİ YOLUYLA çalıştırıyor.
    Elenen aday `calisan_bash()` döngüsünde atlanıyor ve sıra Git Bash'e
    geliyor; o Windows yollarını açabildiği için testler atlanmak yerine
    KOŞUYOR.
    """
    if not aday or not os.path.exists(aday):
        return False
    with tempfile.TemporaryDirectory() as gecici:
        betik = os.path.join(gecici, "sonda.sh")
        # Satır sonu LF olmalı: CRLF'te bash `$'\r'` diye takılır.
        with open(betik, "wb") as f:
            f.write(b"echo ok\n")
        try:
            r = subprocess.run([aday, betik], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=60)
        except OSError:
            return False
    return r.returncode == 0 and (r.stdout or "").strip() == "ok"


@functools.lru_cache(maxsize=1)
def calisan_bash():
    """GERÇEKTEN çalışan bir bash bul; yoksa None.

    `shutil.which("bash")` Windows'ta System32'deki WSL SHIM'ini bulabiliyor.
    Dağıtım kurulu değilse o shim UTF-16LE bir "wsl --install -d <Distro>"
    mesajı basıp 1 döndürür, verilen betiği hiç çalıştırmadan. GitHub'ın
    windows-latest runner'ında birebir bu oldu (2026-08-31, run 33374248471):
    üç test "assert 1 == 0" ile düştü, hata metni NUL dolu geldi. Bu yüzden
    adı bulmak yetmiyor, ÇALIŞTIĞI sınanıyor.
    """
    for aday in _bash_adaylari():
        if _bash_calisiyor_mu(aday):
            return aday
    return None
