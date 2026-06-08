# Serial Debug Assistant / 串口调试助手

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

面向嵌入式与硬件调试的跨平台串口工具（Python + Tkinter + pyserial）。

**仓库地址：** https://github.com/zjingliang/serial_debug_assistant  
**作者：** [@zjingliang](https://github.com/zjingliang)

---

## 功能概览

- **串口连接**：端口扫描、波特率/数据位/校验/停止位/流控、DTR/RTS
- **收发调试**：ASCII/HEX、日志时间戳、保存文件、循环发送、快捷指令
- **工程工具**：CRC/SUM 校验、分包、自动应答、历史发送
- **Modbus RTU**：帧识别与解码、0x03 读寄存器组帧
- **实时曲线**：从接收文本提取数值并多通道绘图
- **多串口监控**：最多 4 路 COM 同屏页签监控

---

## 环境要求

- Python **3.8+**
- 依赖见 `requirements.txt`（主要为 **pyserial**）
- **tkinter**（Windows 安装 Python 时通常已带；Linux 需 `python3-tk`；Anaconda 执行 `conda install tk`）

---

## 安装与运行

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

---

## 使用提示

1. 选择端口与波特率，点击 **打开**。
2. 在 **数据接收** 查看回显；在 **数据发送** 输入后 **发送** 或 `Ctrl+Enter`。
3. 使用 Arduino IDE 等烧录前，请先在本工具 **关闭** 串口，避免端口占用。
4. 快捷指令保存在用户目录 `~/.serial-debug-assistant/shortcuts.json`，不会写入仓库目录。

---

## 目录结构

见 [README.md](README.md)（英文说明）。

---

## 许可证

[MIT License](LICENSE) — Copyright (c) 2026 [zjingliang](https://github.com/zjingliang)

---

## 发布到 GitHub

仓库已对应账号 [**zjingliang**](https://github.com/zjingliang) 下的 **`serial_debug_assistant`**。

在本地 `serial_debug_assistant` 目录下首次推送：

```bash
git init
git add .
git commit -m "Initial release: serial debug assistant v2.1.0"
git branch -M main
git remote add origin https://github.com/zjingliang/serial_debug_assistant.git
git push -u origin main
```

若远程仓库已有内容（例如 GitHub 上创建了 README），可先 `git pull origin main --rebase` 再 push，或在 GitHub 网页删除空仓库后重新创建。
