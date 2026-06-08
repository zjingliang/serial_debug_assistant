@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 安装依赖
echo 正在安装 pyserial ...
python -m pip install -r requirements.txt
if errorlevel 1 pause
