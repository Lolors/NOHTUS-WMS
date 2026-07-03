from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
SERVICES = ROOT / "nohtus" / "services"

def find_func(text, name):
    m = re.search(rf"^def {re.escape(name)}\s*\([^\n]*\):\n", text, re.M)
    if not m:
        return None
    start = m.start()
    nxt = re.search(r"^def [A-Za-z_][A-Za-z0-9_]*\s*\([^\n]*\):\n", text[m.end():], re.M)
    end = m.end() + nxt.start() if nxt else len(text)
    return start, end

def remove_func(text, name):
    span = find_func(text, name)
    if not span:
        return text, None
    s, e = span
    return text[:s] + text[e:], text[s:e].strip() + "\n"

def strip_bad_imports(text, module_name):
    text = re.sub(rf"^from nohtus\.services\.{re.escape(module_name)} import .*\n", "", text, flags=re.M)
    text = re.sub(r"^[ \t]*from app import .*\n", "", text, flags=re.M)
    return text

def final_move(module_name, names):
    service_path = SERVICES / f"{module_name}.py"
    if not service_path.exists():
        service_path.write_text('"""Service helpers."""\n\nfrom __future__ import annotations\n\n', encoding="utf-8")

    app = APP.read_text(encoding="utf-8")
    svc = service_path.read_text(encoding="utf-8")

    moved = []
    blocks = []

    # 서비스 안의 기존 wrapper/중복 함수 제거
    for name in names:
        while True:
            svc, old = remove_func(svc, name)
            if old is None:
                break

    svc = strip_bad_imports(svc, module_name)

    # app.py에서 실제 구현 이동
    for name in names:
        app, block = remove_func(app, name)
        if block is None:
            print(f"SKIP missing in app.py: {name}")
            continue
        blocks.append(block)
        moved.append(name)
        print(f"FINAL MOVE: {name}")

    if not moved:
        raise SystemExit("No functions moved. app.py에 대상 함수가 없으면 먼저 백업/현재 상태를 확인해야 합니다.")

    if "from __future__ import annotations" not in svc:
        svc = 'from __future__ import annotations\n\n' + svc

    svc = svc.rstrip() + "\n\n\n" + "\n\n".join(blocks).rstrip() + "\n"

    import_line = f"from nohtus.services.{module_name} import " + ", ".join(moved)
    if import_line not in app:
        app = import_line + "\n" + app

    APP.write_text(app, encoding="utf-8")
    service_path.write_text(svc, encoding="utf-8")

    subprocess.run([sys.executable, "-m", "py_compile", str(APP), str(service_path)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, check=True)
    print("DONE final move.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: python tools/final_move_service.py <module> <function> [function...]")
    final_move(sys.argv[1], sys.argv[2:])
