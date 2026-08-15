@echo off
echo LaTeX Editor exe olusturuluyor...
echo.

set PYTHON="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

:: Derleme ortamı bağımlılıkları güncel olsun (PyInstaller bunları exe'ye gömer;
:: eksik paket sessizce eksik özellik demek olur — örn. dulwich = sürümleme)
%PYTHON% -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo Bagimlilik kurulumu basarisiz!
    pause
    exit /b 1
)

:: Versiyonu version.py'den çek
for /f "tokens=2 delims== " %%v in ('findstr "VERSION" ..\core\version.py') do set "VER=%%~v"

%PYTHON% -m PyInstaller --onefile --windowed --name "LaTeX Editor v%VER%" --icon "linux\latex-editor.ico" --add-data "..\core;core" --add-data "gui;gui" --add-data "syntax;syntax" --add-data "linux;linux" --add-data "translations;translations" main.py

echo.
if exist "dist\LaTeX Editor v%VER%.exe" (
    echo Basarili! Exe dosyasi: dist\LaTeX Editor v%VER%.exe
) else (
    echo Hata olustu!
)
echo.
pause
