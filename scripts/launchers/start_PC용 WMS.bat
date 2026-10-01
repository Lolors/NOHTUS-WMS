@echo off
cd /d "%~dp0..\.."
set NOHTUS_MOBILE_APP_URL=/mobile
:loop
"C:\Users\Windows10\AppData\Local\Programs\Python\Python311\python.exe" -m streamlit run app.py >> streamlit.log 2>&1
echo ===== restarted %date% %time% ===== >> streamlit.log
powershell -NoProfile -Command "Start-Sleep -Seconds 5"
goto loop
