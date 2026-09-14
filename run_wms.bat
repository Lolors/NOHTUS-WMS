@echo off
title NOHTUS WMS
cd /d "%~dp0"
set NOHTUS_MOBILE_APP_URL=/mobile
python -m streamlit run app.py
pause