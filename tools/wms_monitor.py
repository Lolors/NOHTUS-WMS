"""Desktop controller for the three existing WMS launchers (Windows)."""
import base64
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

ROOT = Path(__file__).resolve().parents[1]
HIDDEN = subprocess.CREATE_NO_WINDOW
SERVICES = {
    "pc": ("PC용 WMS", "start_PC용 WMS.bat", "start_streamlit.bat", 8501, "streamlit.log"),
    "mobile": ("모바일 WMS", "start_모바일 WMS 서버.bat", "start_mobile_api.bat", 8535, "mobile_api.log"),
    "tunnel": ("외부 접속 연결", "start_외부 접속용 연결.bat", "start_cloudflared.bat", None, None),
}


def processes():
    script = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; @(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine) | ConvertTo-Json -Compress"
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    result = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded], capture_output=True, creationflags=HIDDEN, timeout=25)
    if result.returncode:
        raise RuntimeError("실행 상태 조회에 실패했습니다.")
    rows = json.loads(result.stdout.decode("utf-8-sig"))
    return rows if isinstance(rows, list) else [rows]


def classify(rows, key):
    label, filename, legacy, port, log = SERVICES[key]
    matched = []
    for row in rows:
        name = str(row.get("Name") or "").lower()
        command = str(row.get("CommandLine") or "").lower()
        wrapper = name == "cmd.exe" and any(n.lower() in command for n in (filename, legacy))
        server = False
        if name in ("python.exe", "pythonw.exe", "streamlit.exe", "uvicorn.exe"):
            if key == "pc":
                server = bool(re.search(r"streamlit\s+run\s+(?:\"[^\"]*[\\/])?app\.py(?:\"|\s|$)", command))
            elif key == "mobile":
                server = "uvicorn nohtus.mobile_api.main:" in command
        if key == "tunnel":
            server = name == "cloudflared.exe" and "tunnel run" in command and str(Path.home() / ".cloudflared" / "config.yml").lower() in command
        if wrapper or server:
            matched.append(dict(row, wrapper=wrapper, server=server))
    # Legacy launcher may have been started by double-clicking run_wms.bat.
    if key == "pc":
        for row in rows:
            if str(row.get("Name", "")).lower() == "cmd.exe" and "run_wms.bat" in str(row.get("CommandLine", "")).lower():
                matched.append(dict(row, wrapper=True, server=False))
    return matched


