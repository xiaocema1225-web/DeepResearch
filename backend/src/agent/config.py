# -*- coding: utf-8 -*-
"""
统一配置读取（医药投资版）。

读取优先级（与产品约定一致）：
1. 优先读项目 .env 文件（backend/.env）；
2. 若 .env 中没有该键（或值为空），回退读取系统环境变量；
3. 都没有则返回 default。

注意：python-dotenv 的 load_dotenv() 默认行为是"系统环境变量优先"，
与本约定相反，因此这里用 dotenv_values() 直接读取 .env 文件内容
（不污染 os.environ），自行实现"文件优先、系统兜底"的合并顺序。
"""

import os
from pathlib import Path
from typing import Dict, Optional

from dotenv import dotenv_values, find_dotenv
from loguru import logger

# backend/.env（本文件位于 backend/src/agent/config.py，向上三级即 backend/）
_DEFAULT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

_env_file_cache: Optional[Dict[str, Optional[str]]] = None


def _load_env_file() -> Dict[str, Optional[str]]:
    """加载 .env 文件内容（带缓存）。文件不存在时返回空字典。"""
    global _env_file_cache
    if _env_file_cache is not None:
        return _env_file_cache

    env_path = find_dotenv(usecwd=True)
    if not env_path and _DEFAULT_ENV_PATH.is_file():
        env_path = str(_DEFAULT_ENV_PATH)

    if env_path:
        _env_file_cache = dotenv_values(env_path)
        logger.debug(f"已加载 .env 文件: {env_path}（{len(_env_file_cache)} 个键）")
    else:
        _env_file_cache = {}
        logger.debug("未找到 .env 文件，配置将全部来自系统环境变量")
    return _env_file_cache


def get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    读取配置：.env 文件优先，系统环境变量兜底。

    Args:
        key: 配置键名（如 APP_TOKEN、FIRECRAWL_API_KEY）
        default: 两处都没有时的返回值

    Returns:
        配置值；.env 中值为空字符串视为"没有"，继续回退系统环境变量。
    """
    file_value = _load_env_file().get(key)
    if file_value is not None and str(file_value).strip() != "":
        return str(file_value)
    return os.environ.get(key, default)


def reload_env_cache() -> None:
    """清空 .env 缓存（运行时修改了 .env 文件后调用）。"""
    global _env_file_cache
    _env_file_cache = None
