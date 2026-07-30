from __future__ import annotations

import os
from pathlib import Path


def removable_roots() -> list[Path]:
    roots: list[Path] = []
    if os.name == "nt":
        try:
            import ctypes

            get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
            for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                root = Path(f"{letter}:\\")
                if root.exists() and get_drive_type(str(root)) == 2:
                    roots.append(root)
        except Exception:
            pass
    else:
        candidates = [Path("/media"), Path("/mnt"), Path("/run/media")]
        for base in candidates:
            if not base.exists():
                continue
            try:
                for child in base.iterdir():
                    if child.is_dir():
                        nested = [p for p in child.iterdir() if p.is_dir()]
                        roots.extend(nested or [child])
            except OSError:
                continue
    return sorted(set(roots), key=lambda path: str(path).lower())


def find_files(filename: str, max_depth: int = 4) -> list[Path]:
    matches: list[Path] = []
    target = filename.lower()
    for root in removable_roots():
        pending = [(root, 0)]
        while pending:
            directory, depth = pending.pop()
            try:
                for child in directory.iterdir():
                    if child.is_file() and child.name.lower() == target:
                        matches.append(child)
                    elif child.is_dir() and depth < max_depth:
                        pending.append((child, depth + 1))
            except (OSError, PermissionError):
                continue
    return sorted(matches, key=lambda path: (len(path.parts), str(path).lower()))
