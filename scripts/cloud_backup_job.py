"""Hourly Windows task: create a complete cloud backup, reporting failure by exit code."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nohtus.services.database_backup import run_due_backups
result = run_due_backups()
if result["errors"]:
    print("\n".join(result["errors"]))
    raise SystemExit(1)
print("Backup check completed")
