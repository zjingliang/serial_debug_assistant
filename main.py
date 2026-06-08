#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Professional serial debug assistant for embedded / hardware engineers."""

from __future__ import annotations

import binascii
import json
import os
import queue
import re
import sys
import threading
import time
from datetime import datetime
from typing import Callable, List, Optional, Tuple

from checksum import ALGORITHMS
from modbus import ModbusStreamParser
from multi_port_window import MultiPortWindow
from plot_window import PlotWindow
from serial_io import BAUD_RATES, SerialSession, enumerate_serial_ports, parse_port

APP_NAME = "串口调试助手"
APP_VERSION = "2.1.0"
PARITY_UI = ("NONE", "EVEN", "ODD", "MARK", "SPACE")
PARITY_MAP = {"NONE": "N", "EVEN": "E", "ODD": "O", "MARK": "M", "SPACE": "S"}
FLOW_UI = ("NONE", "XON/XOFF", "RTS/CTS")
THEMES = {
    "浅色": {"bg": "#FFFFFF", "fg": "#000000", "rx_bg": "#FFFFFF", "tx_bg": "#FFFFFF"},
    "深色": {"bg": "#2B2B2B", "fg": "#E0E0E0", "rx_bg": "#1E1E1E", "tx_bg": "#1E1E1E"},
}


def windows_set_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

try:
    import serial
except ImportError:
    serial = None


def parse_hex(text: str) -> bytes:
    h = re.sub(r"[^0-9a-fA-F]", "", text)
    if not h:
        return b""
    if len(h) % 2:
        h += "0"
    return binascii.unhexlify(h)


