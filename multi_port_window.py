# -*- coding: utf-8 -*-
"""Multi-port serial monitor window."""

from __future__ import annotations

import queue
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk
from typing import Callable, Dict

try:
    import serial
except ImportError:
    serial = None

from serial_io import BAUD_RATES, SerialSession, enumerate_serial_ports, parse_port

APP_NAME = "串口调试助手"
MAX_PORTS = 4


class PortPane:
    def __init__(self, parent: ttk.Notebook, port: str, baud: int, on_close: Callable[[str], None]) -> None:
        self.port = port
        self.baud = baud
        self._q: queue.Queue[bytes] = queue.Queue()
        self.session = SerialSession(self._q.put)
        self.frame = ttk.Frame(parent, padding=4)
        parent.add(self.frame, text=f"{port} @ {baud}")

        top = ttk.Frame(self.frame)
        top.pack(fill=tk.X)
        self.lbl = ttk.Label(top, text="未连接")
        self.lbl.pack(side=tk.LEFT)
        ttk.Button(top, text="关闭端口", command=lambda: on_close(port)).pack(side=tk.RIGHT)

        self.txt = scrolledtext.ScrolledText(
            self.frame, height=16, wrap=tk.WORD, font=("Consolas", 9), state=tk.DISABLED,
        )
        self.txt.pack(fill=tk.BOTH, expand=True, pady=4)
        self.txt.tag_configure("rx", foreground="#006400")

        self._line_buf = bytearray()

    def open(self) -> None:
        self.session.connect(self.port, self.baud, 8, "N", "1", "NONE")

    def close(self) -> None:
        self.session.disconnect()

    def append(self, text: str) -> None:
        self.txt.configure(state=tk.NORMAL)
        self.txt.insert(tk.END, text, "rx")
        self.txt.see(tk.END)
        self.txt.configure(state=tk.DISABLED)

    def pump(self) -> None:
        while True:
            try:
                chunk = self._q.get_nowait()
            except queue.Empty:
                break
            self._line_buf.extend(chunk)
            while True:
                pos = -1
                for sep in (b"\n", b"\r"):
                    i = self._line_buf.find(sep)
                    if i != -1 and (pos == -1 or i < pos):
                        pos = i
                if pos == -1:
                    break
                line = bytes(self._line_buf[:pos]).decode("utf-8", errors="replace")
                del self._line_buf[: pos + 1]
                if line:
                    ts = datetime.now().strftime("%H:%M:%S")
                    self.append(f"[{ts}] {line}\n")
        if self.session.open:
            self.lbl.configure(text=f"RX:{self.session.rx_bytes} B  TX:{self.session.tx_bytes} B")


class MultiPortWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("多串口监控")
        self.geometry("920x560")
        self.transient(master)
        self._panes: Dict[str, PortPane] = {}

        bar = ttk.Frame(self, padding=8)
        bar.pack(fill=tk.X)
        ttk.Label(bar, text="端口").pack(side=tk.LEFT)
        self.cb_port = ttk.Combobox(bar, width=28)
        self.cb_port.pack(side=tk.LEFT, padx=4)
        ttk.Label(bar, text="波特率").pack(side=tk.LEFT, padx=(8, 0))
        self.cb_baud = ttk.Combobox(bar, width=10, values=BAUD_RATES)
        self.cb_baud.set("115200")
        self.cb_baud.pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="刷新", command=self._refresh).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="添加监控", command=self._add).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="全部关闭", command=self._close_all).pack(side=tk.RIGHT)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        ttk.Label(
            self,
            text=f"最多 {MAX_PORTS} 路并行监控；各页签独立，不影响主窗口串口。",
            foreground="#555",
        ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        self._refresh()
        self.after(80, self._tick)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _refresh(self) -> None:
        rows = enumerate_serial_ports()
        self.cb_port.configure(values=[f"{d} — {desc}" if desc else d for d, desc in rows])
        if rows:
            self.cb_port.set(rows[0][0])

    def _add(self) -> None:
        if len(self._panes) >= MAX_PORTS:
            messagebox.showwarning(APP_NAME, f"最多 {MAX_PORTS} 路")
            return
        port = parse_port(self.cb_port.get())
        if not port:
            messagebox.showerror(APP_NAME, "请选择端口")
            return
        if port in self._panes:
            messagebox.showinfo(APP_NAME, f"{port} 已在监控中")
            return
        if not serial:
            messagebox.showerror(APP_NAME, "未安装 pyserial")
            return
        try:
            baud = int(self.cb_baud.get())
        except ValueError:
            baud = 115200
        try:
            pane = PortPane(self.notebook, port, baud, self._remove)
            pane.open()
            self._panes[port] = pane
            self.notebook.select(pane.frame)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"打开 {port} 失败:\n{e}")

    def _remove(self, port: str) -> None:
        pane = self._panes.pop(port, None)
        if pane:
            pane.close()
            self.notebook.forget(pane.frame)

    def _close_all(self) -> None:
        for port in list(self._panes.keys()):
            self._remove(port)

    def _tick(self) -> None:
        if self.winfo_exists():
            for pane in self._panes.values():
                pane.pump()
            self.after(80, self._tick)

    def _on_close(self) -> None:
        self._close_all()
        self.destroy()
