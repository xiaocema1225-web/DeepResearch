# -*- coding: utf-8 -*-
"""
双引擎网页检索模块（医药投资版）

架构定位（见《架构设计/系统架构与部署视图-医药投资版.md》2.4 外部能力层）：
- 国内/中文信源（药监局公告、医保政策、中文医药媒体、上市公司中文公告等）
  → 阿里百炼平台检索 API（DashScope Generation 联网搜索）
- 国外/英文信源（ClinicalTrials.gov、FDA、PubMed、SEC 财报、海外医药媒体等）
  → Firecrawl Search API（https://api.firecrawl.dev/v1/search）

设计要点：
1. 路由（SearchRouter）：按 LLM 生成的 region 标注（见 tools_and_schemas.SearchQueryItem）
   决定走哪个引擎；未标注时按查询语言自动判别；单引擎失败自动降级到另一引擎。
2. 统一输出：SearchResult 携带完整来源元数据（title/url/snippet/engine/抓取时间），
   这是 PRD 8.7"引用可回溯"和架构文档"来源元数据适配器"的落点。
3. 限流：百炼与 Firecrawl 各自独立的 QPS 限制器，429 时指数退避重试。
"""

import json
import os
import re
import time
import threading
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import requests
from loguru import logger

from agent.config import get_config


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

class SearchResult:
    """统一检索结果条目（对应架构文档 2.4 的来源元数据结构）"""

    def __init__(self, title: str, url: str, snippet: str, engine: str,
                 content: str = "", published_at: str = "", unverified: bool = False):
        self.title = title or ""
        self.url = url or ""
        self.snippet = snippet or ""
        self.engine = engine                    # "bailian" / "firecrawl"
        self.content = content                  # Firecrawl 可带回正文 markdown
        self.published_at = published_at
        self.unverified = unverified            # True = 模型直接生成、未解析出可验证来源
        self.captured_at = datetime.now(timezone.utc).isoformat()  # 抓取留证时间

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "engine": self.engine,
            "content": self.content,
            "published_at": self.published_at,
            "unverified": self.unverified,
            "captured_at": self.captured_at,
        }


# ---------------------------------------------------------------------------
# 速率限制器（令牌桶，线程安全）
# ---------------------------------------------------------------------------

class RateLimiter:
    def __init__(self, max_qps: float):
        self.max_qps = max_qps
        self.min_interval = 1.0 / max_qps
        self.last_request_time = 0.0
        self.lock = threading.Lock()

    def acquire(self) -> float:
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.min_interval:
                wait = self.min_interval - elapsed
                time.sleep(wait)
                self.last_request_time = time.time()
                return wait
            self.last_request_time = now
            return 0.0


_bailian_limiter: Optional[RateLimiter] = None
_firecrawl_limiter: Optional[RateLimiter] = None


def get_bailian_limiter() -> RateLimiter:
    global _bailian_limiter
    if _bailian_limiter is None:
        _bailian_limiter = RateLimiter(float(get_config("BAILIAN_SEARCH_MAX_QPS", "5")))
    return _bailian_limiter


def get_firecrawl_limiter() -> RateLimiter:
    global _firecrawl_limiter
    if _firecrawl_limiter is None:
        _firecrawl_limiter = RateLimiter(float(get_config("FIRECRAWL_SEARCH_MAX_QPS", "5")))
    return _firecrawl_limiter


# ---------------------------------------------------------------------------
# 引擎一：阿里百炼（国内/中文信源）
# ---------------------------------------------------------------------------

