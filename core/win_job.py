# -*- coding: utf-8 -*-
"""Windows Job Object yardımcısı: uygulama ölünce wsl.exe sahipsiz kalmasın.

NE OLUYORDU (2026-11-17'de gerçek exe'de ölçüldü, Claude'un denemesi;
bu modül o ölçümün düzeltmesi): sonsuz döngüye giren belge derlenirken
uygulama `taskkill /F` ile öldürülünce zaman aşımı zamanlayıcısı da
ölüyor; derlemeyi taşıyan wsl.exe ve WSL içindeki pdflatex %100 CPU ile
40+ sn koşmaya devam etti, kendiliğinden durmadı. Dıştaki wsl.exe elle
öldürülünce WSL içindeki ağaç ~4 sn'de düştü. Yani wsl.exe'yi uygulamanın
ölümüne bağlamak yeterli; çekirdekten başkasına (bekçi süreç, derle.sh'e
trap) gerek yok.

ÇÖZÜM: wsl.exe'yi JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE bayraklı bir Job
Object'e atamak. Job tutamacı bu süreçte modül düzeyinde BİR KEZ açılır
ve KASITLI kapatılmaz; uygulama herhangi bir biçimde ölünce (çökme,
taskkill) çekirdek son tutamacı kapatır ve job'daki süreçleri (wsl.exe,
torunları) öldürür. Job'a giren sürecin sonradan doğan torunları da
job'a girer.

SIGORTADIR, akış değil: atama başarısız olursa (eski Windows, süreç
çoktan bitmiş, uygulama iç içe atamaya izin vermeyen bir job'un içinde)
istisna fırlatılmaz, sebep günlüğe yazılır, derleme OLDUĞU GİBİ sürer.
kill-on-close yalnız tutamacın kapanışında (uygulama ölümünde) devreye
girer; normal derleme, Durdur ve zaman aşımı davranışı etkilenmez.

Windows dışında modül içe aktarılabilir ama hiçbir şey yapmaz
(ctypes.windll Windows'a özeldir; çağrılar no-op'tur). derle.sh'e HUP
trap'i EKLENMEZ, ağacın düşme biçimi ölçüldü (bkz. core/compiler.py
`_sureci_oldur`); yerli yolun bekçi deseni (LATEX_EDITOR_PID) Windows'a
taşınmaz.

Testler: tests/test_win_job.py.
"""

import ctypes
import sys

from core.log import get_logger

_logger = get_logger("win_job")

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # İmzalar AÇIKÇA: verilmezse ctypes Python tamsayısını C int'e (32 bit)
    # çevirir ve 64 bitlik tutamaç kırpılır. c_void_p genişlikten bağımsız
    # tutamacı taşır.
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [
        ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.AssignProcessToJobObject.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    class _IO_SAYACLARI(ctypes.Structure):
        """IO_COUNTERS (winnt.h)."""
        _fields_ = [(ad, ctypes.c_ulonglong) for ad in (
            "ReadOperationCount", "WriteOperationCount",
            "OtherOperationCount", "ReadTransferCount",
            "WriteTransferCount", "OtherTransferCount")]

    class _TEMEL_LIMIT(ctypes.Structure):
        """JOBOBJECT_BASIC_LIMIT_INFORMATION (winnt.h)."""
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", ctypes.c_ulong),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_ulong),
            ("Affinity", ctypes.c_size_t),       # ULONG_PTR
            ("PriorityClass", ctypes.c_ulong),
            ("SchedulingClass", ctypes.c_ulong),
        ]

    class _GENIS_LIMIT(ctypes.Structure):
        """JOBOBJECT_EXTENDED_LIMIT_INFORMATION (winnt.h)."""
        _fields_ = [
            ("BasicLimitInformation", _TEMEL_LIMIT),
            ("IoInfo", _IO_SAYACLARI),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    # winbase.h / winnt.h sabitleri
    _GENIS_LIMIT_BILGISI = 9        # JobObjectExtendedLimitInformation
    _KILL_ON_JOB_CLOSE = 0x2000     # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100     # AssignProcessToJobObject istiyor

    _job_tutamac = None             # süreç başına bir kez açılır, kapanmaz


def _job_al():
    """KILL_ON_JOB_CLOSE bayraklı job'u döndür; gerekirse bir kez yarat.

    Başarısızlıkta OSError fırlatır (çağıran günlüğe yazıp sürer); tutamac
    yaratılamadıysa sonraki derleme yeniden dener.
    """
    global _job_tutamac
    if _job_tutamac:
        return _job_tutamac
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
    bilgi = _GENIS_LIMIT()
    bilgi.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
            job, _GENIS_LIMIT_BILGISI, ctypes.byref(bilgi),
            ctypes.sizeof(bilgi)):
        kod = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        raise OSError(kod, "SetInformationJobObject")
    _job_tutamac = job
    return job


def sureci_joba_ata(pid: int) -> bool:
    """Süreci (torunlarıyla) ömrü bizimkine bağlanan job'a ata.

    Dönüş False: atama yapılamadı, sebep günlükte. İstisna FIRLATMAZ;
    job yalnız uygulama ölürken devreye giren bir sigortadır, derlemenin
    kendi akışı değildir.
    """
    if not IS_WINDOWS:
        return False
    try:
        job = _job_al()
    except OSError as e:
        _logger.warning("job açılamadı, wsl.exe sahipsiz kalabilir: %s", e)
        return False
    surec = kernel32.OpenProcess(_PROCESS_TERMINATE | _PROCESS_SET_QUOTA,
                                 False, pid)
    if not surec:
        _logger.warning("OpenProcess(%s) başarısız (winerror %s); "
                        "job ataması atlandı, derleme sürüyor",
                        pid, ctypes.get_last_error())
        return False
    try:
        if not kernel32.AssignProcessToJobObject(job, surec):
            _logger.warning("AssignProcessToJobObject(%s) başarısız "
                            "(winerror %s); derleme sürüyor",
                            pid, ctypes.get_last_error())
            return False
        return True
    finally:
        # Süreç tutamacı kapanabilir: atama kalır, iş bitmiştir.
        kernel32.CloseHandle(surec)
