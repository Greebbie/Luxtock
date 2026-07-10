@echo off
rem Luxtock dashboard launcher — double-click to open http://127.0.0.1:8321
rem If the server is already running, this just opens a browser tab.
rem Otherwise it starts the server here; closing this window stops it.
cd /d "%~dp0"

powershell -NoProfile -Command "$c = New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1', 8321); exit 0 } catch { exit 1 } finally { $c.Close() }" >nul 2>&1
if %errorlevel%==0 (
    start "" "http://127.0.0.1:8321"
    exit /b 0
)

where luxtock >nul 2>&1
if %errorlevel%==0 (
    luxtock ui
    goto :eof
)

python -m luxtock ui
if errorlevel 1 (
    echo.
    echo luxtock is not installed. From this folder run:  pip install -e .
    pause
)
