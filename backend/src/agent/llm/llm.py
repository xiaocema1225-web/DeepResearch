from openai import OpenAI
from agent.config import get_config

class OpenAICompatibleLLM:

    def __init__(self, model_id=""):
        self.model_id = model_id

    def generate_response(self, query):
        # 配置读取：.env 文件优先，系统环境变量兜底（见 agent/config.py）
        client = OpenAI(
            api_key=get_config('APP_TOKEN'),
            base_url=get_config("LLM_BASE_URL"),
        )

        response = client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {
                    "role": "user",
                    "content": query
                }
            ],
            extra_body={"enable_thinking": False},
        )
        return response.choices[0].message.content
