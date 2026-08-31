@echo off
:: setlocal SART: LE_HIZLI (ve VER) cagiran kabuga sizmasin. Sizerse ayni
:: pencerede sonra kosturulan "Sikistirilmis Exe Olustur.bat" sessizce
:: SIKISTIRMASIZ bir exe uretirdi.
setlocal
echo LaTeX Editor exe olusturuluyor (yayinlanan surumun birebir aynisi)...
echo.

set PYTHON="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

:: Derleme ortami bagimliliklari guncel olsun (PyInstaller bunlari exe'ye gomer;
:: eksik paket sessizce eksik ozellik demek olur - orn. dulwich = surumleme)
%PYTHON% -m pip install -q -r requirements.txt -r requirements-build.txt
if errorlevel 1 (
    echo Bagimlilik kurulumu basarisiz!
    pause
    exit /b 1
)

:: Versiyonu version.py'den cek
for /f "tokens=2 delims== " %%v in ('findstr "VERSION" ..\core\version.py') do set "VER=%%~v"

:: TEK KAYNAK: "LaTeX Editor.spec". Buraya --add-data / --exclude-module /
:: --icon / --onefile YAZMA - hepsi spec'te. Uc ayri tanim tutmak, yayinlanan
:: exe ile yerelde denenen exe'yi sessizce farklilastiriyordu.
:: LE_HIZLI=1 => strip/upx kapali, yani CI'nin urettigi exe'nin AYNISI.
:: DIKKAT: satir devami (^) kullanma. Devam eden bir komutun icine REM/::
:: satiri koymak yorum degil ARGUMAN olur ve komutu orada bitirir - bu dosyanin
:: sikistirilmis kardesi tam bu yuzden aylarca hicbir exe uretmedi.
set LE_HIZLI=1
%PYTHON% -m PyInstaller "LaTeX Editor.spec" --clean --noconfirm
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
