# 医药投资深度研究工具（MedResearch DeepResearch）

面向医药投资机构研究团队的 AI 深度调研工具：围绕一个调研主题（赛道 / 公司 / 靶点 / 适应症），自动完成"生成调研计划 → 人工确认 → 双引擎并行检索 → 反思补搜 → 撰写报告 → 带引用交付"的完整流程。

> 产品定义见《卷首/00-产品全貌-医药投资版.md》与《PRD与需求文档/产品需求文档PRD-详细版-医药投资版.md》；技术设计见《架构设计/系统架构与部署视图-医药投资版.md》。

## 三条硬边界（写进系统的，不只是文档）

1. **不构成投资建议**——报告页脚固定输出合规声明（见 `prompts.py` 的 `answer_instructions`）；
2. **只用公开信息**——检索层仅接入公开网页来源（见 `web_search.py`），不接入任何未公开信息（MNPI）；
3. **只做医药投研调研**——不提供医学诊断或用药建议。

## 双引擎检索架构（本项目核心改造）

| 信源方向 | 引擎 | 典型信源 |
|----------|------|----------|
| 国内/中文 | 阿里百炼平台检索 API（DashScope `enable_search`） | 药监局/医保局公告、CDE、中文医药媒体、公司中文公告 |
| 国外/英文 | Firecrawl Search API | ClinicalTrials.gov、FDA、PubMed、SEC/公司财报、海外医药媒体 |

- 路由：LLM 在生成检索查询时为每条查询标注 `region`（domestic/international）；缺省时按语言与国内关键词自动判别；
- 降级：主引擎失败自动切换到另一引擎，单引擎故障不阻断流水线；
- 限流：两引擎各自独立 QPS 限制器，429 指数退避重试；
- 留痕：每条结果携带 `engine` 与 `captured_at` 抓取时间元数据。

代码落点：`backend/src/agent/web_search.py`（引擎与路由）、`backend/src/agent/base_agent.py` 的 `WebSearchAgent`（图内调用入口）。

## 项目结构

- `backend/`：LangGraph Agent 后端（计划生成 → 人工确认 → 并行检索 → 反思补搜 → 报告撰写）
- `frontend/`：React + Vite + Tailwind 前端（欢迎页 / 调研对话页 / 活动时间线）

## Quick Start

**1. 前期准备**

- Node.js 18+、Python 3.11+
- API Key：
  - 阿里百炼：[bailian.console.aliyun.com](https://bailian.console.aliyun.com/)（LLM + 国内检索共用）
  - Firecrawl：[firecrawl.dev](https://www.firecrawl.dev)（海外检索）

**2. 配置环境变量**

```bash
cd backend
cp .env.example .env   # 填入 APP_TOKEN、FIRECRAWL_API_KEY 等
```

**3. 安装依赖并启动后端**

```bash
cd backend
pip install .
langgraph dev   # 默认 http://localhost:2024
```

**4. 启动前端**

```bash
cd frontend
npm install
npm run dev     # 默认 http://localhost:5173，/api 已代理到 2024
```

**5. 参考调研问题**

```text
梳理 GLP-1 赛道全球在研管线的竞争格局，重点关注临床阶段、给药方式差异与专利风险
```

```text
某公司核心品种专利悬崖与仿制药竞争分析，覆盖国内集采影响
```

```text
近一年 ADC 领域 license-in/out 交易盘点，标注交易金额与双方
```

## 与人类参与版（上游）的主要差异

| 项 | 人类参与版 | 医药投资版 |
|----|-----------|-----------|
| 检索 | 单一 MCP 搜索应用 | 双引擎：百炼（国内）+ Firecrawl（国外），region 路由 + 降级 |
| 提示词 | 通用情报分析模板 | 医药投研五大要素（对象/维度/风险/信源/格式），硬数据保真，合规页脚 |
| 查询生成 | 纯字符串列表 | 带 `region` 信源路由标注的结构化查询 |
| main.py | 硬编码 API Key | 密钥全部走 `.env`（安全修复） |
| 前端文案 | 通用欢迎页 | PRD 6.2 医药版文案与占位符 |
