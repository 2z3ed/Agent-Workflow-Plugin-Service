# Agent Workflow Plugin Service

一个插件化的 FastAPI 服务框架，首个插件为邮件分析插件。

## 功能范围

- FastAPI 健康检查接口 `GET /health`
- 最小插件框架
- SQLite 任务存储与任务查询
- 邮件插件：读取 IMAP 邮箱未读邮件并调用 Dify 分析
- Dify 未配置时自动返回 mock 结果

## 环境变量

复制 `.env.example` 为 `.env` 后配置：

- `MAILBOXES`：邮箱配置，格式为 `email:password:imap_server`
- `DIFY_API_URL`：Dify 接口地址，可选
- `DIFY_API_KEY`：Dify API Key，可选
- `DATABASE_PATH`：SQLite 数据库路径，默认 `./data/tasks.db`

示例：

```bash
MAILBOXES=user@example.com:app_password:imap.example.com
DIFY_API_URL=https://api.dify.ai/v1/chat-messages
DIFY_API_KEY=your_api_key
DATABASE_PATH=./data/tasks.db
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置环境

```bash
cp .env.example .env
```

然后编辑 `.env`，填写真实邮箱授权码、可选的 Dify 配置和数据库路径。

## 初始化数据库

```bash
python scripts/init_db.py
```

会自动创建 `data/` 目录和 `data/tasks.db`，并初始化 `tasks` 表。

## 启动 FastAPI 服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问：

- `http://localhost:8000/health`

## 触发邮件任务 API

```bash
curl -X POST http://localhost:8000/api/v1/email/tasks \
  -H "Content-Type: application/json" \
  -d '{"chat_id": "test"}'
```

返回示例：

```json
{
  "task_id": "uuid",
  "status": "completed",
  "created_at": "2026-05-17T10:00:00+00:00",
  "completed_at": "2026-05-17T10:00:05+00:00",
  "result": {
    "email_count": 1,
    "sample_analysis": {}
  },
  "error": null
}
```

## 查询任务 API

```bash
curl http://localhost:8000/api/v1/tasks/uuid
```

## 运行邮件插件测试脚本

```bash
python scripts/test_email_plugin.py
```

脚本会：

1. 实例化 `EmailPlugin`
2. 读取最近 1 天内的未读邮件，最多 5 封
3. 调用 Dify 分析第一封邮件
4. 打印结果

如果没有配置 Dify，会自动返回 mock 分析结果。
如果没有配置邮箱，会抛出清晰错误提示。

## 目录说明

- `app/main.py`：FastAPI 入口和任务 API
- `app/config.py`：环境变量读取
- `app/logger.py`：日志配置
- `app/database.py`：SQLite 初始化与任务表 CRUD
- `app/models.py`：Pydantic 模型
- `app/task_manager.py`：同步任务执行与状态更新
- `app/plugins/base.py`：插件基类
- `app/plugins/registry.py`：插件注册表
- `app/plugins/email/`：邮件插件实现
- `scripts/init_db.py`：数据库初始化脚本
- `scripts/test_email_plugin.py`：独立测试脚本

## 说明

当前版本只实现最小闭环：API 触发 -> 同步执行 -> 结果落库 -> 查询任务。
暂不包含数据库以外的复杂持久化、任务队列、汇总报告和多邮箱循环。
# Agent-Workflow-Plugin-Service
