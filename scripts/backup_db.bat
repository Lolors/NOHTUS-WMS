@echo off
cd /d "%~dp0\.."
if not exist backups mkdir backups
for /f "tokens=1-4 delims=/-. " %%a in ('date /t') do set d=%%a%%b%%c%%d
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set t=%%a%%b
copy data\nohtus.db backups\nohtus_backup_%d%_%t%.db
pause
