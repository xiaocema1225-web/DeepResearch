from typing import Any, Dict, List, Tuple
import re
from langchain_core.messages import AnyMessage, AIMessage, HumanMessage
from loguru import logger


def get_research_topic(messages: List[AnyMessage], ignore_contexts: List[str]=None) -> str:
    """
    从messages中获取research主题。
    """
    # check if request has a history and combine the messages into a single string
    if not ignore_contexts:
        ignore_contexts = []
    if len(messages) == 1:
        research_topic = messages[-1].content
    else:
        research_topic = ""
        for message in messages:
            if isinstance(message, HumanMessage):
                research_topic += f"User: {message.content}\n"
            elif isinstance(message, AIMessage) and message.content not in ignore_contexts:
                research_topic += f"Assistant: {message.content}\n"
    return research_topic

def get_last_user_response(messages: List[AnyMessage]) -> str:
    user_messages = [msg for msg in messages if isinstance(msg, HumanMessage)]
    if user_messages:
        return f"User: {user_messages[-1].content}\n"
    return ""

def resolve_urls(urls_to_resolve: List[Any], id: int) -> Dict[str, str]:
    """
    创建一个ai搜索url(可能非常长)到一个短url的映射，每个URL有一个唯一的id.
    每个原始URL获得一致的缩写形式，同时保持唯一性.
    """
    prefix = f"https://search.com/id/"

    # 检查urls_to_resolve是否为None或空列表
    if urls_to_resolve is None:
        logger.warning(f"urls_to_resolve为None，返回空映射")
        return {}

    if not isinstance(urls_to_resolve, list):
        logger.warning(f"urls_to_resolve不是列表类型: {type(urls_to_resolve)}，返回空映射")
        return {}

    if len(urls_to_resolve) == 0:
        logger.warning(f"urls_to_resolve为空列表，返回空映射")
        return {}

    urls = [site["url"] for site in urls_to_resolve if isinstance(site, dict) and "url" in site]

    # Create a dictionary that maps each unique URL to its first occurrence index
    resolved_map = {}
    for idx, url in enumerate(urls):
        if url not in resolved_map:
            resolved_map[url] = f"{prefix}{id}-{idx}"

    return resolved_map


# ---------------------------------------------------------------------------
# 报告引用校验（防模型自造 URL）
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s\)\]\}\"'，。；、》）】]+")
_URL_TRAILING_PUNCT = ".,;:，。；：、"


def sanitize_report_urls(content: str, sources_gathered: List[Dict[str, Any]]) -> Tuple[str, List[Tuple[str, str]]]:
    """
    校验最终报告中的链接，检测并重写模型自造的伪造 URL。

    合法链接集合 = sources_gathered 中登记的真实检索来源（value 为原始长 URL）。
    报告中出现的任何不在该集合内的 URL（含未被还原的 search.com/id 短链），
    均视为模型自造链接：markdown 链接降级为纯文本标注，裸链接替换为告警文本。

    Args:
        content: final_answer 模型生成的报告正文
        sources_gathered: 检索阶段登记的来源列表 [{"short_url", "value", "label"}, ...]

    Returns:
        (清洗后的正文, 被移除的链接列表 [(label, url), ...])
    """
    valid_urls = {s.get("value", "") for s in sources_gathered if s.get("value")}
    removed: List[Tuple[str, str]] = []

    def _is_valid(url: str) -> bool:
        return url.rstrip(_URL_TRAILING_PUNCT) in valid_urls

    # 先处理 markdown 链接：[label](url)
    def _repl_md(m: "re.Match") -> str:
        label, url = m.group(1), m.group(2)
        if _is_valid(url):
            return m.group(0)
        removed.append((label, url))
        return f"{label}（⚠️ 来源链接未通过校验，已移除）"

    content = _MD_LINK_RE.sub(_repl_md, content)

    # 再处理裸 URL（含未被还原的 search.com/id 短链；合法 markdown 链接内的 URL 已在合法集合中，原样保留）
    def _repl_bare(m: "re.Match") -> str:
        url = m.group(0)
        if _is_valid(url):
            return url
        removed.append(("", url))
        return "（⚠️ 来源链接未通过校验，已移除）"

    content = _BARE_URL_RE.sub(_repl_bare, content)

    if removed:
        logger.warning(f"引用校验：检测到 {len(removed)} 个未通过来源校验的链接（模型自造 URL），已移除：{removed}")
    return content, removed
