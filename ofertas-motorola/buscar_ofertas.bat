@echo off
rem Doble clic en este archivo para buscar las ofertas (Windows).
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 buscar_ofertas.py %*
) else (
    python buscar_ofertas.py %*
)
if %errorlevel%==9009 (
    echo.
    echo No se encontro Python. Instalalo desde https://www.python.org/downloads/
    echo y marca la casilla "Add Python to PATH" durante la instalacion.
)
echo.
pause
