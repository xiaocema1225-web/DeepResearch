from typing import List
from pydantic import BaseModel, Field


class SearchQueryItem(BaseModel):
    query: str = Field(
        description="用于网络检索的查询语句."
    )
    region: str = Field(
        description="目标信源区域：'domestic'（中文/国内信源，走阿里百炼检索）或 'international'（英文/海外信源，走Firecrawl检索）."
    )


class SearchQueryList(BaseModel):
    queries: List[SearchQueryItem] = Field(
        description="用于网络检索的查询列表，每条查询标注目标信源区域."
    )
    rationale: str = Field(
        description="简要解释为什么这些问题与研究主题相关."
    )


class Reflection(BaseModel):
    is_sufficient: bool = Field(
        description="所提供的概要是否足以回答用户的问题."
    )
    knowledge_gap: str = Field(
        description="描述哪些信息缺失或需要澄清."
    )
    follow_up_queries: List[SearchQueryItem] = Field(
        description="解决知识差距的后续查询列表，每条查询标注目标信源区域."
    )


class PlanReflection(BaseModel):
    satisfy: bool = Field(
        description="用户对生成的研究计划是否满意."
    )
