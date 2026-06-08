# -*- coding: utf-8 -*-
"""Real-time strip-chart panel (Tk Canvas, no extra deps)."""

from __future__ import annotations

import re
import tkinter as tk
from collections import deque
from tkinter import ttk
from typing import Deque, List, Optional, Tuple


class PlotWindow(tk.Toplevel):
    MAX_POINTS = 600

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("实时曲线")
        self.geometry("860x420")
        self.transient(master)

        self._channels: List[Tuple[str, str, Deque[float], str]] = []
        self._running = True

        cfg = ttk.LabelFrame(self, text="数据提取", padding=8)
        cfg.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(
            cfg,
            text="从接收文本提取数值：逗号/空格分隔取前 N 路，或正则 (默认捕获浮点数)",
        ).pack(anchor=tk.W)
        row = ttk.Frame(cfg)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="通道数").pack(side=tk.LEFT)
        self.var_ch = tk.IntVar(value=2)
        ttk.Spinbox(row, from_=1, to=8, textvariable=self.var_ch, width=5, command=self._rebuild_channels).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="正则").pack(side=tk.LEFT, padx=(12, 4))
        self.var_regex = tk.StringVar(value=r"(-?\d+\.?\d*)")
        ttk.Entry(row, textvariable=self.var_regex, width=36).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="应用", command=self._rebuild_channels).pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text="清空曲线", command=self._clear_data).pack(side=tk.LEFT)

        self.canvas = tk.Canvas(self, bg="#FAFAFA", height=280, highlightthickness=1, highlightbackground="#CCC")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self.lbl_info = ttk.Label(self, text="等待数据…")
        self.lbl_info.pack(anchor=tk.W, padx=8, pady=4)

        self._rebuild_channels()
        self._draw_job: Optional[str] = None
        self._schedule_draw()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        self._running = False
        if self._draw_job:
            try:
                self.after_cancel(self._draw_job)
            except Exception:
                pass
        self.destroy()

    def _rebuild_channels(self) -> None:
        try:
            n = max(1, min(8, int(self.var_ch.get())))
        except (tk.TclError, ValueError):
            n = 2
        colors = ("#E53935", "#1E88E5", "#43A047", "#FB8C00", "#8E24AA", "#00ACC1", "#6D4C41", "#546E7A")
        old = {name: dq for name, _, dq, _ in self._channels}
        self._channels = []
        for i in range(n):
            name = f"CH{i + 1}"
            dq: Deque[float] = old.get(name, deque(maxlen=self.MAX_POINTS))
            if dq.maxlen != self.MAX_POINTS:
                dq = deque(dq, maxlen=self.MAX_POINTS)
            self._channels.append((name, name, dq, colors[i % len(colors)]))

    def _clear_data(self) -> None:
        for _, _, dq, _ in self._channels:
            dq.clear()
        self.canvas.delete("all")

    def feed_text(self, text: str) -> None:
        if not self._running or not text.strip():
            return
        try:
            pattern = self.var_regex.get() or r"(-?\d+\.?\d*)"
            nums = [float(x) for x in re.findall(pattern, text)]
        except re.error:
            nums = []
        if not nums:
            parts = re.split(r"[,;\s]+", text.strip())
            for p in parts:
                try:
                    nums.append(float(p))
                except ValueError:
                    continue
        for i, (_, _, dq, _) in enumerate(self._channels):
            if i < len(nums):
                dq.append(nums[i])
        if nums:
            self.lbl_info.configure(text=f"最近样本: {nums[:8]}{'…' if len(nums) > 8 else ''}")

    def _schedule_draw(self) -> None:
        if self._running and self.winfo_exists():
            self._draw()
            self._draw_job = self.after(80, self._schedule_draw)

    def _draw(self) -> None:
        w = max(self.canvas.winfo_width(), 400)
        h = max(self.canvas.winfo_height(), 200)
        self.canvas.delete("all")
        pad_l, pad_r, pad_t, pad_b = 48, 12, 12, 28
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_t - pad_b

        all_vals: List[float] = []
        for _, _, dq, _ in self._channels:
            all_vals.extend(dq)
        if not all_vals:
            self.canvas.create_text(w // 2, h // 2, text="暂无曲线数据", fill="#999")
            return

        vmin, vmax = min(all_vals), max(all_vals)
        if abs(vmax - vmin) < 1e-9:
            vmin -= 1.0
            vmax += 1.0
        margin = (vmax - vmin) * 0.08
        vmin -= margin
        vmax += margin

        x0, y0 = pad_l, pad_t
        x1, y1 = pad_l + plot_w, pad_t + plot_h
        self.canvas.create_rectangle(x0, y0, x1, y1, outline="#BBB")
        for i in range(5):
            gy = y1 - plot_h * i / 4
            val = vmin + (vmax - vmin) * i / 4
            self.canvas.create_line(x0, gy, x1, gy, fill="#E8E8E8")
            self.canvas.create_text(x0 - 6, gy, text=f"{val:.2g}", anchor=tk.E, font=("Consolas", 8), fill="#666")

        legend_x = x0 + 8
        for name, _, dq, color in self._channels:
            if not dq:
                continue
            pts = []
            n = len(dq)
            for j, v in enumerate(dq):
                px = x0 + plot_w * j / max(n - 1, 1)
                py = y1 - (v - vmin) / (vmax - vmin) * plot_h
                pts.extend([px, py])
            if len(pts) >= 4:
                self.canvas.create_line(*pts, fill=color, width=2, smooth=True)
            cur = dq[-1]
            self.canvas.create_rectangle(legend_x, y0 + 4, legend_x + 10, y0 + 14, fill=color, outline="")
            self.canvas.create_text(legend_x + 14, y0 + 9, text=f"{name}={cur:.4g}", anchor=tk.W, font=("Consolas", 9))
            legend_x += 100
