"""Qt'nin Türkçe kataloğunda karşılığı kalmamış kutu metinleri.

Linux'ta yerel dosya kutusu yoksa (KDE, WSLg gibi masaüstleri) Qt kendi
kutusunu açıyor. Qt 6.11 o kutunun iki etiketine kısayol harfi ekledi
("&Look in:", "Files of &type:"); PyQt6 ile gelen qtbase_tr.qm ise hâlâ eski
metinleri ("Look in:", "Files of type:") çeviriyor, yani eşleşme yok.
Ölçüldü (2026-09-29, AppImage 1.1.2, WSLg): Türkçe arayüzde bu iki etiket
İngilizce, kutunun geri kalanı Türkçe.

Qt bu metinleri "QFileDialog" bağlamında KENDİSİ soruyor ve yüklü bütün
kataloglara bakıyor. Bu dosya çalışma anında içe aktarılmıyor; yalnız
çeviri çıkarımı için var: metinler latexeditor_*.ts'e o bağlamda giriyor.
Türkçe karşılıkları .ts'te ELLE yazılı (update_translations.sh bitmemiş
Türkçe girdileri kaynak metinle dolduruyor, o da burada İngilizce olurdu).
"""

from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("QFileDialog", s)

METINLER = (_("&Look in:"), _("Files of &type:"))
