@echo off
title NOHTUS WMS
cd /d "%~dp0"
start "ngrok - nohtus-wms" C:\ngrok\ngrok.exe http 8501 --url https://broaden-utopia-caution.ngrok-free.dev
python -m streamlit run app.py
pause
