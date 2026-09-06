"""LaTeX Editor — giriş noktası."""

import os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, '..'))

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.i18n import init as init_i18n
from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("App", s)
from gui.main_window import MainWindow
from gui.single_instance import SingleInstance


def _register_file_association():
    """Windows: .tex dosyalarını 'Birlikte Aç' listesine ekle."""
    if not getattr(sys, 'frozen', False):
        return

    if sys.platform == 'win32':
        try:
            import winreg
            exe_path = os.path.normpath(sys.executable)
            # İkon dosyasını AppData'ya kopyala
            app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
            os.makedirs(app_data, exist_ok=True)
            icon_path = os.path.join(app_data, 'latex-file-icon.ico')
            src_icon = os.path.join(sys._MEIPASS, 'linux', 'latex-file-icon.ico')
            if os.path.isfile(src_icon) and not os.path.isfile(icon_path):
                import shutil
                shutil.copy2(src_icon, icon_path)
            # Kendi ProgID'mizi kaydet
            prog_id = "LaTeXEditor.tex"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}") as key:
                winreg.SetValue(key, None, winreg.REG_SZ, "LaTeX Editor Document")
                with winreg.CreateKey(key, "DefaultIcon") as icon_key:
                    winreg.SetValue(icon_key, None, winreg.REG_SZ, icon_path)
                with winreg.CreateKey(key, "shell\\open\\command") as cmd_key:
                    winreg.SetValue(cmd_key, None, winreg.REG_SZ, f'"{exe_path}" "%1"')
            # OpenWithProgids — varsayılanı değiştirmez, sadece listeye ekler
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\.tex\\OpenWithProgids") as key:
                winreg.SetValueEx(key, prog_id, 0, winreg.REG_NONE, b"")
            # NOT: Buradan, .tex'in AKTİF ProgID'sinin (UserChoice) DefaultIcon'unu
            # bizim ikonumuzla ezen bir blok kaldırıldı. .tex başka bir editöre
            # (TeXstudio, VS Code...) bağlıysa o uygulamanın kayıt defteri
            # girdisini değiştiriyordu: HKCU, HKLM'i ezdiği için dosyalar bizim
            # ikonumuzla görünüp o programda açılıyordu ve geri alınmıyordu.
            # Kendi ProgID'mizin ikonunu ayarlamak (yukarıda) meşru; başkasınınkini
            # değiştirmek değil.
        except Exception:
            pass

    elif sys.platform == 'linux':
        try:
            import shutil
            # AppImage gerçek yolunu bul
            exe_path = os.environ.get('APPIMAGE', os.path.abspath(sys.executable))
            app_dir = sys._MEIPASS
            apps_dir = os.path.expanduser("~/.local/share/applications")
            icons_dir = os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps")
            mime_icons_dir = os.path.expanduser("~/.local/share/icons/hicolor/256x256/mimetypes")
            os.makedirs(apps_dir, exist_ok=True)
            os.makedirs(icons_dir, exist_ok=True)
            os.makedirs(mime_icons_dir, exist_ok=True)
            # .desktop dosyası oluştur
            desktop_path = os.path.join(apps_dir, "latex-editor.desktop")
            # Exec TIRNAKLANIYOR. Desktop Entry şartnamesi bu alanı boşluğa
            # göre argümanlara ayırıyor; AppImage kullanıcının indirdiği yerden
            # çalışıyor ve "~/Downloads/LaTeX Editor.AppImage" gibi boşluklu bir
            # yol sıradan. Tırnaksızken program adı ikiye bölünüyordu (ölçüldü
            # 2026-09-06: "/home/k/Downloads/LaTeX" + "Editor.AppImage"), yani
            # çift tıklama hiçbir şey açmıyordu. Windows dalı (yukarıda) aynı
            # dersi zaten biliyor: f'"{exe_path}" "%1"'.
            # Şartname tırnak içinde şu dördünün kaçışını istiyor: \ " ` $
            _kacisli = exe_path
            for _ozel in ("\\", '"', "`", "$"):
                _kacisli = _kacisli.replace(_ozel, "\\" + _ozel)
            desktop_content = (
                "[Desktop Entry]\n"
                "Name=LaTeX Editor\n"
                "Comment=LaTeX editörü ve derleyici\n"
                f'Exec="{_kacisli}" %F\n'
                "Icon=latex-editor\n"
                "Type=Application\n"
                "Categories=Development;IDE;\n"
                "MimeType=text/x-tex;\n"
                "Keywords=latex;tex;editor;pdf;\n"
                "StartupNotify=true\n"
            )
            # encoding AÇIK. İçerik ASCII dışı taşıyor ("editörü") ve Desktop
            # Entry şartnamesi dosyanın UTF-8 olmasını şart koşuyor. Bugün
            # doğru yazılıyor ama TESADÜFEN: Qt, QApplication kurulurken
            # C yerel ayarını C.UTF-8'e çeviriyor ve bu çağrı ondan sonra
            # geliyor (main: QApplication -> _register_file_association).
            # Ölçüldü 2026-09-06, LC_ALL=C ile: QApplication'dan ÖNCE aynı
            # yazma UnicodeEncodeError veriyor, sonra veriyor değil. Çağrı
            # sırası değişirse dosya sessizce yazılmaz olurdu (gövde tümüyle
            # `except Exception: pass` içinde).
            with open(desktop_path, 'w', encoding='utf-8') as f:
                f.write(desktop_content)
            # İkonları kopyala
            for icon_name in ('latex-editor.png', 'latex-file-icon.png'):
                src = os.path.join(app_dir, 'linux', icon_name)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(icons_dir, icon_name))
            # .tex dosya ikonu (MIME tipi ikonu)
            file_icon_src = os.path.join(app_dir, 'linux', 'latex-file-icon.png')
            if os.path.isfile(file_icon_src):
                shutil.copy2(file_icon_src, os.path.join(mime_icons_dir, 'text-x-tex.png'))
                # Aktif ikon temasına da kopyala (sistem ikonunu ezer)
                try:
                    import subprocess
                    # TIMEOUT ŞART. Bu iki çağrı (burası ve aşağıdaki
                    # update-desktop-database) deponun timeout GEÇMEYEN tek
                    # iki subprocess çağrısıydı ve ikisi de AÇILIŞ yolunda:
                    # `main()` sırası QApplication -> _register_file_association
                    # -> MainWindow, yani bunlar dönene kadar ekranda hiçbir
                    # pencere yok. `gsettings` bozuk bir dbus oturumunda
                    # süresiz asılabiliyor. ÖLÇÜLDÜ (2026-09-06, PATH'e
                    # asılan taklitle): her biri 10 sn bekleyen iki komutla
                    # fonksiyon 20.7 saniye blokluyor, uygulama o süre
                    # boyunca hiç açılmıyor.
                    #
                    # 5 saniye ÖLÇÜMDEN seçildi, tahminden değil: ikisinin de
                    # gerçek süresi beşer koşuda 0.04-0.07 sn, yani sınır
                    # yaklaşık yüz katı. Süre dolarsa kayıt yarım kalır ve
                    # sonuç yalnızca kozmetik olur (.tex ikonu/"Birlikte Aç"
                    # girdisi eksik kalır, sonraki açılışta yeniden denenir);
                    # tersi, hiç açılmayan bir uygulamaydı.
                    result = subprocess.run(
                        ['gsettings', 'get', 'org.gnome.desktop.interface', 'icon-theme'],
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=5)
                    if result.returncode == 0:
                        active_theme = result.stdout.strip().strip("'")
                        theme_base = os.path.expanduser(f"~/.local/share/icons/{active_theme}")
                        # Her iki dizin yapısını da dene: {size}/mimetypes/ ve mimetypes/{size}/
                        for size in (16, 24, 32, 48, 64, 128, 256):
                            for pattern in [
                                f"{theme_base}/{size}x{size}/mimetypes",
                                f"{theme_base}/mimetypes/{size}",
                            ]:
                                os.makedirs(pattern, exist_ok=True)
                                shutil.copy2(file_icon_src, os.path.join(pattern, 'text-x-tex.png'))
                except Exception:
                    pass
            # Mime veritabanını güncelle. Timeout gerekçesi ve 5 saniyenin
            # ölçümü yukarıda. Süre dolarsa dıştaki `except Exception`
            # yakalıyor; bu zaten fonksiyonun son adımı.
            import subprocess
            subprocess.run(
                ["update-desktop-database", os.path.expanduser("~/.local/share/applications")],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass


def main():
    # Yakalanmayan Python istisnalarını logla
    def _handle_exception(exc_type, exc_value, exc_tb):
        import traceback
        from core.log import get_logger
        _logger = get_logger("main")
        _logger.error("Yakalanmamış istisna: %s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = _handle_exception

    app = QApplication(sys.argv)
    app.setApplicationName("LaTeX Editor")

    init_i18n(app)
    _register_file_association()

    # Komut satırından dosya yolu geldiyse al (Windows "Birlikte Aç")
    file_arg = ""
    for arg in sys.argv[1:]:
        if os.path.isfile(arg):
            file_arg = os.path.normpath(arg)
            break

    single = SingleInstance()
    if not single.try_become_primary():
        # Zaten bir örnek çalışıyor. Eskiden burada yalnız "zaten çalışıyor"
        # uyarısı vardı ve dosya AÇILMIYORDU — "Birlikte Aç" ilk açılıştan
        # sonra işlevsizdi. Artık yol çalışan örneğe iletilip sessizce çıkılır.
        if single.send(file_arg):
            sys.exit(0)
        QMessageBox.warning(
            None,
            "LaTeX Editor",
            _("Uygulama zaten çalışıyor ama yanıt vermiyor.\n"
              "Açık pencereyi kullanın ya da uygulamayı kapatıp yeniden başlatın."),
        )
        sys.exit(1)

    window = MainWindow(open_file=file_arg)
    window.show()
    single.file_received.connect(window.open_from_other_instance)

    exit_code = app.exec()
    single.stop()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
