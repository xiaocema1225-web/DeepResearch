#!/bin/bash
# PYTHONUTF8=1：保证 .env（UTF-8 编码）在任何系统 locale 下都能被正确读取
export PYTHONUTF8=1
cd "$(dirname "$0")/backend" && langgraph dev
