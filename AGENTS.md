# AGENTS.md – Agent Workflow Plugin Service

> **版本**：v1.0  
> **最后更新**：2026-05-17  
> **状态**：可执行规范

---

## 一、项目定位

**Agent Workflow Plugin Service** 是一个**可热插拔的插件服务框架**，为 `feishu-rpa-commerce-agent`（主项目）提供多种业务能力插件。

- 它不是主项目的子目录，而是一个**平行目录**（例如 `/home/zed/agent-workflow-plugin-service`）
- 它不直接接收飞书消息，也不处理飞书长连接
- 它通过 **REST API** 对外提供服务，主项目通过 HTTP 调用它
- **插件化设计**：每个业务能力（邮件、选品、广告等）都是一个独立插件，放在 `plugins/` 目录下
- **当前第一个插件**：邮件分析插件（`plugins/email/`）

**核心能力框架**：
1. 统一插件加载与路由
2. 每个插件独立实现自己的业务逻辑
3. 提供标准 API：`POST /api/v1/{plugin_name}/tasks`（触发任务）和 `GET /api/v1/tasks/{task_id}`（查询结果）
4. 插件之间互不依赖，可独立开发、测试、部署

---

## 二、项目边界

### 2.1 本服务负责的事情

| 层级 | 职责 |
|------|------|
| 框架层（core） | 配置管理、日志、数据库连接（SQLite）、任务状态存储、插件发现与路由 |
| 插件层（plugins） | 每个插件实现自己的业务逻辑（如邮件读取、Dify 调用、汇总报告） |
| API 层 | 统一入口：`/api/v1/{plugin_name}/tasks`（启动任务）、`/api/v1/tasks/{task_id}`（查询任务） |

### 2.2 本服务不负责的事情

- ❌ 不直接发送飞书消息（由主项目负责）
- ❌ 不处理用户认证与权限（由主项目负责）
- ❌ 不提供 Web UI
- ❌ 不负责定时调度（由主项目或外部 cron 触发）

### 2.3 与主项目的依赖关系

- 主项目通过 `docker-compose` 集成本服务，服务名固定为 `plugin-service`
- 主项目调用本服务的 API：`POST /api/v1/email/tasks`（触发邮件分析）等
- 主项目负责将最终报告推送到飞书

---

## 三、技术栈（当前版本）

| 组件 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.11+ |  |
| Web 框架 | FastAPI | 轻量、高性能 |
| 数据库 | SQLite | 存储任务状态（后续可扩展） |
| 配置管理 | `python-dotenv` | 环境变量 |
| 进程管理 | Uvicorn | ASGI 服务器 |

**明确禁止引入**（当前版本）：
- Redis / Celery / Postgres / MinIO
- 消息队列
- 复杂插件系统（用简单的字典映射即可）

---

## 四、目录结构（强制）

