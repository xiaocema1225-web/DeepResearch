@echo off
rem PYTHONUTF8=1：让 Python 以 UTF-8 读取文件，修复中文 Windows 下
rem langgraph dev 读取 UTF-8 编码 .env 时的 UnicodeDecodeError (gbk)
set PYTHONUTF8=1
cd /d "%~dp0backend"
langgraph dev
