import json

from agent.tools_and_schemas import SearchQueryList, Reflection, PlanReflection
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langgraph.types import Send
from langgraph.graph import StateGraph
from langgraph.graph import START, END
from langchain_core.runnables import RunnableConfig

from agent.state import (
    OverallState,
    QueryGenerationState,
    ReflectionState,
    WebSearchState,
)
from agent.configuration import Configuration
from agent.prompts import (
    get_current_date,
    query_writer_instructions,
    web_searcher_instructions,
    reflection_instructions,
    answer_instructions,
    plan_instructions,
    plan_reflection_instructions
)
from agent.post import Post
from agent.utils import (
    get_research_topic,
    get_last_user_response,
    resolve_urls,
    sanitize_report_urls,
)
from agent.base_agent import Agent, JsonAgent, WebSearchAgent
from loguru import logger
# override=True：.env 文件中的值优先于系统环境变量注入 os.environ，
# 与 agent/config.py 的".env 优先、系统兜底"约定保持一致
load_dotenv(override=True)

GENERATE_PLAN_NODE = "generate_plan"
GENERATE_SEARCH_NODE = "generate_search"
WEB_SEARCH_NODE = "web_search"
CRITIQUE_NODE = "critique"
FINAL_ANSWER_NODE = "final_answer"


def effective_model(state: dict, configurable: "Configuration") -> str:
    """
    解析本次任务实际使用的模型。

    优先级：任务状态里的 reasoning_model（前端按研究强度下发：
    轻→deepseek-v4.1-flash / 中→qwen3.8-flash / 深→qwen3.8-max-0902）
    高于配置默认值，保证同一任务内所有节点用同一个模型。
    """
    return state.get("reasoning_model") or configurable.query_generator_model

# 节点定义
def generate_plan(state: OverallState, config: RunnableConfig)-> OverallState:
    """
    生成调研计划的LangGraph节点

    基于用户的医药调研课题，使用LLM生成一份带医药投研维度的详细调研计划。

    Args:
        state: 包含用户问题的当前图状态
        config: 可运行配置，包括LLM提供商设置

    Returns:
        包含计划状态更新的字典，包括plan和plan_status键
    """
    logger.info("正在生成调研计划...")
    if state.get("plan_status", "unconfirmed") != "unconfirmed":
        return {}

    configurable = Configuration.from_runnable_config(config)
    agent = Agent(model_id=effective_model(state, configurable))
    agent.set_step_prompt(plan_instructions)
    response = agent.step(
        current_date=get_current_date(),
        research_topic=get_research_topic(state["messages"], [msg.content for msg in state["plan_messages"]]),
        research_proposal=state.get("plan", "")
    )
    response = Post.extract_pattern(response, pattern="markdown")
    logger.info(state)
    logger.info(response)

    return {"messages": [AIMessage(content=response)],
            "plan": response,
            "plan_status": "unconfirmed",
            "plan_messages": [AIMessage(content=response)]}

def evaluate_plan(state: OverallState, config: RunnableConfig)-> ReflectionState:
    """
    评估调研计划的LangGraph节点（人机协作关键点：确认前不检索）

    分析当前计划并根据用户反馈决定下一步行动：
    - 如果用户确认计划，继续生成查询
    - 如果用户需要修改计划，重新生成
    - 如果用户未确认，等待确认
    """
    configurable = Configuration.from_runnable_config(config)
    plan = state.get("plan", None)
    if state.get("plan_status", "unconfirmed") == "unconfirmed":
        logger.info("等待用户确认调研计划...")
        return "awaiting_plan_confirmation"

    if not plan:
        logger.info("没有计划需要评估。")
        return "replan"
    else:
        context = get_last_user_response(state["messages"])
        if "开始研究" in context:
            return GENERATE_SEARCH_NODE
        if "需求确认" in context:
            return GENERATE_SEARCH_NODE

        agent = JsonAgent(model_id=effective_model(state, configurable), keys=PlanReflection)
        agent.set_step_prompt(plan_reflection_instructions)
        result = agent.step(
            research_proposal=state.get("plan", ""),
            context=context,
        )
        if result.satisfy:
            return GENERATE_SEARCH_NODE
        return "replan"


