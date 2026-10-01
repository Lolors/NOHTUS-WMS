@echo off
:loop
"C:\Program Files (x86)\cloudflared\cloudflared.exe" --config="C:\Users\Windows10\.cloudflared\config.yml" tunnel run
powershell -NoProfile -Command "Start-Sleep -Seconds 5"
goto loop
