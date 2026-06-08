# -*- coding: utf-8 -*-
"""Modbus RTU frame parser (sniffer / decode)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from checksum import crc16_modbus


@dataclass
class ModbusFrame:
    raw: bytes
    address: int
    function: int
    crc_ok: bool
    summary: str
    detail: str


FUNC_NAMES = {
    0x01: "读线圈",
    0x02: "读离散输入",
    0x03: "读保持寄存器",
    0x04: "读输入寄存器",
    0x05: "写单线圈",
    0x06: "写单寄存器",
    0x0F: "写多线圈",
    0x10: "写多寄存器",
}


def verify_crc(data: bytes) -> bool:
    if len(data) < 4:
        return False
    body = data[:-2]
    expect = int.from_bytes(data[-2:], "little")
    return crc16_modbus(body) == expect


def decode_frame(data: bytes) -> ModbusFrame:
    addr, func = data[0], data[1]
    crc_ok = verify_crc(data)
    base_func = func & 0x7F
    fname = FUNC_NAMES.get(base_func, f"功能码 0x{func:02X}")

    if func & 0x80:
        exc = data[2] if len(data) > 2 else 0
        summary = f"[Modbus] 站号 {addr} {fname} 异常 {exc}"
        detail = f"异常码={exc}  RAW={data.hex(' ').upper()}"
        return ModbusFrame(data, addr, func, crc_ok, summary, detail)

    detail = data.hex(" ").upper()
    summary = f"[Modbus] 站号 {addr} {fname}  {len(data)}B"

    if func in (0x01, 0x02, 0x03, 0x04) and len(data) == 8:
        start = int.from_bytes(data[2:4], "big")
        qty = int.from_bytes(data[4:6], "big")
        summary = f"[Modbus] 请求 站号{addr} {fname} 起始{start} 数量{qty}"
    elif func in (0x03, 0x04) and len(data) >= 5:
        bc = data[2]
        regs = [
            int.from_bytes(data[3 + i : 5 + i], "big")
            for i in range(0, min(bc, len(data) - 5), 2)
        ]
        summary = f"[Modbus] 应答 站号{addr} {fname} {len(regs)}个寄存器"
        detail = " ".join(f"{r}" for r in regs[:24]) + (" …" if len(regs) > 24 else "")
    elif func in (0x05, 0x06) and len(data) >= 8:
        reg = int.from_bytes(data[2:4], "big")
        val = int.from_bytes(data[4:6], "big")
        summary = f"[Modbus] 站号{addr} {fname} 地址{reg} 值0x{val:04X}({val})"
    elif func == 0x10 and len(data) >= 8:
        start = int.from_bytes(data[2:4], "big")
        qty = int.from_bytes(data[4:6], "big")
        summary = f"[Modbus] 站号{addr} {fname} 起始{start} 数量{qty}"

    if not crc_ok:
        summary += " [CRC错误]"

    return ModbusFrame(data, addr, func, crc_ok, summary, detail)


class ModbusStreamParser:
    """Scan byte stream for valid Modbus RTU frames via CRC."""

    MAX_LEN = 256

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> List[ModbusFrame]:
        self._buf.extend(chunk)
        out: List[ModbusFrame] = []
        while len(self._buf) >= 4:
            matched = False
            upper = min(len(self._buf), self.MAX_LEN)
            for length in range(4, upper + 1):
                candidate = bytes(self._buf[:length])
                if not verify_crc(candidate):
                    continue
                addr, func = candidate[0], candidate[1]
                if addr == 0 or addr > 247:
                    continue
                if func == 0 and length > 8:
                    continue
                try:
                    out.append(decode_frame(candidate))
                except Exception:
                    pass
                del self._buf[:length]
                matched = True
                break
            if not matched:
                del self._buf[0]
        if len(self._buf) > 1024:
            del self._buf[:-128]
        return out

    def clear(self) -> None:
        self._buf.clear()