def generate_query(state: OverallState, config: RunnableConfig) -> QueryGenerationState:
    """
    基于调研课题生成检索查询的LangGraph节点

    使用LLM生成带 region 信源路由标注（domestic→百炼 / international→Firecrawl）
    的检索查询列表。
    """
    configurable = Configuration.from_runnable_config(config)
    logger.info(f"LangGraph节点开始运行.....，配置：[{config}]")
    # 检查自定义初始搜索查询数量
    if state.get("initial_search_query_count") is None:
        state["initial_search_query_count"] = configurable.number_of_initial_queries

    agent = JsonAgent(model_id=effective_model(state, configurable), keys=SearchQueryList)
    agent.set_step_prompt(query_writer_instructions)
    result = agent.step(
        current_date=get_current_date(),
        research_topic=get_research_topic(state["messages"]),
        number_queries=state["initial_search_query_count"],
        research_proposal=state.get("plan", "")
    )
    logger.info(f"生成待检索内容.....{state}")
    logger.info(f"待检索内容生成结果: {result}")
    # 兼容 LLM 偶尔返回纯字符串列表的情况
    normalized = []
    for item in result.queries:
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({"query": item.query, "region": item.region})
    return {"search_query": normalized}


def send_to_web_search(state: QueryGenerationState):
    """
    将检索查询发送到web_search节点的LangGraph节点（并行检索，单源隔离）

    为每条检索查询生成一个检索节点，携带 query + region 路由标注。
    """
    logger.info(f"准备发送请求给检索节点（双引擎：百炼/Firecrawl）......")
    return [
        Send(WEB_SEARCH_NODE, {
            "search_query": item["query"] if isinstance(item, dict) else item,
            "region": item.get("region") if isinstance(item, dict) else None,
            "reasoning_model": state.get("reasoning_model"),
            "id": int(idx),
        })
        for idx, item in enumerate(state["search_query"])
    ]


