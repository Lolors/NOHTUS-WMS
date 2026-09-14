@echo off
cd /d "C:\Users\Windows10\Documents\GitHub\NOHTUS-WMS"
:loop
python -m uvicorn nohtus.mobile_api.main:root_app --port 8535 >> mobile_api.log 2>&1
echo ===== restarted %date% %time% ===== >> mobile_api.log
timeout /t 5
goto loop
