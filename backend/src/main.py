# -*- coding: utf-8 -*-
"""
本地自测入口（医药投资版）。

安全说明：API Key 一律从 .env / 环境变量读取，禁止在代码中硬编码
（原人类参与版 src/main.py 曾硬编码密钥，医药投资版已修复——
 对应 PRD 九章"安全"与合规要求）。
"""
from dotenv import load_dotenv

# override=True：.env 文件优先，系统环境变量兜底
load_dotenv(override=True)

from agent.base_agent import Agent, WebSearchAgent  # noqa: E402
from loguru import logger  # noqa: E402

if __name__ == '__main__':
    # 自测1：LLM 基础调用
    agent = Agent()
    response = agent("GLP-1 受体激动剂的作用机制是什么？一句话回答。")
    print(response)

    # 自测2：双引擎检索（国内走百炼，国外走 Firecrawl）
    searcher = WebSearchAgent()
    logger.info(searcher.step(prompt="GLP-1 减肥药 医保 获批 进展", count=5))
    logger.info(searcher.step(prompt="semaglutide phase 3 cardiovascular outcomes FDA", count=5))
