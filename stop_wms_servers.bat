@echo off
title Stop NOHTUS WMS Servers
cd /d "%~dp0"
echo Stopping NOHTUS WMS desktop app and mobile API server...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_wms_servers.ps1"
echo.
echo Done. Run run_wms.bat and start_mobile_api.bat again to start them back up.
pause
