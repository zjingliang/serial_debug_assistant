@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 串口调试助手
echo 正在启动（首次使用请先运行 install_deps.bat）...
python -u main.py
if errorlevel 1 (
  echo.
  echo 若提示缺少 tkinter，Anaconda 用户请执行: conda install tk
  pause
)