```text
agent-workflow-plugin-service/
├── Dockerfile
├── requirements.txt
├── .env.example
├── README.md
├── data/                     # 挂载卷，存放 SQLite 数据库
│   └── tasks.db
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI 入口
│   ├── config.py             # 配置加载
│   ├── logger.py             # 日志
│   ├── database.py           # SQLite 连接与任务表
│   ├── models.py             # Pydantic 模型（TaskStatus 等）
│   ├── task_manager.py       # 任务状态管理（内存 + 持久化）
│   └── plugins/
│       ├── __init__.py
│       ├── base.py           # 插件基类（定义 execute 方法）
│       ├── registry.py       # 插件注册与路由
│       └── email/            # 邮件分析插件
│           ├── __init__.py
│           ├── plugin.py     # 插件主类（继承 base）
│           ├── email_fetcher.py
│           ├── dify_client.py
│           ├── repository.py
│           └── reporter.py
├── scripts/
│   ├── init_db.py
│   └── test_email_plugin.py
└── tests/
文件职责清单：

文件	职责
app/main.py	FastAPI 应用，注册路由
app/config.py	从环境变量读取配置
app/database.py	SQLite 初始化、任务表 CRUD
app/task_manager.py	创建任务、更新状态、查询结果
app/plugins/base.py	定义 Plugin 抽象基类（execute(task_id, **params) -> result）
app/plugins/registry.py	插件注册表（PLUGINS = {"email": EmailPlugin}）和路由辅助
app/plugins/email/plugin.py	邮件插件的具体实现
app/plugins/email/email_fetcher.py	邮箱读取
app/plugins/email/dify_client.py	Dify 调用
app/plugins/email/repository.py	邮件去重存储（独立于任务表）
app/plugins/email/reporter.py	汇总报告生成
五、API 设计规范
所有接口前缀 /api/v1/。服务监听 0.0.0.0:8000。

5.1 启动插件任务
URL：POST /api/v1/{plugin_name}/tasks

请求体：插件自定义（例如邮件插件可传 chat_id）

json
{
  "chat_id": "oc_xxxxx"
}
响应：

json
{
  "task_id": "uuid",
  "status": "pending",
  "created_at": "2026-05-17T10:00:00"
}
5.2 查询任务结果
URL：GET /api/v1/tasks/{task_id}

响应：

json
{
  "task_id": "uuid",
  "status": "completed",
  "created_at": "...",
  "completed_at": "...",
  "result": { ... },   // 插件返回的具体结果
  "error": null
}
5.3 健康检查
URL：GET /health

响应：{"status": "ok"}

六、插件开发规范
6.1 插件基类（base.py）
python
from abc import ABC, abstractmethod

class Plugin(ABC):
    name: str  # 插件唯一标识

    @abstractmethod
    def execute(self, task_id: str, **params) -> dict:
        """
        执行插件任务。
        :param task_id: 任务ID，可用于记录日志
        :param params: 从 API 请求体传入的参数
        :return: 执行结果（将被存入任务记录的 result 字段）
        """
        pass
6.2 插件注册（registry.py）
python
from .email.plugin import EmailPlugin

PLUGINS = {
    "email": EmailPlugin(),
    # 后续扩展： "product": ProductPlugin(),
}
6.3 邮件插件实现（email/plugin.py）
继承 Plugin

实现 execute 方法：

读取 MAILBOXES 环境变量
遍历邮箱，调用 EmailFetcher
调用 DifyClient 分析
使用 EmailRepository 去重存储
调用 Reporter 生成报告
返回 {"batch_id": "...", "report": "...", "total_processed": N}
七、数据库设计（SQLite）
7.1 任务表 tasks
字段	类型	说明
task_id	TEXT PRIMARY KEY	UUID
plugin_name	TEXT	插件名称（email, product, ...）
status	TEXT	pending / running / completed / failed
params	TEXT	JSON 格式的请求参数
result	TEXT	JSON 格式的结果
error	TEXT	错误信息
created_at	DATETIME	创建时间
completed_at	DATETIME	完成时间
7.2 邮件插件独立表 email_processed
（与之前设计相同，用于去重）

八、开发阶段规划（MVP 优先）
第一阶段：框架骨架 + 邮件插件核心（当前轮）
实现上述目录结构

实现 FastAPI 基础服务、健康检查

实现插件注册与路由（只注册 email 插件）

实现邮件插件的核心逻辑：

邮箱读取（IMAP）

Dify 调用（可 mock）

不要求去重存储、不要求汇总报告（简化）

提供测试脚本验证单个邮箱读取 + Dify 分析

第二阶段：任务管理与存储
实现 SQLite 任务表

实现任务管理器（创建任务、更新状态、后台执行）

实现 POST /api/v1/email/tasks 和 GET /api/v1/tasks/{task_id}

第三阶段：邮件插件完善
实现去重存储（email_processed 表）

实现汇总报告生成

多邮箱支持

后续阶段：扩展其他插件
九、第一轮开发范围（严格限定）
本轮只做：

项目骨架（目录结构、requirements.txt、Dockerfile、.env.example）

FastAPI 基础服务（main.py, config.py, logger.py, health 接口）

插件框架最小化：

plugins/base.py（抽象基类）

plugins/registry.py（硬编码注册 email 插件）

plugins/email/plugin.py（骨架，execute 先返回 mock 结果）

邮件插件的核心能力（不依赖数据库）：

email_fetcher.py（IMAP 读取，返回邮件列表）

dify_client.py（调用 Dify 或 mock）

在 plugin.py 的 execute 中调用它们，并打印结果

测试脚本 scripts/test_email_plugin.py（直接实例化 EmailPlugin 并调用 execute）

本轮不做：

SQLite 数据库（任务表、邮件去重表）

任务管理 API（/api/v1/email/tasks 等）

汇总报告生成

多邮箱循环（只支持单个邮箱）

任何形式的持久化


# AGENTS.md – 选品插件开发约束（最小闭环版）

## 一、项目目标

在当前 `Agent Workflow Plugin Service` 中新增一个 **选品分析插件（Product Plugin）**，实现最小可演示闭环：

1. 用户在飞书群中 @机器人 发送 `选品分析 <关键词>`
2. 机器人立即回复“正在分析中...”
3. 系统后台调用 Dify 工作流（模拟分析，不依赖真实数据源）
4. Dify 返回结构化 JSON 和纯文本总结
5. 机器人将纯文本总结发送到群聊

**核心原则**：只做最小闭环，不扩展任何非必需功能。

## 二、强制边界（禁止事项）

- ❌ 不接入任何真实数据源（亚马逊 API、爬虫、第三方付费服务）
- ❌ 不新建数据库表（不存储选品历史、关键词、报告）
- ❌ 不实现指标统计、趋势分析、报警、导出、审计等功能
- ❌ 不支持批量分析、多关键词对比、历史记录查询
- ❌ 不实现复杂规则引擎或打分模型（仅用 Dify 生成模拟值）
- ❌ 不修改已有邮件插件的任何代码
- ❌ 不新增 Python 依赖（复用现有依赖）

## 三、允许的功能

- ✅ 新增 `app/plugins/product/` 目录及 `plugin.py`
- ✅ 在 `registry.py` 中注册 `ProductPlugin`
- ✅ 在 `feishu_commands.py` 中增加对 `选品分析 <关键词>` 的识别
- ✅ 复用 `DifyClient` 调用 Dify 工作流
- ✅ 复用 `FeishuAppClient` 发送报告
- ✅ 复用 `task_manager` 创建和管理任务
- ✅ 复用现有 `scripts/test_*.py` 测试框架

## 四、最小闭环验收标准（全部满足即停止）

- [ ] 飞书群中发送 `@机器人 选品分析 无线耳机` 后，机器人回复“正在分析中...”
- [ ] 服务日志显示任务创建成功，插件执行完成
- [ ] Dify 工作流被调用，输入为关键词，输出包含 JSON（`score`, `summary`, `suggestion`）和纯文本总结
- [ ] 飞书群中收到最终报告（纯文本，不包含 JSON）
- [ ] 整个流程在 15 秒内完成
- [ ] 没有出现任何错误日志（预期内的 Dify 超时除外）

## 五、开发过程规则

1. **逐项汇报**：每完成一个可独立验证的步骤（如插件注册、指令识别、Dify 接入），必须向用户汇报当前状态和下一步计划。
2. **停止信号**：一旦上述六项验收标准全部满足，Agent 必须立即停止开发，输出验收清单，等待用户的下一步指令。
3. **禁止持续“优化”**：不得在闭环达标后继续添加“增强”功能（如缓存、批量、图表等）。
4. **遇到障碍**：如果 Dify 工作流无法创建或 API 调用失败，优先使用 mock 数据完成闭环（但需在报告中说明）。

## 六、Dify 工作流要求

- 工作流名称：`product_analyzer`
- 输入变量：`keyword`（字符串）
- 输出：
  - JSON 格式：`{"score": 0-100, "summary": "...", "suggestion": "..."}`
  - 纯文本：一段自然语言总结（不超过 200 字）
- 提示词可参考：
你是一个选品分析助手。针对用户输入的关键词，模拟生成一份选品建议。
输入关键词：{{keyword}}
输出 JSON 格式（不要输出额外文字）：
{"score": 0-100, "summary": "一句话总结", "suggestion": "具体建议"}
然后在 JSON 后另起一行输出一段适合发飞书的纯文本总结（不含 JSON 内容）。

text

## 七、文件修改清单（仅限以下）

- 新增：`app/plugins/product/__init__.py`
- 新增：`app/plugins/product/plugin.py`
- 修改：`app/plugins/registry.py`（注册 `ProductPlugin`）
- 修改：`app/services/feishu_commands.py`（增加指令分支）
- 修改：`scripts/test_*.py`（可选，用于手动测试）
- 其他文件不得改动

## 八、最终交付

完成验收后，输出以下内容：
1. 变更文件列表及简要说明
2. Dify 工作流的导入 JSON（或手动创建步骤）
3. 手动验收结果截图（描述即可）
4. 一句“已达到最小闭环，等待后续指令”

**违反上述任何一条，即视为过度开发，需要回退。**

# Listing 优化插件开发约束（最小闭环版）

## 一、项目目标

在当前 `Agent Workflow Plugin Service` 中新增 **Listing 优化插件（Listing Optimizer）**，实现最小可演示闭环：

用户通过飞书发送 `Listing 优化 <商品关键词或现有 Listing 文本>` → 机器人立即回复“正在分析 Listing...” → 系统调用 Dify 工作流（模拟专业分析）→ Dify 返回包含**至少 5 个维度**的结构化优化建议（标题、五点、描述、关键词、A+、评分、差异化）→ 机器人将格式清晰的纯文本报告发送到群聊。

**核心原则**：只做最小闭环，所有分析基于 LLM 通用知识，不接入真实数据源。

## 二、强制边界（禁止事项）

- ❌ 不接入任何亚马逊 API、爬虫、第三方付费服务。
- ❌ 不新建数据库表（不存储历史优化记录）。
- ❌ 不实现 A/B 测试、排名追踪、价格监控、广告分析等扩展功能。
- ❌ 不依赖真实销售数据或关键词工具。
- ❌ 不修改邮件插件、选品插件等已有代码（除必要的注册和指令扩展外）。
- ❌ 不新增 Python 依赖。

## 三、允许的功能

- ✅ 新增 `app/plugins/listing/` 目录及 `plugin.py`。
- ✅ 在 `registry.py` 中注册 `ListingOptimizerPlugin`。
- ✅ 在 `feishu_commands.py` 中增加对 `^Listing 优化\s+(.+)$` 指令的识别。
- ✅ 复用 `DifyClient` 调用 Dify 工作流。
- ✅ 复用 `FeishuAppClient` 发送报告。
- ✅ 复用 `task_manager` 创建和管理任务。
- ✅ 使用独立的环境变量：`LISTING_DIFY_API_URL`、`LISTING_DIFY_API_KEY`（无全局回退）。
- ✅ 在 Dify 中创建工作流 `listing_optimizer`，输入变量 `product_input`，输出 JSON + 纯文本。

## 四、最小闭环验收标准（全部满足即停止）

- [ ] 飞书群中发送 `@机器人 Listing 优化 无线耳机` 后，机器人回复“正在分析 Listing...”。
- [ ] 服务日志显示任务创建成功，插件执行完成。
- [ ] Dify 工作流被调用，输入为提取的文本，输出 JSON 至少包含以下 5 个字段：
  - `title_optimized`
  - `bullet_points`（数组，至少 3 个）
  - `backend_keywords`（数组，至少 5 个）
  - `score`（0-100 整数）
  - `differentiation`（字符串）
- [ ] 飞书群中收到纯文本报告（非 JSON 格式），内容分段清晰，包含标题、卖点、关键词、评分、差异化建议等信息。
- [ ] 整个流程在 20 秒内完成。
- [ ] 没有出现与本次任务无关的错误日志（预期内的 Dify 超时或回退 mock 除外）。

## 五、开发过程规则

1. **逐项汇报**：每完成一个可独立验证的步骤（插件骨架、指令识别、Dify 接入），向用户汇报当前状态和下一步计划。
2. **停止信号**：一旦上述六项验收标准全部满足，Agent 必须立即停止开发，输出验收清单，等待用户的下一步指令。
3. **禁止持续优化**：不得在闭环达标后继续添加“增强”功能（如缓存、批量、历史记录等）。
4. **遇到障碍**：如果 Dify 工作流无法创建或 API 调用失败，优先使用 mock 数据完成闭环（但需在报告中说明）。

## 六、Dify 工作流要求

- **工作流名称**：`listing_optimizer`
- **输入变量**：`product_input`（字符串）
- **LLM 提示词**（必须包含，可复制到 Dify 节点）：
你是一位资深亚马逊Listing优化专家。请针对用户提供的商品信息，生成一份专业的优化报告。

用户输入：{{product_input}}

请严格按照以下JSON格式输出，不要额外解释，不要markdown代码块，只输出JSON对象：
{
"title_optimized": "优化后的标题示例（最多200字符）",
"bullet_points": ["卖点1", "卖点2", "卖点3", "卖点4", "卖点5"],
"description_structured": "建议的产品描述结构（150字内）",
"backend_keywords": ["keyword1", "keyword2", ..., "keyword15"],
"aplus_suggestions": "A+页面建议（80字内）",
"score": 85,
"score_reasons": "信息完整度80/100、关键词质量90/100、可读性85/100",
"differentiation": "建议强调的核心差异化卖点"
}

JSON 输出后，另起一行输出一段适合飞书群发的纯文本总结（不超过500字），格式可以分段、使用emoji，内容需覆盖主要优化建议。

text
- **发布后获取 API Key**，格式 `app-xxx`。

## 七、文件修改清单（仅限以下）

- 新增：`app/plugins/listing/__init__.py`
- 新增：`app/plugins/listing/plugin.py`
- 修改：`app/plugins/registry.py`（注册 `ListingOptimizerPlugin`）
- 修改：`app/services/feishu_commands.py`（增加指令分支）
- 修改：`app/config.py`（增加 `listing_dify_api_url` 和 `listing_dify_api_key` 字段）
- 修改：`.env.example`（增加 `LISTING_DIFY_API_URL`、`LISTING_DIFY_API_KEY`）
- 可选：新增测试脚本 `scripts/test_listing_plugin.py`

**其他文件不得改动。**

## 八、最终交付

完成验收后，输出以下内容：
1. 变更文件列表及简要说明。
2. Dify 工作流的导入 JSON 或手动创建步骤。
3. 手动验收结果截图（或文字描述）。
4. 一句“已达到最小闭环，等待后续指令”。

**违反上述任何一条，即视为过度开发，需要回退。**


## 开发要求必读此项，此轮开发的全部要求
# AGENTS.md – 广告监控插件（最小闭环版）

## 一、项目目标

在当前 `Agent Workflow Plugin Service` 中新增一个 **广告数据监控与优化建议插件（Ad Optimizer Plugin）**，实现最小可演示闭环：

1. 用户在飞书群中 @机器人 发送 `广告报告` 或 `广告优化`
2. 机器人立即回复“正在获取广告数据...”
3. 系统后台生成模拟广告数据（近7天整体指标 + 3-5个关键词表现）
4. 通过简单规则引擎分析数据，生成优化建议（如降低/提高出价、暂停关键词、添加否定词）
5. 机器人将汇总报告和优化建议发送到群聊

**核心原则**：不调用 Dify、不调用真实 SP-API、不存储数据、仅使用 Python 模拟。

## 二、强制边界（禁止事项）

- ❌ 不调用任何外部 API（包括 Dify、亚马逊 SP-API）
- ❌ 不使用数据库（不新建表、不存储广告数据）
- ❌ 不支持多广告活动选择（固定演示一个广告活动）
- ❌ 不实现复杂预测算法或机器学习
- ❌ 不修改已有邮件、选品插件的代码
- ❌ 不新增 Python 依赖（复用现有）

## 三、允许的功能

- ✅ 新增 `app/plugins/ad/plugin.py` 及 `__init__.py`
- ✅ 在 `registry.py` 中注册 `AdOptimizerPlugin`
- ✅ 在 `feishu_commands.py` 中增加 `广告报告`/`广告优化` 指令
- ✅ 使用 `task_manager` 创建和运行任务
- ✅ 模拟生成广告数据（整体指标 + 关键词明细）
- ✅ 基于规则（如 ACOS > 30% 建议降价，CTR < 1% 建议优化创意）
- ✅ 格式化飞书消息（文本，含表格或列表）

## 四、最小闭环验收标准（全部满足即停止）

- [ ] 飞书群中发送 `@机器人 广告报告` 后，机器人回复“正在获取广告数据...”
- [ ] 服务日志显示任务创建成功，插件执行完成
- [ ] 10秒内收到飞书消息，包含：
  - 整体指标：展示次数、点击次数、花费、销售额、ACOS、ROAS
  - 至少3个关键词的优化建议（每个建议含关键词、当前指标、具体操作）
- [ ] 消息中没有报错，没有模拟数据标记（内容自然）
- [ ] 整个过程不产生任何数据库写入（除任务表外）

## 五、开发过程规则

1. **逐项汇报**：每完成一个独立步骤（插件注册、指令添加、规则逻辑）必须向用户汇报。
2. **停止信号**：一旦验收标准全部满足，立即停止开发，输出验收清单。
3. **禁止“优化”**：不得添加缓存、历史记录、批量处理等额外功能。
4. **模拟数据需合理**：生成的数据应在商业常识范围内（例如 ACOS 在 10%-50% 之间）。

## 六、飞书报告格式建议

整体指标：
- 曝光：12,500
- 点击：380 (CTR 3.04%)
- 花费：$342.50
- 销售额：$1250.00
- ACOS：27.4%
- ROAS：3.65

关键词优化建议：
- “wireless earbuds”：ACOS 22% → ✅ 表现好，可提高出价 10%
- “bluetooth earphones”：ACOS 35% → ⚠️ 高于阈值，建议降低出价 15%
- “free shipping”：无转化 → ❌ 添加为否定关键词

## 七、文件修改清单（仅限以下）

- 新增：`app/plugins/ad/__init__.py`
- 新增：`app/plugins/ad/plugin.py`
- 修改：`app/plugins/registry.py`
- 修改：`app/services/feishu_commands.py`
- 其他文件不得改动

## 八、最终交付

完成后输出：
1. 变更文件列表及简要说明
2. 手动验收结果（描述）
3. 一句“已达到最小闭环，等待后续指令”

