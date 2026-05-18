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