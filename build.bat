@echo off
rem Construit dist\CalculatricePro.exe sous Windows (Python 3.10+ requis).
cd /d "%~dp0"
python -m venv .venv || goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt || goto :error
python -m pytest -q || goto :error
pyinstaller --noconfirm --clean CalculatricePro.spec || goto :error
echo.
echo Termine : dist\CalculatricePro.exe
goto :eof
:error
echo La construction a echoue.
exit /b 1