class BailianSearchEngine:
    """
    阿里百炼平台联网搜索。

    通过 DashScope 兼容模式调用支持联网搜索的模型（enable_search=True），
    要求模型以结构化 JSON 返回检索到的网页列表（title/url/snippet），
    从而保留引用所需的来源元数据。

    配置项（.env）：
      APP_TOKEN          百炼 API Key（与 LLM 共用）
      LLM_BASE_URL       百炼兼容模式端点，如 https://dashscope.aliyuncs.com/compatible-mode/v1
      BAILIAN_SEARCH_MODEL  用于联网搜索的模型，默认 qwen-plus（须支持 enable_search）
    """

    SEARCH_PROMPT = (
        "请联网搜索以下内容，并把你实际检索到的网页结果以 JSON 数组返回。"
        "每个元素包含 title（网页标题）、url（网页链接）、snippet（与查询最相关的原文片段，100-200字）。"
        "只返回 JSON 数组本身，不要输出任何其他文字。搜索内容：{query}"
    )

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.model_id = get_config("BAILIAN_SEARCH_MODEL", "qwen-plus")

    def search(self, query: str, count: int = 10) -> List[SearchResult]:
        limiter = get_bailian_limiter()
        prompt = self.SEARCH_PROMPT.format(query=query)
        last_raw_text = ""

        for attempt in range(self.max_retries):
            try:
                limiter.acquire()
                raw_text = self._call(query=query, prompt=prompt)
                if raw_text:
                    last_raw_text = raw_text
                results = self._parse_results(raw_text, query)
                if results:
                    return results[:count]
                raise Exception("百炼联网搜索返回为空（未解析出带来源链接的结构化结果）")
            except Exception as e:
                msg = str(e)
                logger.error(f"百炼检索错误（尝试 {attempt + 1}/{self.max_retries}）：{msg}")
                if "429" in msg:
                    time.sleep(5 * (attempt + 1))      # 429 指数退避
                elif attempt < self.max_retries - 1:
                    time.sleep(2)

        # 重试耗尽但模型有正文输出：保留原文并显式标注"来源未验证"，不再静默丢弃。
        # 该条目不带 url，下游 graph.web_search 节点会据此写入检索质量披露。
        if last_raw_text:
            logger.warning(f"百炼检索连续 {self.max_retries} 次未解析出结构化来源，保留原始正文并标注来源未验证: {query}")
            return [SearchResult(
                title=f"百炼联网检索原始正文（来源未验证）：{query[:30]}",
                url="",
                snippet=last_raw_text[:800],
                engine="bailian",
                content=last_raw_text,
                unverified=True,
            )]
        return []

    def _call(self, query: str, prompt: str) -> str:
        """调用百炼兼容模式接口，返回模型原始输出文本（结构化解析在 search 中进行）。"""
        from openai import OpenAI

        client = OpenAI(
            api_key=get_config("APP_TOKEN"),
            base_url=get_config("LLM_BASE_URL"),
        )
        response = client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            extra_body={
                "enable_search": True,
                "search_options": {"forced_search": True, "enable_source": True},
            },
        )
        return response.choices[0].message.content or ""

    def _parse_results(self, text: str, query: str) -> List[SearchResult]:
        """从模型输出中解析结构化网页结果。"""
        # 提取 JSON 数组（模型可能包裹在 ```json 代码块中）
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            logger.warning(f"百炼检索未返回 JSON 数组，查询: {query}")
            # 降级：把整段文本作为一条无 URL 结果会导致引用缺失，故返回空
            return []
        try:
            items = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            logger.error(f"百炼检索结果 JSON 解析失败: {e}")
            return []

        results = []
        for item in items:
            if isinstance(item, dict) and item.get("url"):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                    engine="bailian",
                ))
        return results


# ---------------------------------------------------------------------------
# 引擎二：Firecrawl（国外/英文信源）
# ---------------------------------------------------------------------------

