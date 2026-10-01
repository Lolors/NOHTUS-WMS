@echo off
cd /d "%~dp0..\.."
:loop
"C:\Users\Windows10\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn nohtus.mobile_api.main:root_app --port 8535 >> mobile_api.log 2>&1
echo ===== restarted %date% %time% ===== >> mobile_api.log
powershell -NoProfile -Command "Start-Sleep -Seconds 5"
goto loop
