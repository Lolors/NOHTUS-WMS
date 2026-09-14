@echo off
cd /d "C:\Users\Windows10\Documents\GitHub\NOHTUS-WMS"
set NOHTUS_MOBILE_APP_URL=/mobile
:loop
python -m streamlit run app.py >> streamlit.log 2>&1
echo ===== restarted %date% %time% ===== >> streamlit.log
timeout /t 5
goto loop
