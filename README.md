# Serial Debug Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Cross-platform **serial port debugging tool** for embedded and hardware engineers.  
Built with **Python 3**, **Tkinter**, and **pyserial** — no extra GUI frameworks required.

**Repository:** https://github.com/zjingliang/serial_debug_assistant  
**Author:** [@zjingliang](https://github.com/zjingliang)

📄 [中文说明 README.zh-CN.md](README.zh-CN.md)

> 中文界面 · 适用于 Windows / macOS / Linux（需可用串口与 tkinter）

---

## Features

| Area | Capability |
|------|------------|
| **Connection** | Port scan, baud / data / parity / stop / flow control, DTR & RTS |
| **Receive** | ASCII or HEX, log timestamps, auto-wrap, save to file |
| **Transmit** | ASCII or HEX, escape sequences, AT auto-CRLF, suffix bytes, loop send |
| **Engineering** | CRC/SUM/XOR calculator, packet framing, auto-reply rules, shortcuts |
| **Modbus RTU** | Frame sniffing & decode, read-holding-registers (0x03) builder |
| **Plotting** | Real-time multi-channel strip chart from parsed numeric data |
| **Multi-port** | Monitor up to 4 COM ports in separate tabs |

---

## Requirements

- **Python 3.8+**
- **pyserial** — see `requirements.txt`
- **tkinter** — usually bundled with Python on Windows; on Linux you may need `python3-tk`; Anaconda: `conda install tk`

---

## Quick start

### Windows

```bat
install_deps.bat
run.bat
```

### macOS / Linux

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

1. Select **port** and **baud rate**, click **打开** (Open).  
2. View traffic in **数据接收**; type in **数据发送** and click **发送** or press `Ctrl+Enter`.  
3. Close the port before other tools (e.g. IDE upload) use the same COM port.

---

## Project layout

```
serial_debug_assistant/
├── main.py                 # Main application
├── serial_io.py            # Serial port session & enumeration
├── modbus.py               # Modbus RTU parser
├── plot_window.py          # Real-time plot window
├── multi_port_window.py    # Multi-port monitor
├── checksum.py             # CRC / checksum algorithms
├── requirements.txt
├── run.bat                 # Windows launcher
├── install_deps.bat
├── LICENSE                 # MIT
└── README.md
```

User shortcuts are stored under `~/.serial-debug-assistant/shortcuts.json` (created at runtime, not part of the repo).

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+Enter` | Send |
| `F5` | Refresh port list |

---

## Modbus & plotting

- Enable **Modbus RTU 解析** under receive settings, or open **Modbus 工具** to build a read request.
- Open **实时曲线** to plot numeric values extracted from received text (regex configurable).
- Open **多串口监控** to watch up to four ports in parallel (independent of the main port).

---

## Contributing

Issues and pull requests are welcome. Please keep changes focused and match the existing style.

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE).  
Copyright (c) 2026 [zjingliang](https://github.com/zjingliang).
