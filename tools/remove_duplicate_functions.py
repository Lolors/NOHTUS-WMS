from pathlib import Path
import re
import sys

APP = Path("app.py")

def find_all_funcs(text, name):
    matches = list(re.finditer(rf"^def {re.escape(name)}\s*\([^\n]*\):\n", text, re.M))
    spans = []
    for m in matches:
        start = m.start()
        nxt = re.search(r"^def [A-Za-z_][A-Za-z0-9_]*\s*\([^\n]*\):\n", text[m.end():], re.M)
        end = m.end() + nxt.start() if nxt else len(text)
        spans.append((start, end))
    return spans

def remove_duplicate_keep_first(name):
    text = APP.read_text(encoding="utf-8")
    spans = find_all_funcs(text, name)
    if len(spans) <= 1:
        print(f"SKIP {name}: {len(spans)} found")
        return
    for start, end in reversed(spans[1:]):
        text = text[:start] + text[end:]
    APP.write_text(text, encoding="utf-8")
    print(f"REMOVED duplicates: {name}, removed {len(spans)-1}")

for name in sys.argv[1:]:
    remove_duplicate_keep_first(name)
