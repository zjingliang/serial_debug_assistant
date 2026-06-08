# -*- coding: utf-8 -*-
"""Serial port I/O core."""

from __future__ import annotations

import sys
import threading
import time
from typing import Callable, List, Optional, Tuple

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

BAUD_RATES = (
    "1200", "2400", "4800", "9600", "19200", "38400", "57600",
    "115200", "230400", "460800", "921600", "1000000", "1500000", "2000000",
)


def enumerate_serial_ports() -> List[Tuple[str, str]]:
    found: dict[str, str] = {}
    if serial:
        try:
            for p in serial.tools.list_ports.comports():
                desc = (p.description or p.name or "").strip()
                found[p.device] = desc or "Serial"
        except Exception:
            pass
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
            i = 0
            while True:
                try:
                    _n, port_val, _t = winreg.EnumValue(key, i)
                    i += 1
                    if port_val and port_val not in found:
                        found[port_val] = "Registry"
                except OSError:
                    break
            winreg.CloseKey(key)
        except OSError:
            pass
    return sorted(found.items(), key=lambda x: x[0].upper())


def parse_port(selection: str) -> str:
    import re

    s = (selection or "").strip().split(" — ")[0].strip()
    if not s:
        return ""
    m = re.match(r"^(COM\d+)", s, re.I)
    if m:
        return m.group(1).upper()
    return s.split()[0]


def parity_py(name: str) -> str:
    m = {
        "N": serial.PARITY_NONE,
        "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD,
        "M": serial.PARITY_MARK,
        "S": serial.PARITY_SPACE,
    }
    return m.get(name, serial.PARITY_NONE)


def stopbits_py(name: str) -> float:
    m = {"1": serial.STOPBITS_ONE, "1.5": serial.STOPBITS_ONE_POINT_FIVE, "2": serial.STOPBITS_TWO}
    return m.get(name, serial.STOPBITS_ONE)


class SerialSession:
    def __init__(self, on_rx: Callable[[bytes], None]) -> None:
        self.on_rx = on_rx
        self.ser: Optional[serial.Serial] = None
        self._alive = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.rx_frames = 0
        self.tx_frames = 0

    @property
    def open(self) -> bool:
        return bool(self.ser and self.ser.is_open)

    def connect(
        self,
        port: str,
        baud: int,
        databits: int,
        parity: str,
        stopbits: str,
        flow: str,
    ) -> None:
        self.disconnect()
        if not serial:
            raise RuntimeError("未安装 pyserial")
        xonxoff = flow == "XON/XOFF"
        rtscts = flow == "RTS/CTS"
        self.ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=databits,
            parity=parity_py(parity),
            stopbits=stopbits_py(stopbits),
            xonxoff=xonxoff,
            rtscts=rtscts,
            timeout=0.05,
        )
        self.rx_bytes = self.tx_bytes = self.rx_frames = self.tx_frames = 0
        self._alive.set()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        self._alive.clear()
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def write(self, data: bytes) -> int:
        if not self.open or not data:
            return 0
        assert self.ser
        n = self.ser.write(data)
        self.ser.flush()
        self.tx_bytes += n
        self.tx_frames += 1
        return n

    def set_dtr(self, v: bool) -> None:
        if self.open and self.ser:
            self.ser.dtr = v

    def set_rts(self, v: bool) -> None:
        if self.open and self.ser:
            self.ser.rts = v

    def _read_loop(self) -> None:
        while self._alive.is_set() and self.ser and self.ser.is_open:
            try:
                chunk = self.ser.read(4096)
                if chunk:
                    self.rx_bytes += len(chunk)
                    self.on_rx(chunk)
                else:
                    time.sleep(0.01)
            except Exception:
                break
