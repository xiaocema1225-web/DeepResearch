from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import add_messages
from typing_extensions import Annotated


import operator


class OverallState(TypedDict):
    messages: Annotated[list, add_messages]
    plan: str
    plan_status: str
    plan_messages: Annotated[list, add_messages]
    search_query: Annotated[list, operator.add]
    web_search_result: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]
    search_warnings: Annotated[list, operator.add]  # 检索异常/来源未验证告警，随节点累加
    initial_search_query_count: int
    max_research_loops: int
    research_loop_count: int
    reasoning_model: str


class ReflectionState(TypedDict):
    is_sufficient: bool
    knowledge_gap: str
    follow_up_queries: Annotated[list, operator.add]
    research_loop_count: int
    number_of_ran_queries: int
    max_research_loops: int


class Query(TypedDict):
    query: str
    rationale: str


class QueryGenerationState(TypedDict):
    search_query: list[Query]


class WebSearchState(TypedDict):
    search_query: str
    region: str  # "domestic"（百炼）/ "international"（Firecrawl），可空表示自动判别
    reasoning_model: str  # 任务级模型（随研究强度下发），透传给检索摘要节点
    id: str

class PlanState(TypedDict):
    plan: str


@dataclass(kw_only=True)
class SearchStateOutput:
    running_summary: str = field(default=None)  # Final report
