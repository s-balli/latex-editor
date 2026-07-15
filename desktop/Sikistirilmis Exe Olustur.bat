@echo off
echo LaTeX Editor (sikistirilmis) exe olusturuluyor...
echo.

set PYTHON="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

:: Versiyonu version.py'den çek
for /f "tokens=2 delims== " %%v in ('findstr "VERSION" ..\core\version.py') do set "VER=%%~v"

:: UPX kontrolu
set UPX_FLAG=
if exist "upx\upx.exe" (
    echo UPX bulundu, sikistirma aktif.
    set UPX_FLAG=--upx-dir=upx
) else (
    echo UPX bulunamadi. Sikistirma olmadan devam ediliyor.
    echo UPX eklemek icin: https://github.com/upx/upx/releases indirip upx\ klasorune koyun.
    echo.
)

%PYTHON% -m PyInstaller --onefile --windowed ^
    --name "LaTeX Editor v%VER%" ^
    --icon "linux\latex-editor.ico" ^
    --add-data "..\core;core" ^
    --add-data "gui;gui" ^
    --add-data "syntax;syntax" ^
    --add-data "linux;linux" ^
    --add-data "translations;translations" ^
    --exclude-module tkinter ^
    --exclude-module unittest ^
    --exclude-module test ^
    --exclude-module email ^
    --exclude-module html ^
    --exclude-module xmlrpc ^
    --exclude-module pydoc ^
    --exclude-module curses ^
    --exclude-module lib2to3 ^
    --exclude-module idlelib ^
    --exclude-module pip ^
    --exclude-module setuptools ^
    --strip ^
    %UPX_FLAG% ^
    main.py

echo.
if exist "dist\LaTeX Editor v%VER%.exe" (
    echo Basarili! Exe dosyasi: dist\LaTeX Editor v%VER%.exe
    for %%A in ("dist\LaTeX Editor v%VER%.exe" %%) do echo Boyut: %%~zA bytes
) else (
    echo Hata olustu!
)
echo.
pause
