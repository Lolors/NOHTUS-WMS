@echo off
cd /d "%~dp0"
python -m pip install streamlit pandas rapidfuzz openpyxl reportlab playwright
python -m playwright install chromium
pause
