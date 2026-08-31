@echo off
:: setlocal: UPX_FLAG/VER cagiran kabuga sizmasin (bkz. "Exe Olustur.bat")
setlocal
:: LE_HIZLI disaridan gelmis olabilir; burada sikistirma ISTIYORUZ.
set LE_HIZLI=
echo LaTeX Editor (sikistirilmis) exe olusturuluyor...
echo.

set PYTHON="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

:: Derleme ortami bagimliliklari guncel olsun (bkz. "Exe Olustur.bat")
%PYTHON% -m pip install -q -r requirements.txt -r requirements-build.txt
if errorlevel 1 (
    echo Bagimlilik kurulumu basarisiz!
    pause
    exit /b 1
)

:: Versiyonu version.py'den cek
for /f "tokens=2 delims== " %%v in ('findstr "VERSION" ..\core\version.py') do set "VER=%%~v"

:: UPX kontrolu. Spec zaten yerelde strip+upx istiyor; PyInstaller upx.exe'yi
:: PATH'te arar, depoya konan kopyayi bulmasi icin --upx-dir gerekiyor.
set UPX_FLAG=
if exist "upx\upx.exe" (
    echo UPX bulundu, sikistirma aktif.
    set UPX_FLAG=--upx-dir upx
) else (
    echo UPX bulunamadi. Sikistirma olmadan devam ediliyor.
    echo UPX eklemek icin: https://github.com/upx/upx/releases indirip upx\ klasorune koyun.
    echo.
)

:: TEK KAYNAK: "LaTeX Editor.spec". Hariç tutma listesi, datas ve ikon ORADA;
:: burada tekrarlanmiyor. Bu dosyanin eski hali listeyi kendi tutuyordu ve
:: satir devami (^) icine konan REM satirlari yuzunden PyInstaller'a ne
:: --exclude-module ne de main.py geciyordu: script hicbir exe uretmiyordu.
%PYTHON% -m PyInstaller "LaTeX Editor.spec" --clean --noconfirm %UPX_FLAG%
if errorlevel 1 (
    echo PyInstaller basarisiz!
    pause
    exit /b 1
)

:: Spec sabit ad uretir ("LaTeX Editor.exe"); surum etiketini burada ekliyoruz.
if exist "dist\LaTeX Editor.exe" move /y "dist\LaTeX Editor.exe" "dist\LaTeX Editor v%VER%.exe" >nul

echo.
if exist "dist\LaTeX Editor v%VER%.exe" (
    echo Basarili! Exe dosyasi: dist\LaTeX Editor v%VER%.exe
    for %%A in ("dist\LaTeX Editor v%VER%.exe") do echo Boyut: %%~zA bytes
) else (
    echo Hata olustu!
)
echo.
pause
