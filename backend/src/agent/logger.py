# -*- coding: utf-8 -*-
"""统一日志配置（loguru）"""
import sys
import os
from loguru import logger

from agent.config import get_config


def setup_logger():
    """初始化日志：控制台 + 落盘文件（按天滚动，留痕审计友好）"""
    logger.remove()
    log_level = get_config("LOG_LEVEL", "INFO")
    logger.add(sys.stderr, level=log_level)

    log_dir = get_config("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger.add(
        os.path.join(log_dir, "med_research_{time:YYYY-MM-DD}.log"),
        rotation="00:00",
        retention="90 days",
        level="DEBUG",
        encoding="utf-8",
    )


def log_request_details(body_data):
    """记录请求体详情（供问题定位与过程留痕）"""
    try:
        logger.debug(f"请求详情: {body_data}")
    except Exception:
        logger.debug("请求详情记录失败（非结构化数据）")