def hex_spaced(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def parse_escapes(text: str) -> bytes:
    out = bytearray()
    i = 0
    while i < len(text):
        c = text[i]
        if c != "\\":
            out.extend(c.encode("utf-8"))
            i += 1
            continue
        if i + 1 >= len(text):
            out.append(ord("\\"))
            break
        n = text[i + 1]
        if n == "n":
            out.append(0x0A)
        elif n == "r":
            out.append(0x0D)
        elif n == "t":
            out.append(0x09)
        elif n == "0":
            out.append(0x00)
        elif n == "\\":
            out.append(0x5C)
        elif n in "xX" and i + 3 < len(text):
            try:
                out.append(int(text[i + 2 : i + 4], 16))
                i += 4
                continue
            except ValueError:
                out.append(ord("\\"))
        else:
            out.append(ord(n))
        i += 2
    return bytes(out)


class SerialDebugApp(tk.Tk):
    CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".serial-debug-assistant")
    CONFIG_FILE = os.path.join(CONFIG_DIR, "shortcuts.json")

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1060x680")
        self.minsize(900, 560)

        self._rx_q: queue.Queue[bytes] = queue.Queue()
        self.session = SerialSession(self._rx_q.put)
        self._rx_buf = bytearray()
        self._last_rx_time = 0.0
        self._loop_job: Optional[str] = None
        self._save_fp = None
        self._shortcuts: List[dict] = []
        self._send_history: List[str] = []
        self._auto_rules: List[dict] = []
        self._modbus = ModbusStreamParser()
        self._plot_win: Optional[PlotWindow] = None
        self._multi_win: Optional[MultiPortWindow] = None

        # --- state vars ---
        self.var_modbus = tk.BooleanVar(value=False)
        self.var_dtr = tk.BooleanVar(value=False)
        self.var_rts = tk.BooleanVar(value=False)
        self.var_rx_ascii = tk.BooleanVar(value=True)
        self.var_rx_log = tk.BooleanVar(value=True)
        self.var_rx_wrap = tk.BooleanVar(value=True)
        self.var_rx_hide = tk.BooleanVar(value=False)
        self.var_rx_save = tk.BooleanVar(value=False)
        self.var_rx_scroll = tk.BooleanVar(value=True)
        self.var_tx_ascii = tk.BooleanVar(value=True)
        self.var_tx_escape = tk.BooleanVar(value=True)
        self.var_tx_at_cr = tk.BooleanVar(value=True)
        self.var_tx_append = tk.BooleanVar(value=False)
        self.var_tx_show = tk.BooleanVar(value=True)
        self.var_loop_ms = tk.IntVar(value=0)
        self.var_pkt_timeout = tk.IntVar(value=50)
        self.var_pkt_fixed = tk.IntVar(value=0)
        self.var_pkt_mode = tk.StringVar(value="line")
        self.var_theme = tk.StringVar(value="浅色")
        self.var_append_hex = tk.StringVar(value="")

        self._build_ui()
        self._load_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._quit)
        self.bind("<Control-Return>", lambda _e: self._send())
        self.bind("<F5>", lambda _e: self._refresh_ports())

        self._refresh_ports()
        self.after(60, self._pump)
        self.after(30, self._pkt_timer)

    def _build_ui(self) -> None:
        root = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        root.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        left = ttk.Frame(root, width=268)
        right = ttk.Frame(root)
        root.add(left, weight=0)
        root.add(right, weight=1)

        self._build_left(left)
        self._build_right(right)
        self._build_statusbar()

    def _build_left(self, parent: ttk.Frame) -> None:
        # 串口设置
        port_box = ttk.LabelFrame(parent, text="串口设置", padding=6)
        port_box.pack(fill=tk.X, pady=(0, 4))

        rows = [
            ("串口号", "cb_port"),
            ("波特率", "cb_baud"),
            ("校验位", "cb_parity"),
            ("数据位", "cb_data"),
            ("停止位", "cb_stop"),
            ("流控制", "cb_flow"),
        ]
        for r, (label, attr) in enumerate(rows):
            ttk.Label(port_box, text=label).grid(row=r, column=0, sticky=tk.W, pady=2)
            cb = ttk.Combobox(port_box, width=18, state="readonly" if attr != "cb_port" else "normal")
            cb.grid(row=r, column=1, sticky=tk.EW, padx=(4, 0))
            setattr(self, attr, cb)
        port_box.columnconfigure(1, weight=1)

        self.cb_baud.configure(values=BAUD_RATES)
        self.cb_baud.set("115200")
        self.cb_parity.configure(values=PARITY_UI)
        self.cb_parity.set("NONE")
        self.cb_data.configure(values=("5", "6", "7", "8"))
        self.cb_data.set("8")
        self.cb_stop.configure(values=("1", "1.5", "2"))
        self.cb_stop.set("1")
        self.cb_flow.configure(values=FLOW_UI)
        self.cb_flow.set("NONE")

        open_row = ttk.Frame(port_box)
        open_row.grid(row=len(rows), column=0, columnspan=2, pady=(6, 2), sticky=tk.EW)
        self.btn_open = ttk.Button(open_row, text="打开", width=10, command=self._toggle_port)
        self.btn_open.pack(side=tk.LEFT)
        self.led = tk.Canvas(open_row, width=16, height=16, highlightthickness=0)
        self.led.pack(side=tk.LEFT, padx=8)
        self._led_id = self.led.create_oval(2, 2, 14, 14, fill="#333333", outline="#666")
        ttk.Button(open_row, text="刷新", width=6, command=self._refresh_ports).pack(side=tk.RIGHT)

        line_row = ttk.Frame(port_box)
        line_row.grid(row=len(rows) + 1, column=0, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(line_row, text="DTR", variable=self.var_dtr, command=self._sync_lines).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(line_row, text="RTS", variable=self.var_rts, command=self._sync_lines).pack(side=tk.LEFT)

        # 接收设置
        rx_box = ttk.LabelFrame(parent, text="接收设置", padding=6)
        rx_box.pack(fill=tk.X, pady=4)
        fmt = ttk.Frame(rx_box)
        fmt.pack(fill=tk.X)
        ttk.Radiobutton(fmt, text="ASCII", variable=self.var_rx_ascii, value=True).pack(side=tk.LEFT)
        ttk.Radiobutton(fmt, text="HEX", variable=self.var_rx_ascii, value=False).pack(side=tk.LEFT, padx=8)
        for text, var in (
            ("按日志模式显示", self.var_rx_log),
            ("接收区自动换行", self.var_rx_wrap),
            ("接收数据不显示", self.var_rx_hide),
        ):
            ttk.Checkbutton(rx_box, text=text, variable=var, command=self._on_rx_wrap).pack(anchor=tk.W)
        ttk.Checkbutton(rx_box, text="Modbus RTU 解析", variable=self.var_modbus).pack(anchor=tk.W)
        save_row = ttk.Frame(rx_box)
        save_row.pack(fill=tk.X)
        ttk.Checkbutton(save_row, text="接收保存到文件", variable=self.var_rx_save, command=self._toggle_save_file).pack(side=tk.LEFT)
        ttk.Button(save_row, text="…", width=3, command=self._pick_save_file).pack(side=tk.LEFT, padx=2)
        link = ttk.Frame(rx_box)
        link.pack(fill=tk.X, pady=(4, 0))
        ttk.Checkbutton(link, text="自动滚屏", variable=self.var_rx_scroll).pack(side=tk.LEFT)
        ttk.Button(link, text="清除接收", command=self._clear_rx).pack(side=tk.RIGHT)

        # 工具
        tools = ttk.Frame(parent)
        tools.pack(fill=tk.X, pady=4)
        tool_items = (
            ("自动应答", self._dlg_auto_reply),
            ("界面主题", self._dlg_theme),
            ("分包设置", self._dlg_packet),
            ("校验计算", self._dlg_checksum),
            ("实时曲线", self._open_plot),
            ("Modbus 工具", self._dlg_modbus),
            ("多串口监控", self._open_multi_port),
        )
        for i, (text, cmd) in enumerate(tool_items):
            ttk.Button(tools, text=text, command=cmd).grid(row=i // 2, column=i % 2, sticky=tk.EW, padx=2, pady=2)
        tools.columnconfigure(0, weight=1)
        tools.columnconfigure(1, weight=1)

        # 发送设置
        tx_box = ttk.LabelFrame(parent, text="发送设置", padding=6)
        tx_box.pack(fill=tk.X, pady=4)
        fmt2 = ttk.Frame(tx_box)
        fmt2.pack(fill=tk.X)
        ttk.Radiobutton(fmt2, text="ASCII", variable=self.var_tx_ascii, value=True).pack(side=tk.LEFT)
        ttk.Radiobutton(fmt2, text="HEX", variable=self.var_tx_ascii, value=False).pack(side=tk.LEFT, padx=8)
        for text, var in (
            ("自动解析转义符", self.var_tx_escape),
            ("AT 指令自动回车", self.var_tx_at_cr),
            ("自动发送附加位", self.var_tx_append),
            ("发送回显到接收区", self.var_tx_show),
        ):
            ttk.Checkbutton(tx_box, text=text, variable=var).pack(anchor=tk.W)
        file_row = ttk.Frame(tx_box)
        file_row.pack(fill=tk.X, pady=2)
        ttk.Button(file_row, text="打开文件数据源…", command=self._load_tx_file).pack(side=tk.LEFT)
        loop_row = ttk.Frame(tx_box)
        loop_row.pack(fill=tk.X, pady=2)
        ttk.Label(loop_row, text="循环周期").pack(side=tk.LEFT)
        ttk.Spinbox(loop_row, from_=0, to=3600000, increment=100, textvariable=self.var_loop_ms, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Label(loop_row, text="ms (0=关闭)").pack(side=tk.LEFT)
        ttk.Button(loop_row, text="应用", width=5, command=self._apply_loop).pack(side=tk.RIGHT)
        link2 = ttk.Frame(tx_box)
        link2.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(link2, text="快捷指令", command=self._dlg_shortcuts).pack(side=tk.LEFT)
        ttk.Button(link2, text="历史发送", command=self._dlg_history).pack(side=tk.RIGHT)

    def _build_right(self, parent: ttk.Frame) -> None:
        paned = ttk.Panedwindow(parent, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        rx_outer = ttk.LabelFrame(paned, text="数据接收", padding=4)
        tx_outer = ttk.LabelFrame(paned, text="数据发送", padding=4)
        paned.add(rx_outer, weight=3)
        paned.add(tx_outer, weight=1)

        self.txt_rx = scrolledtext.ScrolledText(
            rx_outer, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10), undo=False,
        )
        self.txt_rx.pack(fill=tk.BOTH, expand=True)
        self.txt_rx.tag_configure("rx", foreground="#006400")
        self.txt_rx.tag_configure("tx", foreground="#0000AA")
        self.txt_rx.tag_configure("sys", foreground="#666666")
        self.txt_rx.tag_configure("modbus", foreground="#7B1FA2")

        tx_body = ttk.Frame(tx_outer)
        tx_body.pack(fill=tk.BOTH, expand=True)
        self.txt_tx = scrolledtext.ScrolledText(tx_body, height=5, wrap=tk.WORD, font=("Consolas", 10))
        self.txt_tx.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        btn_col = ttk.Frame(tx_body)
        btn_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        ttk.Button(btn_col, text="清除", width=8, command=lambda: self.txt_tx.delete("1.0", tk.END)).pack(pady=(0, 6))
        ttk.Button(btn_col, text="发送", width=8, command=self._send).pack()

        append_row = ttk.Frame(tx_outer)
        append_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(append_row, text="附加 HEX:").pack(side=tk.LEFT)
        ttk.Entry(append_row, textvariable=self.var_append_hex, width=24).pack(side=tk.LEFT, padx=4)
        ttk.Label(append_row, text="Ctrl+Enter 发送", foreground="#888").pack(side=tk.RIGHT)

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self, padding=(6, 2))
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.lbl_status = ttk.Label(bar, text="就绪")
        self.lbl_status.pack(side=tk.LEFT)
        self.lbl_cnt = ttk.Label(bar, text="RX:0  TX:0  帧 RX:0 TX:0")
        self.lbl_cnt.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(bar, text="复位计数", command=self._reset_counters).pack(side=tk.RIGHT)

    # ---------- port ----------
    def _refresh_ports(self) -> None:
        rows = enumerate_serial_ports()
        self.cb_port.configure(values=[f"{d} — {desc}" if desc else d for d, desc in rows])
        if rows and not self.cb_port.get():
            self.cb_port.set(rows[0][0])
        self.lbl_status.configure(text=f"已发现 {len(rows)} 个串口" if rows else "未发现串口")

    def _toggle_port(self) -> None:
        if self.session.open:
            self._close_port()
        else:
            self._open_port()

    def _open_port(self) -> None:
        port = parse_port(self.cb_port.get())
        if not port:
            messagebox.showerror(APP_NAME, "请选择或输入串口号（如 COM3）")
            return
        if not serial:
            messagebox.showerror(APP_NAME, "请先运行 install_deps.bat 安装 pyserial")
            return
        try:
            baud = int(self.cb_baud.get())
            databits = int(self.cb_data.get())
            parity = PARITY_MAP.get(self.cb_parity.get(), "N")
            stop = self.cb_stop.get()
            flow = self.cb_flow.get()
            self.session.connect(port, baud, databits, parity, stop, flow)
            self.session.set_dtr(self.var_dtr.get())
            self.session.set_rts(self.var_rts.get())
            self.cb_port.set(port)
            self.btn_open.configure(text="关闭")
            self.led.itemconfigure(self._led_id, fill="#00CC00", outline="#008800")
            self.lbl_status.configure(text=f"已打开 {port} @ {baud}")
            self._append_sys(f"串口已打开 {port} @ {baud}")
            self._apply_loop()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"打开失败:\n{e}")

    def _close_port(self) -> None:
        self._stop_loop()
        self.session.disconnect()
        self.btn_open.configure(text="打开")
        self.led.itemconfigure(self._led_id, fill="#333333", outline="#666")
        self.lbl_status.configure(text="串口已关闭")
        self._append_sys("串口已关闭")
        self._close_save_file()

    def _sync_lines(self) -> None:
        if self.session.open:
            self.session.set_dtr(self.var_dtr.get())
            self.session.set_rts(self.var_rts.get())

    def _quit(self) -> None:
        self._stop_loop()
        self._close_save_file()
        self.session.disconnect()
        self.destroy()

    # ---------- RX display ----------
    def _on_rx_wrap(self) -> None:
        self.txt_rx.configure(wrap=tk.WORD if self.var_rx_wrap.get() else tk.NONE)

    def _append_text(self, tag: str, text: str) -> None:
        if tag == "rx" and self.var_rx_hide.get():
            return
        self.txt_rx.configure(state=tk.NORMAL)
        self.txt_rx.insert(tk.END, text, tag)
        if self.var_rx_scroll.get():
            self.txt_rx.see(tk.END)
        self.txt_rx.configure(state=tk.DISABLED)
        if tag == "rx" and self.var_rx_save.get() and self._save_fp:
            try:
                self._save_fp.write(text)
                self._save_fp.flush()
            except Exception:
                pass

    def _append_sys(self, msg: str) -> None:
        if self.var_rx_log.get():
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._append_text("sys", f"[{ts}] {msg}\n")
        else:
            self._append_text("sys", f"{msg}\n")

    def _format_rx(self, data: bytes) -> str:
        if self.var_rx_ascii.get():
            body = data.decode("utf-8", errors="replace")
        else:
            body = hex_spaced(data)
        if self.var_rx_log.get():
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            return f"[{ts}] {body}\n"
        return body + ("\n" if self.var_rx_wrap.get() else "")

    def _emit_rx_frame(self, frame: bytes) -> None:
        if not frame:
            return
        self.session.rx_frames += 1
        self._append_text("rx", self._format_rx(frame))
        self._feed_plot(frame)
        self._try_auto_reply(frame)

    def _feed_plot(self, frame: bytes) -> None:
        if not self._plot_win or not self._plot_win.winfo_exists():
            return
        if self.var_rx_ascii.get():
            self._plot_win.feed_text(frame.decode("utf-8", errors="replace"))
        else:
            self._plot_win.feed_text(frame.hex(" "))

    def _show_modbus(self, mf) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3] if self.var_rx_log.get() else ""
        head = f"[{ts}] " if ts else ""
        line = f"{head}{mf.summary}\n  {mf.detail}\n"
        self._append_text("modbus", line)

    def _handle_rx_chunk(self, chunk: bytes) -> None:
        self._last_rx_time = time.time()
        mode = self.var_pkt_mode.get()
        fixed = max(0, int(self.var_pkt_fixed.get() or 0))

        if mode == "fixed" and fixed > 0:
            self._rx_buf.extend(chunk)
            while len(self._rx_buf) >= fixed:
                frame = bytes(self._rx_buf[:fixed])
                del self._rx_buf[:fixed]
                self._emit_rx_frame(frame)
            return

        if mode == "line":
            self._rx_buf.extend(chunk)
            while True:
                pos = -1
                for sep in (b"\n", b"\r"):
                    i = self._rx_buf.find(sep)
                    if i != -1 and (pos == -1 or i < pos):
                        pos = i
                if pos == -1:
                    break
                frame = bytes(self._rx_buf[:pos])
                del self._rx_buf[: pos + 1]
                self._emit_rx_frame(frame)
            return

        # raw / timeout handled in timer
        self._rx_buf.extend(chunk)

    def _pkt_timer(self) -> None:
        if self.var_pkt_mode.get() == "timeout" and self._rx_buf:
            ms = max(10, int(self.var_pkt_timeout.get() or 50))
            if (time.time() - self._last_rx_time) * 1000 >= ms:
                frame = bytes(self._rx_buf)
                self._rx_buf.clear()
                self._emit_rx_frame(frame)
        self.after(30, self._pkt_timer)

    def _pump(self) -> None:
        while True:
            try:
                chunk = self._rx_q.get_nowait()
            except queue.Empty:
                break
            if self.var_modbus.get():
                for mf in self._modbus.feed(chunk):
                    self._show_modbus(mf)
            self._handle_rx_chunk(chunk)
        self.lbl_cnt.configure(
            text=(
                f"RX:{self.session.rx_bytes}  TX:{self.session.tx_bytes}  "
                f"帧 RX:{self.session.rx_frames} TX:{self.session.tx_frames}"
            )
        )
        self.after(60, self._pump)

    def _clear_rx(self) -> None:
        self.txt_rx.configure(state=tk.NORMAL)
        self.txt_rx.delete("1.0", tk.END)
        self.txt_rx.configure(state=tk.DISABLED)
        self._rx_buf.clear()

    def _reset_counters(self) -> None:
        self.session.rx_bytes = self.session.tx_bytes = 0
        self.session.rx_frames = self.session.tx_frames = 0

    def _toggle_save_file(self) -> None:
        if self.var_rx_save.get():
            self._pick_save_file()
        else:
            self._close_save_file()

    def _pick_save_file(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".log",
            initialfile=f"serial_{datetime.now():%Y%m%d_%H%M%S}.log",
            filetypes=[("Log", "*.log"), ("Text", "*.txt"), ("All", "*.*")],
        )
        if not path:
            self.var_rx_save.set(False)
            return
        self._close_save_file()
        self._save_fp = open(path, "a", encoding="utf-8")
        self.var_rx_save.set(True)
        self.lbl_status.configure(text=f"接收保存: {path}")

    def _close_save_file(self) -> None:
        if self._save_fp:
            try:
                self._save_fp.close()
            except Exception:
                pass
            self._save_fp = None

    # ---------- TX ----------
    def _build_payload(self) -> bytes:
        raw = self.txt_tx.get("1.0", tk.END).rstrip("\n")
        if self.var_tx_ascii.get():
            if self.var_tx_escape.get():
                data = parse_escapes(raw)
            else:
                data = raw.encode("utf-8")
            if self.var_tx_at_cr.get() and raw.strip().upper().startswith("AT"):
                if not data.endswith(b"\r\n") and not data.endswith(b"\n"):
                    data += b"\r\n"
        else:
            data = parse_hex(raw)

        if self.var_tx_append.get():
            extra = self.var_append_hex.get().strip()
            if extra:
                data += parse_hex(extra)

        return data

    def _send(self, payload: Optional[bytes] = None) -> None:
        if not self.session.open:
            messagebox.showwarning(APP_NAME, "请先打开串口")
            return
        try:
            data = payload if payload is not None else self._build_payload()
            if not data:
                return
            n = self.session.write(data)
            preview = hex_spaced(data) if not self.var_tx_ascii.get() else data.decode("utf-8", errors="replace")
            if self.var_tx_show.get():
                if self.var_rx_log.get():
                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    self._append_text("tx", f"[{ts}] >> {preview}\n")
                else:
                    self._append_text("tx", f">> {preview}\n")
            self._push_history(self.txt_tx.get("1.0", tk.END).rstrip("\n"))
            self.lbl_status.configure(text=f"已发送 {n} 字节")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"发送失败:\n{e}")

    def _push_history(self, text: str) -> None:
        if not text.strip():
            return
        self._send_history = [text] + [h for h in self._send_history if h != text]
        self._send_history = self._send_history[:30]

    def _load_tx_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("All", "*.*"), ("Text", "*.txt"), ("Binary", "*.bin")])
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            if self.var_tx_ascii.get():
                self.txt_tx.delete("1.0", tk.END)
                self.txt_tx.insert(tk.END, data.decode("utf-8", errors="replace"))
            else:
                self.txt_tx.delete("1.0", tk.END)
                self.txt_tx.insert(tk.END, hex_spaced(data))
            self.lbl_status.configure(text=f"已载入 {os.path.basename(path)} ({len(data)} B)")
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def _apply_loop(self) -> None:
        self._stop_loop()
        try:
            ms = int(self.var_loop_ms.get())
        except (tk.TclError, ValueError):
            ms = 0
        if ms > 0 and self.session.open:
            self._loop_tick(ms)

    def _loop_tick(self, ms: int) -> None:
        if self.session.open:
            self._send()
        self._loop_job = self.after(ms, lambda: self._loop_tick(ms))

    def _stop_loop(self) -> None:
        if self._loop_job:
            try:
                self.after_cancel(self._loop_job)
            except Exception:
                pass
            self._loop_job = None

    # ---------- auto reply ----------
    def _try_auto_reply(self, frame: bytes) -> None:
        if not self._auto_rules or not self.session.open:
            return
        text = frame.decode("utf-8", errors="replace")
        hexs = hex_spaced(frame)
        for rule in self._auto_rules:
            key = rule.get("match", "")
            if not key:
                continue
            if rule.get("hex") and key.upper() in hexs.upper():
                self._send(parse_hex(rule.get("reply", "")))
            elif not rule.get("hex") and key in text:
                resp = rule.get("reply", "")
                if rule.get("reply_hex"):
                    self._send(parse_hex(resp))
                else:
                    self._send(resp.encode("utf-8"))

    def _dlg_auto_reply(self) -> None:
        d = tk.Toplevel(self)
        d.title("自动应答")
        d.geometry("520x360")
        d.transient(self)
        ttk.Label(d, text="每行一条：匹配内容 | 应答内容 | hex(可选)").pack(anchor=tk.W, padx=8, pady=6)
        txt = scrolledtext.ScrolledText(d, height=14)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        for rule in self._auto_rules:
            flag = "hex" if rule.get("hex") else "txt"
            txt.insert(tk.END, f"{rule.get('match','')}|{rule.get('reply','')}|{flag}\n")

        def save() -> None:
            rules = []
            for line in txt.get("1.0", tk.END).splitlines():
                if not line.strip() or line.strip().startswith("#"):
                    continue
                parts = line.split("|")
                if len(parts) < 2:
                    continue
                rules.append(
                    {
                        "match": parts[0].strip(),
                        "reply": parts[1].strip(),
                        "hex": len(parts) > 2 and parts[2].strip().lower() == "hex",
                        "reply_hex": len(parts) > 2 and parts[2].strip().lower() == "hex",
                    }
                )
            self._auto_rules = rules
            d.destroy()

        ttk.Button(d, text="保存", command=save).pack(pady=6)

    # ---------- packet settings ----------
    def _dlg_packet(self) -> None:
        d = tk.Toplevel(self)
        d.title("分包设置")
        d.transient(self)
        f = ttk.Frame(d, padding=12)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="分包模式").grid(row=0, column=0, sticky=tk.W)
        for i, (val, label) in enumerate(
            (("line", "按行 (\\r\\n)"), ("timeout", "按超时"), ("fixed", "固定长度"))
        ):
            ttk.Radiobutton(f, text=label, variable=self.var_pkt_mode, value=val).grid(row=1 + i, column=0, sticky=tk.W)
        ttk.Label(f, text="超时 (ms)").grid(row=4, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Spinbox(f, from_=10, to=10000, textvariable=self.var_pkt_timeout, width=10).grid(row=4, column=1, sticky=tk.W)
        ttk.Label(f, text="固定长度 (字节)").grid(row=5, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Spinbox(f, from_=0, to=65535, textvariable=self.var_pkt_fixed, width=10).grid(row=5, column=1, sticky=tk.W)
        ttk.Button(f, text="确定", command=d.destroy).grid(row=6, column=0, columnspan=2, pady=12)

    # ---------- theme ----------
    def _dlg_theme(self) -> None:
        d = tk.Toplevel(self)
        d.title("界面主题")
        d.transient(self)
        f = ttk.Frame(d, padding=12)
        f.pack()
        for name in THEMES:
            ttk.Radiobutton(f, text=name, variable=self.var_theme, value=name, command=self._apply_theme).pack(anchor=tk.W)
        ttk.Button(f, text="关闭", command=d.destroy).pack(pady=8)

    def _apply_theme(self) -> None:
        t = THEMES.get(self.var_theme.get(), THEMES["浅色"])
        for w in (self.txt_rx, self.txt_tx):
            w.configure(bg=t.get("rx_bg", "#FFF"), fg=t.get("fg", "#000"), insertbackground=t.get("fg", "#000"))

    # ---------- checksum ----------
    def _dlg_checksum(self) -> None:
        d = tk.Toplevel(self)
        d.title("校验计算")
        d.geometry("480x280")
        d.transient(self)
        f = ttk.Frame(d, padding=10)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="数据 (HEX，空格可选)").pack(anchor=tk.W)
        ent = scrolledtext.ScrolledText(f, height=4)
        ent.pack(fill=tk.X, pady=4)
        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="算法").pack(side=tk.LEFT)
        cb = ttk.Combobox(row, values=list(ALGORITHMS.keys()), state="readonly", width=16)
        cb.set("CRC16-Modbus")
        cb.pack(side=tk.LEFT, padx=6)
        lbl = ttk.Label(f, text="结果: —", font=("Consolas", 11))
        lbl.pack(anchor=tk.W, pady=6)

        def calc() -> None:
            try:
                data = parse_hex(ent.get("1.0", tk.END))
                fn = ALGORITHMS[cb.get()]
                val = fn(data)
                if cb.get() == "CRC32":
                    lbl.configure(text=f"结果: 0x{val:08X}  ({val})")
                elif "16" in cb.get() or cb.get() == "SUM16":
                    lbl.configure(text=f"结果: 0x{val:04X}  低字节在前: {val & 0xFF:02X} {val >> 8:02X}")
                else:
                    lbl.configure(text=f"结果: 0x{val:02X}  ({val})")
            except Exception as e:
                lbl.configure(text=f"错误: {e}")

        def append() -> None:
            calc()
            try:
                data = parse_hex(ent.get("1.0", tk.END))
                val = ALGORITHMS[cb.get()](data)
                if "16" in cb.get() or cb.get() == "SUM16":
                    suffix = f"{val & 0xFF:02X}{val >> 8:02X}"
                elif cb.get() == "CRC32":
                    suffix = f"{val:08X}"
                else:
                    suffix = f"{val:02X}"
                cur = self.var_append_hex.get()
                self.var_append_hex.set((cur + " " + suffix).strip())
                self.var_tx_append.set(True)
                d.destroy()
            except Exception as e:
                messagebox.showerror(APP_NAME, str(e))

        bf = ttk.Frame(f)
        bf.pack(fill=tk.X, pady=4)
        ttk.Button(bf, text="计算", command=calc).pack(side=tk.LEFT)
        ttk.Button(bf, text="追加到附加位", command=append).pack(side=tk.LEFT, padx=8)

    # ---------- shortcuts ----------
    def _load_shortcuts(self) -> None:
        if os.path.isfile(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, encoding="utf-8") as f:
                    self._shortcuts = json.load(f)
            except Exception:
                self._shortcuts = []

    def _save_shortcuts(self) -> None:
        try:
            os.makedirs(self.CONFIG_DIR, exist_ok=True)
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._shortcuts, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _dlg_shortcuts(self) -> None:
        d = tk.Toplevel(self)
        d.title("快捷指令")
        d.geometry("560x400")
        d.transient(self)
        cols = ("name", "payload", "mode")
        tree = ttk.Treeview(d, columns=cols, show="headings", height=12)
        tree.heading("name", text="名称")
        tree.heading("payload", text="内容")
        tree.heading("mode", text="模式")
        tree.column("name", width=100)
        tree.column("payload", width=320)
        tree.column("mode", width=60)
        tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        def refresh() -> None:
            tree.delete(*tree.get_children())
            for s in self._shortcuts:
                tree.insert("", tk.END, values=(s["name"], s["payload"], s.get("mode", "ASCII")))

        refresh()

        def add_cmd() -> None:
            name = simpledialog.askstring("名称", "指令名称:", parent=d)
            if not name:
                return
            payload = simpledialog.askstring("内容", "发送内容:", parent=d)
            if payload is None:
                return
            mode = "HEX" if messagebox.askyesno("模式", "HEX 模式？\n选「否」为 ASCII") else "ASCII"
            self._shortcuts.append({"name": name, "payload": payload, "mode": mode})
            self._save_shortcuts()
            refresh()

        def send_sel() -> None:
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0], "values")
            mode, payload = vals[2], vals[1]
            if mode == "HEX":
                self._send(parse_hex(payload))
            else:
                old_a, old_e = self.var_tx_ascii.get(), self.var_tx_escape.get()
                self.var_tx_ascii.set(True)
                self.var_tx_escape.set(True)
                self.txt_tx.delete("1.0", tk.END)
                self.txt_tx.insert(tk.END, payload)
                self._send()
                self.var_tx_ascii.set(old_a)
                self.var_tx_escape.set(old_e)

        def delete_sel() -> None:
            sel = tree.selection()
            if not sel:
                return
            idx = tree.index(sel[0])
            if 0 <= idx < len(self._shortcuts):
                del self._shortcuts[idx]
                self._save_shortcuts()
                refresh()

        bf = ttk.Frame(d)
        bf.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(bf, text="添加", command=add_cmd).pack(side=tk.LEFT)
        ttk.Button(bf, text="发送选中", command=send_sel).pack(side=tk.LEFT, padx=6)
        ttk.Button(bf, text="删除", command=delete_sel).pack(side=tk.LEFT)
        tree.bind("<Double-1>", lambda _e: send_sel())

    def _dlg_history(self) -> None:
        d = tk.Toplevel(self)
        d.title("历史发送")
        d.geometry("520x320")
        d.transient(self)
        lb = tk.Listbox(d, font=("Consolas", 10))
        lb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        for h in self._send_history:
            lb.insert(tk.END, h[:200])

        def use() -> None:
            sel = lb.curselection()
            if not sel:
                return
            self.txt_tx.delete("1.0", tk.END)
            self.txt_tx.insert(tk.END, self._send_history[sel[0]])
            d.destroy()

        ttk.Button(d, text="填入发送区", command=use).pack(pady=6)

    # ---------- plot / modbus / multi-port ----------
    def _open_plot(self) -> None:
        if self._plot_win and self._plot_win.winfo_exists():
            self._plot_win.lift()
            return
        self._plot_win = PlotWindow(self)

    def _open_multi_port(self) -> None:
        if self._multi_win and self._multi_win.winfo_exists():
            self._multi_win.lift()
            return
        self._multi_win = MultiPortWindow(self)

    def _dlg_modbus(self) -> None:
        d = tk.Toplevel(self)
        d.title("Modbus RTU 工具")
        d.geometry("540x420")
        d.transient(self)
        ttk.Label(
            d,
            text="勾选「接收设置 → Modbus RTU 解析」后，自动从字节流识别 CRC 合法帧并解码。\n"
            "下方可手动构造读保持寄存器 (0x03) 请求并发送。",
            wraplength=500,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=10, pady=8)

        f = ttk.LabelFrame(d, text="读保持寄存器 0x03", padding=10)
        f.pack(fill=tk.X, padx=10, pady=4)
        self.var_mb_addr = tk.IntVar(value=1)
        self.var_mb_reg = tk.IntVar(value=0)
        self.var_mb_qty = tk.IntVar(value=2)
        for r, (label, var) in enumerate(
            (("站号", self.var_mb_addr), ("起始寄存器", self.var_mb_reg), ("数量", self.var_mb_qty))
        ):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky=tk.W, pady=2)
            ttk.Spinbox(f, from_=0, to=65535, textvariable=var, width=10).grid(row=r, column=1, sticky=tk.W)

        preview = ttk.Label(f, text="帧: —", font=("Consolas", 10))
        preview.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=6)

        def build_read03() -> bytes:
            addr = max(0, min(247, int(self.var_mb_addr.get())))
            reg = int(self.var_mb_reg.get()) & 0xFFFF
            qty = max(1, min(125, int(self.var_mb_qty.get())))
            pdu = bytes([addr, 0x03, reg >> 8, reg & 0xFF, qty >> 8, qty & 0xFF])
            crc = ALGORITHMS["CRC16-Modbus"](pdu)
            frame = pdu + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
            preview.configure(text=f"帧: {hex_spaced(frame)}")
            return frame

        def send_read() -> None:
            frame = build_read03()
            self._send(frame)

        def to_tx_hex() -> None:
            frame = build_read03()
            self.var_tx_ascii.set(False)
            self.txt_tx.delete("1.0", tk.END)
            self.txt_tx.insert(tk.END, hex_spaced(frame))
            d.destroy()

        bf = ttk.Frame(f)
        bf.grid(row=4, column=0, columnspan=2, sticky=tk.W)
        ttk.Button(bf, text="预览", command=build_read03).pack(side=tk.LEFT)
        ttk.Button(bf, text="发送", command=send_read).pack(side=tk.LEFT, padx=6)
        ttk.Button(bf, text="填入发送区", command=to_tx_hex).pack(side=tk.LEFT)

        ttk.Checkbutton(
            d,
            text="启用接收区 Modbus 自动解析",
            variable=self.var_modbus,
        ).pack(anchor=tk.W, padx=10, pady=8)
        ttk.Button(d, text="清除 Modbus 解析缓冲", command=self._modbus.clear).pack(anchor=tk.W, padx=10)
        ttk.Button(d, text="关闭", command=d.destroy).pack(pady=8)


def main() -> None:
    windows_set_dpi_awareness()
    if serial is None:
        print("请先运行 install_deps.bat")
    try:
        SerialDebugApp().mainloop()
    except tk.TclError as e:
        print("Tkinter 错误:", e)
        input("按回车退出…")


if __name__ == "__main__":
    main()
