"""Projede arama işçisi — taramayı UI thread'inden kaldırır.

pdf_search_worker'ın kardeşi ve aynı yaşam döngüsü korumasında: tek uzun
ömürlü QThread, latest-wins TEK slot (aramada yalnız son sorgu anlamlıdır),
sonuçlar `search_id` ile damgalanır, `atexit` ile durdurulur.

NEDEN İŞÇİ. Ölçüldü (2026-08-31, 232 dosya / 4.8 MB'lık ağaç):

    Windows yerel diskte      : 39–90 ms
    WSL üzerinden /mnt/c'de   : 850–2250 ms

Yani maliyet dosya sistemine bağlı ve SINIRSIZ: proje `\\\\wsl.localhost\\...`
üzerinde ya da ağ paylaşımında olabilir, dosya sayısı da tezlerde birkaç
yüze çıkar. UI thread'inde koşturmak, bu turda kapatılan 1.7 sn'lik referans
denetimi donmasının aynısını yeniden üretirdi.

İPTAL: yeni sorgu gelince süren tarama DOSYA BAŞINA iptal edilir
(core.project_search.search_project'in `iptal` kancası). Yazarken art arda
Enter'a basmak taramaları üst üste yığmaz.
"""

import atexit
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from core.project_search import search_project

_alive_workers: set["ProjectSearchWorker"] = set()


def _stop_all_at_exit():
    for w in list(_alive_workers):
        try:
            w.stop()
            w.wait(6000)
        except Exception:
            pass


atexit.register(_stop_all_at_exit)


class ProjectSearchWorker(QThread):
    """Arka planda proje geneli metin araması."""

    # search_id, [Bulgu, ...], kesildi_mi
    found = pyqtSignal(int, list, bool)

    def __init__(self):
        super().__init__()
        self._cond = threading.Condition()
        self._stop = False
        # (search_id, kok, sorgu, buyuk_kucuk_duyarli)
        self._job: tuple[int, str, str, bool] | None = None

    # --- UI thread'inden ---

    def search(self, search_id: int, kok: str, sorgu: str, case_sensitive: bool):
        with self._cond:
            self._job = (search_id, kok, sorgu, case_sensitive)
            self._cond.notify_all()

    def stop(self):
        with self._cond:
            self._stop = True
            self._cond.notify_all()

    # --- işçi thread ---

    def run(self):
        _alive_workers.add(self)
        try:
            self._run_loop()
        finally:
            _alive_workers.discard(self)

    def _run_loop(self):
        while True:
            with self._cond:
                while not self._stop and self._job is None:
                    self._cond.wait()
                if self._stop:
                    return
                job, self._job = self._job, None

            search_id, kok, sorgu, cs = job
            iptal_edildi = False

            def _iptal():
                nonlocal iptal_edildi
                if self._stop:
                    iptal_edildi = True
                    return True
                with self._cond:
                    if self._job is not None:   # yeni sorgu geldi
                        iptal_edildi = True
                        return True
                return False

            try:
                bulgular, kesildi = search_project(
                    kok, sorgu, case_sensitive=cs, iptal=_iptal)
            except Exception:
                # Tarama hiçbir koşulda işçiyi düşürmemeli: kök silinmiş
                # olabilir, izin kalkmış olabilir. Boş sonuç dönmek, thread'i
                # kaybedip sonraki aramaların sessizce ölmesinden iyidir.
                bulgular, kesildi = [], False

            if iptal_edildi:
                continue        # bayat sonuç: yeni sorgu var ya da kapanıyoruz
            self.found.emit(search_id, bulgular, kesildi)