def web_search(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """
    执行网页检索的节点（双引擎：国内→阿里百炼，国外→Firecrawl）

    Args:
        state: 包含检索查询、region 标注和研究循环计数的当前图状态
        config: 可运行配置

    Returns:
        包含状态更新的字典，包括sources_gathered、research_loop_count和web_search_results
    """
    logger.info(f"开始网页检索（双引擎）......")
    # 配置
    configurable = Configuration.from_runnable_config(config)
    web_searcher = WebSearchAgent()

    # 执行检索（region 决定走百炼还是 Firecrawl，单引擎失败自动降级）
    response = web_searcher.step(
        prompt=state["search_query"],
        count=configurable.search_results_per_query,
        region=state.get("region"),
    )

    # 检查检索结果是否为空或None
    if not response or response is None:
        logger.error(f"网页检索返回为空: {state['search_query']}")
        return {
            "sources_gathered": [],
            "search_query": [state["search_query"]],
            "web_search_result": [
                f"【本次检索失败】双引擎均未检索到关于 '{state['search_query']}' 的结果。"
                "本节内容只能基于模型既有知识撰写，最终报告必须显著披露本次检索失败，且严禁编造引用链接。"
            ],
            "search_warnings": [
                f"本次检索失败：查询「{state['search_query']}」双引擎均无结果，"
                "报告相应内容来自模型既有知识，未经实时检索验证。"
            ],
        }

    # 区分可验证来源（带 URL）与未验证内容（如百炼解析失败时保留的模型原始正文）
    verified_items, unverified_items = [], []
    for item in response:
        if item.get("unverified") or not item.get("url"):
            unverified_items.append(item)
        else:
            verified_items.append(item)

    # 长URL到短URL的映射（仅对可验证来源建立映射，未验证内容不进入引用集合）
    long2short_url_mappings = resolve_urls(verified_items, state["id"])
    sources_gathered = [{"short_url": long2short_url_mappings[item["url"]], "value": item["url"], "label": item["title"]} for item in verified_items]
    web_search_result = [{"snippet": item["snippet"], "title": item["title"], "url": long2short_url_mappings[item["url"]], "engine": item.get("engine", "")} for item in verified_items]
    # 未验证内容：保留正文但显式标注，防止下游误当作可引用来源
    for item in unverified_items:
        web_search_result.append({
            "snippet": item.get("snippet", ""),
            "title": item.get("title", ""),
            "url": "",
            "engine": item.get("engine", ""),
            "note": "来源未验证：该条为模型直接生成的正文，未解析出可验证的来源链接，仅供参考，严禁据此编造引用链接",
        })
    web_search_result = json.dumps(web_search_result, ensure_ascii=False, indent=4)

    agent = Agent(model_id=effective_model(state, configurable))
    agent.set_step_prompt(web_searcher_instructions)
    modified_text = agent.step(query=state["search_query"], current_date=get_current_date(), web_search_result=web_search_result)
    modified_text = Post.extract_pattern(modified_text, pattern="text")

    # 未验证内容随摘要流入最终报告，附强制披露标记
    if unverified_items:
        modified_text += (
            "\n\n> ⚠️【检索质量披露】本主题部分检索结果未能解析出可验证的来源链接，"
            "内容为模型直接生成并保留（来源未验证）。最终报告引用时必须显著标注，严禁编造链接。"
        )

    logger.info(f"检索标题: {state['search_query']}")
    logger.debug(f"网页检索结果: {modified_text}")

    search_warnings = []
    if unverified_items:
        search_warnings.append(
            f"来源未验证：查询「{state['search_query']}」的检索结果未能解析出可验证链接，"
            "已保留模型原始正文并在文中标注（来源未验证）。"
        )
    return {
        "sources_gathered": sources_gathered,
        "search_query": [state["search_query"]],
        "web_search_result": [modified_text],
        "search_warnings": search_warnings,
    }


def critique(state: OverallState, config: RunnableConfig) -> ReflectionState:
    """
    识别医药调研知识差距并生成潜在后续查询的节点

    分析当前摘要以识别需要进一步调研的维度（临床数据、竞争格局、政策支付等），
    并生成带 region 标注的后续检索查询。
    """
    logger.info(f"反思分析识别知识差距并生成潜在后续查询的节点工作......")
    configurable = Configuration.from_runnable_config(config)
    # 增加研究循环计数并获取推理模型（优先任务级 reasoning_model，与全图一致）
    state["research_loop_count"] = state.get("research_loop_count", 0) + 1
    reasoning_model = state.get("reasoning_model") or configurable.reflection_model
    logger.info(f"critique反思节点模型：{reasoning_model}")

    # 格式化提示
    agent = JsonAgent(model_id=reasoning_model, keys=Reflection)
    agent.set_step_prompt(reflection_instructions)
    result = agent.step(
        current_date=get_current_date(),
        number_queries=state["initial_search_query_count"],
        research_topic=get_research_topic(state["messages"]),
        summaries="\n\n---\n\n".join(state["web_search_result"]),
        research_proposal=state.get("plan", "")
    )

    logger.info(f"反思分析：{result}")
    return {
        "is_sufficient": result.is_sufficient,
        "knowledge_gap": result.knowledge_gap,
        "follow_up_queries": result.follow_up_queries,
        "research_loop_count": state["research_loop_count"],
        "number_of_ran_queries": len(state["search_query"]),
        "max_research_loops": state.get("max_research_loops", configurable.max_research_loops),
    }


def route_evaluate(
    state: ReflectionState,
    config: RunnableConfig,
) -> OverallState:
    """
    确定research中下一步的路由函数

    信息充足或达到最大循环数则进入报告撰写；否则携带 region 标注继续补搜。
    达到循环上限时，信息缺口将在报告中显式标注"暂无公开数据"。
    """
    logger.info("准备评估当前研究......")
    configurable = Configuration.from_runnable_config(config)
    max_research_loops = (
        state.get("max_research_loops")
        if state.get("max_research_loops") is not None
        else configurable.max_research_loops
    )

    logger.info(state)
    logger.info(f"最大研究循环数: {max_research_loops}")
    logger.info(f"当前已研究次数: {state['research_loop_count']}")
    if state["is_sufficient"] or state["research_loop_count"] >= max_research_loops:
        return FINAL_ANSWER_NODE
    else:
        return [
            Send(
                WEB_SEARCH_NODE,
                {
                    "search_query": item["query"] if isinstance(item, dict) else item,
                    "region": item.get("region") if isinstance(item, dict) else None,
                    "reasoning_model": state.get("reasoning_model"),
                    "id": state["number_of_ran_queries"] + int(idx),
                },
            )
            for idx, item in enumerate(state["follow_up_queries"])
        ]


def final_answer(state: OverallState, config: RunnableConfig):
    """
    最终确定调研报告的节点

    生成带引用（含登记号/来源/日期）和合规页脚声明的医药投研报告，
    并将短URL还原为原始URL。
    """
    logger.info("最终调研报告准备生成........")
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.answer_model
    logger.info(f"final_answer最终报告节点模型：{reasoning_model}")

    # 格式化提示
    agent = Agent(model_id=reasoning_model)
    agent.set_step_prompt(answer_instructions)
    content = agent.step(
        current_date=get_current_date(),
        research_topic=get_research_topic(state["messages"]),
        summaries="\n---\n\n".join(state["web_search_result"]),
        research_proposal=state.get("plan", "")
    )

    # 用原始URL替换短URL，并将所有使用的URL添加到sources_gathered
    unique_sources = []
    for source in state["sources_gathered"]:
        if source["short_url"] in content:
            content= content.replace(
                source["short_url"], source["value"]
            )
            unique_sources.append(source)

    # 引用校验：检测模型自造的伪造链接（不在检索来源集合中的 URL，
    # 含未被还原的 search.com/id 短链），重写为告警文本而不是放行
    content, removed_links = sanitize_report_urls(content, state["sources_gathered"])
    if removed_links:
        logger.warning(f"final_answer 引用校验：移除 {len(removed_links)} 个模型自造链接")

    # 检索与引用质量披露：检索失败 / 来源未验证 / 被移除的伪造链接，显式写入报告
    disclosures = []
    for warning in state.get("search_warnings", []) or []:
        disclosures.append(warning)
    if removed_links:
        disclosures.append(
            f"引用校验：报告初稿中有 {len(removed_links)} 个链接无法与本次检索来源对应"
            "（疑似模型自造），已自动移除并在正文原位标注。"
        )
    if disclosures:
        content += (
            "\n\n---\n\n## ⚠️ 检索与引用质量披露\n\n"
            + "\n".join(f"- {d}" for d in disclosures)
            + "\n"
        )

    logger.info(f"最终确定报告：{content}")
    return {
        "messages": [AIMessage(content=content)],
        "sources_gathered": unique_sources,
    }


# 创建我们的Agent图
builder = StateGraph(OverallState, config_schema=Configuration)



# 定义图中的节点
builder.add_node(GENERATE_PLAN_NODE, generate_plan)
builder.add_node(GENERATE_SEARCH_NODE, generate_query)
builder.add_node(WEB_SEARCH_NODE, web_search)
builder.add_node(CRITIQUE_NODE, critique)
builder.add_node(FINAL_ANSWER_NODE, final_answer)
builder.add_node("awaiting_plan_confirmation", lambda state, config: state)
builder.add_node("replan", lambda state, config: {"plan_status": "unconfirmed"})

# 将入口点设置为`GENERATE_PLAN_NODE`
# 这意味着这个节点是第一个被调用的
builder.add_edge(START, GENERATE_PLAN_NODE)
builder.add_conditional_edges(
    GENERATE_PLAN_NODE, evaluate_plan, [GENERATE_SEARCH_NODE, "replan", "awaiting_plan_confirmation"]
)
builder.add_edge("replan", GENERATE_PLAN_NODE)
# 添加条件边以在并行分支中继续检索查询
builder.add_conditional_edges(
    GENERATE_SEARCH_NODE, send_to_web_search, [WEB_SEARCH_NODE]
)
# 对进度进行评估
builder.add_edge(WEB_SEARCH_NODE, CRITIQUE_NODE)
# 评估后决定下一步如何做
builder.add_conditional_edges(
    CRITIQUE_NODE, route_evaluate, [WEB_SEARCH_NODE, FINAL_ANSWER_NODE]
)
# 最终确定报告
builder.add_edge(FINAL_ANSWER_NODE, END)

# 编译图
graph = builder.compile(name="med-research-agent")

# 可选：导出流程图（仅在交互环境中启用，生产部署不影响）
try:
    from IPython.display import Image, display
    display(Image(graph.get_graph().draw_mermaid_png(output_file_path='./医药投资版.png')))
except Exception:
    pass
