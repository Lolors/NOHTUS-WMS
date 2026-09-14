@echo off
:loop
"C:\Program Files (x86)\cloudflared\cloudflared.exe" --config="C:\Users\Windows10\.cloudflared\config.yml" tunnel run
timeout /t 5
goto loop
