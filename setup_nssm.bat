@echo off
REM Run this script as Administrator to register IndexTTS API as a Windows service.

set SERVICE=Touge-IndexTTS-API
set BAT_PATH=D:\AIGC\Background_Tasks\IndexTTS-API\start_service.bat
set APP_DIR=D:\AIGC\Background_Tasks\IndexTTS-API
set LOG_DIR=D:\AIGC\Background_Tasks\IndexTTS-API\logs

REM ---------- Service arguments (forwarded to main.py) ----------
set HOST=0.0.0.0
set PORT=10001
REM --------------------------------------------------------------

nssm install %SERVICE% "%BAT_PATH%"
nssm set %SERVICE% AppDirectory "%APP_DIR%"
nssm set %SERVICE% AppParameters "--host %HOST% --port %PORT%"
nssm set %SERVICE% DisplayName "Touge IndexTTS API"
nssm set %SERVICE% Description "IndexTTS 语音合成 API 服务"
nssm set %SERVICE% AppStdout "%LOG_DIR%\service_stdout.log"
nssm set %SERVICE% AppStderr "%LOG_DIR%\service_stderr.log"

echo.
echo Service "%SERVICE%" registered successfully.
echo Run: nssm start %SERVICE%
pause
