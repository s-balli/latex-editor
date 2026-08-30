@echo off
:: %* : Explorer'dan gelen dosya yolunu main.py'ye ilet. Bu olmadan
:: 'Birlikte Ac' ile secilen dosya main.py'ye HIC ulasmiyordu.
start "" "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" "%~dp0main.py" %*