def listening(port):
    if not port:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def start_service(key):
    if classify(processes(), key):
        return "이미 실행 중입니다."
    spec = SERVICES[key]
    if spec[3] and listening(spec[3]):
        raise RuntimeError(f"포트 {spec[3]}가 이미 사용 중입니다. 중복 실행하지 않았습니다.")
    path = ROOT / "scripts" / "launchers" / spec[1]
    if not path.is_file():
        path = ROOT / spec[1]
    if not path.is_file():
        path = ROOT / spec[2]
    if not path.is_file():
        raise FileNotFoundError("실행 배치파일을 찾을 수 없습니다.")
    subprocess.Popen(["cmd.exe", "/d", "/c", str(path)], cwd=ROOT, creationflags=HIDDEN, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "시작 요청을 보냈습니다. 상태가 갱신됩니다."


def stop_service(key):
    rows = classify(processes(), key)
    # Stop loop parents first, otherwise they relaunch Python after five seconds.
    for row in sorted(rows, key=lambda r: not r["wrapper"]):
        subprocess.run(["taskkill", "/PID", str(row["ProcessId"]), "/T", "/F"], capture_output=True, creationflags=HIDDEN, timeout=15)
    if classify(processes(), key):
        raise RuntimeError("일부 프로세스가 종료되지 않았습니다. 실행 권한을 확인하세요.")
    return "중지했습니다."


class Monitor:
    def __init__(self, window):
        self.window = window
        self.busy = False
        self.scanning = False
        self.pending = []
        self.lock = threading.Lock()
        window.title("NOHTUS WMS 실행 관리")
        window.geometry("850x420")
        window.minsize(790, 410)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", font=("맑은 고딕", 10))
        style.configure("TButton", font=("맑은 고딕", 10), padding=6)
        outer = ttk.Frame(window, padding=20); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="WMS 실행 관리", font=("맑은 고딕", 19, "bold")).pack(anchor="w")
        ttk.Label(outer, text="5초마다 상태 확인 · 이 창을 닫아도 서버는 계속 실행됩니다.").pack(anchor="w", pady=(5, 16))
        self.labels = {}; self.buttons = []
        for key, spec in SERVICES.items():
            box = ttk.Frame(outer); box.pack(fill="x", pady=10)
            ttk.Label(box, text=spec[0], width=16).pack(side="left")
            status = ttk.Label(box, text="확인 중…", width=37); status.pack(side="left"); self.labels[key] = status
            for text, action in (("시작", "start"), ("중지", "stop"), ("재시작", "restart")):
                button = ttk.Button(box, text=text, width=7, command=lambda k=key,a=action:self.action(k,a)); button.pack(side="left", padx=3);self.buttons.append(button)
        ttk.Separator(outer).pack(fill="x", pady=12)
        ttk.Label(outer, text="외부 연결은 프로세스 실행 여부만 확인합니다. 인터넷 접속 성공을 보장하지 않습니다.", foreground="#666666").pack(anchor="w")
        self.message = ttk.Label(outer, text="", wraplength=790); self.message.pack(anchor="w", pady=8)
        bar = ttk.Frame(outer); bar.pack(fill="x")
        for key in ("pc", "mobile"):
            ttk.Button(bar, text=SERVICES[key][0]+" 로그", command=lambda k=key:self.open_log(k)).pack(side="left", padx=(0,8))
        ttk.Button(bar,text="폴더 열기",command=lambda:os.startfile(ROOT)).pack(side="left")
        self.poll(); self.refresh()

    def deliver(self, callback):
        with self.lock: self.pending.append(callback)

    def poll(self):
        with self.lock: callbacks,self.pending=self.pending,[]
        for callback in callbacks: callback()
        self.window.after(100,self.poll)

    def refresh(self):
        if not self.scanning:
            self.scanning=True
            def work():
                try:
                    rows=processes();states={}
                    for key,spec in SERVICES.items():
                        matches=classify(rows,key); servers=[r for r in matches if r['server']]
                        if servers:
                            healthy=listening(spec[3]) if spec[3] else True
                            text=("실행 중" if healthy else "프로세스 실행 / 응답 대기")+" · PID "+", ".join(str(r['ProcessId']) for r in servers)
                            color="#15803d" if healthy else "#b45309"
                        elif matches: text,color="배치 실행 / 서버 재시작 대기", "#b45309"
                        else: text,color="중지됨", "#64748b"
                        states[key]=(text,color)
                    def apply():
                        for key,(text,color) in states.items():self.labels[key].configure(text=text,foreground=color)
                    self.deliver(apply)
                except Exception:
                    self.deliver(lambda:[label.configure(text="상태 조회 실패",foreground="#b91c1c") for label in self.labels.values()])
                finally:self.scanning=False
            threading.Thread(target=work,daemon=True).start()
        self.window.after(5000,self.refresh)

    def action(self,key,action):
        if self.busy:return
        self.busy=True
        for button in self.buttons:button.state(["disabled"])
        self.message.configure(text=SERVICES[key][0]+" 처리 중…")
        def work():
            try:
                if action in ("stop","restart"): result=stop_service(key)
                if action in ("start","restart"): result=start_service(key)
            except Exception as exc:result=str(exc)
            def done():
                self.busy=False
                for button in self.buttons:button.state(["!disabled"])
                self.message.configure(text=result)
            self.deliver(done)
        threading.Thread(target=work,daemon=True).start()

    def open_log(self,key):
        path=ROOT / SERVICES[key][4]
        if path.is_file():os.startfile(path)
        else:messagebox.showinfo("로그", "아직 로그 파일이 없습니다.")


if __name__ == "__main__":
    window=tk.Tk();Monitor(window);window.mainloop()
