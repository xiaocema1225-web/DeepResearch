import copy
import traceback
import json
from loguru import logger
from agent.llm.llm import OpenAICompatibleLLM
from agent.post import Post


class Agent:
    step_prompt = """{prompt}"""
    def __init__(self, model_id="qwen2.5-72b-instruct"):
        self.llm = OpenAICompatibleLLM(model_id=model_id)

    def __call__(self, prompt):
        response = self.llm.generate_response(prompt)
        return response

    def set_step_prompt(self, prompt):
        self.step_prompt = prompt

    def step(self, **kwargs):
        step_prompt = self.prompt_format(self.step_prompt, **kwargs)
        response = ""
        for _ in range(3):
            try:
                response = self(step_prompt)
                response = self.post_process(response)
                break
            except Exception as e:
                logger.error(f"大模型调用错误：{e}\n{traceback.format_exc()}")
                continue
        return response

    def post_process(self, response):
        return response

    def prompt_format(self, prompt, **kwargs):
        prompt_ = copy.deepcopy(prompt)
        for k in kwargs.keys():
            rep = "{"+k+"}"
            prompt_ = prompt_.replace(rep, str(kwargs[k]))
        return prompt_


class JsonAgent(Agent):
    def __init__(self, model_id="qwen2.5-72b-instruct", keys=None):
        super().__init__(model_id)
        self.keys = keys

    def post_process(self, response):
        result = json.loads(Post.extract_pattern(response, pattern="json"))
        if not self.keys:
            return result
        return self.keys(**result)


class WebSearchAgent(Agent):
    """
    网页检索 Agent（医药投资版双引擎实现）。

    与通用版的区别：不再走单一 MCP 搜索应用，而是调用 agent.web_search 模块的
    hybrid_search()——国内/中文信源走阿里百炼平台检索 API，国外/英文信源走
    Firecrawl Search API，主引擎失败自动降级到另一引擎（对应架构文档 2.4 与 ADR-4）。

    入参 region（可选）："domestic" / "international"，由查询生成阶段 LLM 标注；
    缺省时按查询语言与国内关键词自动判别。
    """

    def step(self, prompt, count=10, region=None, **kwargs):
        from agent.web_search import hybrid_search

        try:
            results = hybrid_search(prompt, count=count, region=region)
        except Exception as e:
            logger.error(f"双引擎检索异常：{e}\n{traceback.format_exc()}")
            return None

        if not results:
            logger.warning(f"检索无结果（双引擎均已尝试）: {prompt}")
            return None

        # 统一转为 dict 列表（保留 engine/captured_at 等来源元数据，供引用与留痕）
        return [r.to_dict() for r in results]


if __name__ == '__main__':
    agent = WebSearchAgent()
    response = agent.step(prompt="GLP-1 减肥药 国内获批进展", count=10)
    logger.info(response)
    response = agent.step(prompt="semaglutide cardiovascular outcomes trial FDA", count=10)
    logger.info(response)