class FirecrawlSearchEngine:
    """
    Firecrawl Search API（https://api.firecrawl.dev/v2/search，v1 已弃用）。

    用于检索国外公开网页：ClinicalTrials.gov、FDA、PubMed、SEC/公司 IR 页、
    海外医药媒体（Endpoints、Fierce、STAT 等）。

    配置项（.env）：
      FIRECRAWL_API_KEY   Firecrawl API Key
      FIRECRAWL_BASE_URL  可选，自托管时覆盖，默认 https://api.firecrawl.dev
      FIRECRAWL_SCRAPE_CONTENT  是否抓取正文 markdown（true/false，默认 false 省额度）
    """

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.base_url = get_config("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev")
        self.scrape_content = get_config("FIRECRAWL_SCRAPE_CONTENT", "false").lower() == "true"

    def search(self, query: str, count: int = 10) -> List[SearchResult]:
        api_key = get_config("FIRECRAWL_API_KEY")
        if not api_key:
            logger.error("未配置 FIRECRAWL_API_KEY，Firecrawl 检索不可用")
            return []

        limiter = get_firecrawl_limiter()
        payload: Dict[str, Any] = {"query": query, "limit": count}
        if self.scrape_content:
            payload["scrapeOptions"] = {"formats": ["markdown"]}

        for attempt in range(self.max_retries):
            try:
                limiter.acquire()
                resp = requests.post(
                    f"{self.base_url}/v2/search",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=60,
                )
                if resp.status_code == 429:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"Firecrawl 429 限流，{wait} 秒后重试")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return self._parse_results(resp.json())
            except requests.RequestException as e:
                logger.error(f"Firecrawl 检索错误（尝试 {attempt + 1}/{self.max_retries}）：{e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
        return []

    def _parse_results(self, payload: Dict[str, Any]) -> List[SearchResult]:
        """解析 Firecrawl 搜索响应（兼容 v2 与旧 v1 两种返回结构）。

        v2: {"success": true, "data": {"web": [ {url,title,description,position}, ... ]}}
        v1(已弃用): {"success": true, "data": [ {url,title,description}, ... ]}
        """
        if not payload.get("success", True):
            logger.error(f"Firecrawl 返回失败: {payload}")
            return []

        data = payload.get("data") or {}
        if isinstance(data, dict):
            items = data.get("web") or data.get("results") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []

        results = []
        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", "") or (item.get("markdown", "")[:300] if item.get("markdown") else ""),
                engine="firecrawl",
                content=item.get("markdown", "") if self.scrape_content else "",
            ))
        return results


# ---------------------------------------------------------------------------
# 路由与降级
# ---------------------------------------------------------------------------

_DOMESTIC_HINTS = (
    "医保", "集采", "NMPA", "CDE", "药监局", "中标", "招标", "A股", "港股",
    "恒瑞", "百济", "信达", "药明", "复星", "license-in",
)

_CJK_RE = re.compile(r"[一-鿿]")


def detect_region(query: str) -> str:
    """无显式 region 标注时按内容自动判别：含中文或国内关键词 → domestic。"""
    for hint in _DOMESTIC_HINTS:
        if hint.lower() in query.lower():
            return "domestic"
    return "domestic" if _CJK_RE.search(query) else "international"


def hybrid_search(query: str, count: int = 10, region: Optional[str] = None) -> List[SearchResult]:
    """
    双引擎混合检索入口。

    路由逻辑（对应架构文档 ADR-4 单源隔离 + 降级）：
    1. region 显式指定（LLM 在生成查询时标注）→ 优先对应引擎；
    2. 未指定 → detect_region 自动判别；
    3. 主引擎失败或返回空 → 自动降级到另一引擎，保证单引擎故障不阻断流水线。
    """
    region = region or detect_region(query)
    bailian = BailianSearchEngine()
    firecrawl = FirecrawlSearchEngine()

    primary, secondary, primary_name = (
        (bailian, firecrawl, "bailian") if region == "domestic"
        else (firecrawl, bailian, "firecrawl")
    )

    logger.info(f"检索路由：查询[{query[:50]}...] → 主引擎 {primary_name}")
    results = primary.search(query, count=count)
    # 主引擎"无结果"或"只有来源未验证的原始正文"都视为未获得可验证来源，降级另一引擎
    verified = [r for r in results if not getattr(r, "unverified", False)]
    if not verified:
        logger.warning(f"主引擎 {primary_name} 无结果或未通过来源校验，降级到另一引擎重试")
        secondary_results = secondary.search(query, count=count)
        # 合并：另一引擎的可验证结果优先；百炼保留的未验证正文仍然带回（供披露与参考）
        results = secondary_results + [r for r in results if getattr(r, "unverified", False)]
    if not results:
        logger.error(f"双引擎均无结果: {query}")
    return results


if __name__ == "__main__":
    # 自测：国内查询走百炼，海外查询走 Firecrawl
    rs = hybrid_search("GLP-1 减肥药 医保 进展", count=5, region="domestic")
    for r in rs:
        print(r.engine, r.title, r.url)
    rs = hybrid_search("semaglutide phase 3 trial results NCT", count=5, region="international")
    for r in rs:
        print(r.engine, r.title, r.url)
