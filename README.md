# Agent Workflow Plugin Service

一个插件化的 FastAPI 服务框架，首个插件为邮件分析插件。

## 功能范围

- FastAPI 健康检查接口 `GET /health`
- 最小插件框架
- SQLite 任务存储与任务查询
- 邮件插件：读取 IMAP 邮箱未读邮件并调用 Dify 分析
- 邮件去重存储 `email_processed`
- 多邮箱循环处理
- 汇总报告生成
- 飞书 Webhook 主动推送汇总报告
- 飞书长连接接收消息（企业自建应用）
- 第二个插件示例 `hello`
- 第三个插件示例 `timestamp`
- Dify 未配置时自动返回 mock 结果

## 第二个插件示例

系统内置了一个最小示例插件 `hello`，用于验证框架扩展性。

### 调用方式

```bash
curl -X POST http://localhost:8000/api/v1/hello/tasks \
  -H "Content-Type: application/json" \
  -d '{"name": "Cursor"}'
```

## 第三个插件示例

`timestamp` 插件返回服务器当前 UTC 和本地时间戳。

```bash
curl -X POST http://localhost:8000/api/v1/timestamp/tasks \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 环境变量

复制 `.env.example` 为 `.env` 后配置：

- `MAILBOXES`：邮箱配置，格式为 `email:password:imap_server;email2:password2:imap_server2`
- `DIFY_API_URL`：Dify 工作流接口地址（邮件插件，亦可用 `EMAIL_DIFY_API_URL`）
- `DIFY_API_KEY`：Dify API Key（邮件插件，亦可用 `EMAIL_DIFY_API_KEY`）
- `EMAIL_DIFY_API_URL` / `EMAIL_DIFY_API_KEY`：邮件分析工作流（推荐显式配置）
- `PRODUCT_DIFY_API_URL` / `PRODUCT_DIFY_API_KEY`：选品分析工作流 `product_analyzer`
- `LISTING_DIFY_API_URL` / `LISTING_DIFY_API_KEY`：Listing 优化工作流 `listing_optimizer`（可复用同一 Dify 实例，使用独立 API Key）
- `DATABASE_PATH`：SQLite 数据库路径，默认 `./data/tasks.db`
- `MAX_EMAILS_PER_BOX`：每个邮箱最多读取邮件数，默认 `20`
- `LOOKBACK_DAYS`：回溯天数，默认 `1`
- `ONLY_UNREAD`：是否只读未读邮件，默认 `true`
- `SEND_FEISHU`：是否发送飞书通知，默认 `true`
- `FEISHU_WEBHOOK_URL`：飞书自定义机器人 Webhook，可选
- `FEISHU_SECRET`：飞书机器人签名密钥，可选
- `FEISHU_APP_ID`：飞书企业自建应用 App ID，用于长连接接收事件
- `FEISHU_APP_SECRET`：飞书企业自建应用 App Secret
- `FEISHU_ENABLE_LONG_CONN`：是否启动飞书长连接，默认 `true`
- `FEISHU_ENABLE_OAPI_LONG_CONN`：兼容开关，建议保持 `true`
- `FEISHU_CHAT_ID`：可选，用于标识飞书群或调试信息
- `ALERT_FREQUENCY_LIMIT_MINUTES`：报警飞书推送频率限制，默认 `10`，设为 `0` 表示不限制

## 插件市场与插件列表

- `GET /api/v1/plugins`：返回基础插件列表，不含文档
- `GET /api/v1/plugins/market`：返回插件市场视图，含分类、文档、搜索、排序、分页
- `GET /api/v1/plugins/metrics`：返回各插件的历史运行指标，可按时间范围过滤
- `GET /api/v1/plugins/metrics?bucket=day|month`：返回按时间分组的趋势数据
- `GET /api/v1/plugins/metrics?bucket=day|month&compare_plugins=email,hello`：返回多插件对比趋势数据
- `GET /api/v1/plugins/metrics?bucket=day|month&normalize=true`：返回归一化后的趋势数据
- `GET /api/v1/plugins/metrics?...&export_format=csv`：导出趋势 CSV
- `GET /api/v1/plugins/metrics?...&send_feishu=true`：当触发报警时推送飞书
- `GET /api/v1/plugins/metrics?...&alert_message_template=...`：自定义飞书报警消息模板
- `GET /api/v1/plugins/alerts/history`：查询报警历史记录
- `GET /api/v1/plugins/alerts/history/stats`：查看报警历史统计聚合
- `DELETE /api/v1/plugins/alerts/history`：清理报警历史记录

### 市场接口常用参数

- `q`：按 `name`、`description`、`docs` 模糊搜索，大小写不敏感
- `category`：按分类过滤，如 `business`、`example`、`utility`
- `sort`：按 `name` 或 `category` 排序
- `page`、`page_size`：分页参数

### 指标接口说明

指标接口基于 `tasks` 表聚合统计每个插件的历史任务数据，包括：

- `plugin_name`
- `total_tasks`
- `completed_tasks`
- `failed_tasks`
- `last_execution_at`
- `avg_execution_seconds`
- `success_rate`
- `status_breakdown`

`avg_execution_seconds` 表示平均执行时长，单位为秒，只统计 `completed` 任务，使用 `completed_at - created_at` 计算。
如果没有已完成任务，该字段返回 `null`。

`success_rate` 表示执行成功率，计算方式为 `completed_tasks / total_tasks`。
如果没有任务数据，该字段返回 `null`。通常可理解为：

- 大于 `0.9`：状态较健康
- 低于 `0.5`：需要关注

`status_breakdown` 是按状态的分组统计对象，包含：

- `completed`
- `failed`
- `running`
- `pending`

### 飞书长连接配置

1. 在飞书开放平台创建企业自建应用，开启机器人能力。
2. 订阅事件 `im.message.receive_v1`。
3. 选择“使用长连接接收事件”。
4. 获取并配置：
   - `FEISHU_APP_ID`
   - `FEISHU_APP_SECRET`
5. 启动服务后，程序会在初始化阶段启动长连接线程。
6. 在飞书群内 @机器人 或私聊机器人，控制台应输出收到的消息内容。

建议先用测试脚本观察日志输出：

```bash
python scripts/test_feishu_longconn.py
```

### Dify 工作流创建指南

1. 在 Dify 中创建工作流应用。
2. 设置输入变量：`email_text`
3. 设置输出字段：
   - `customer_intent`
   - `has_followup`
   - `next_followup_time`
   - `urgency`
   - `brief_summary`
4. 将工作流 API URL 和 API Key 配置到：
   - `DIFY_API_URL`
   - `DIFY_API_KEY`
5. 使用示例文本调用测试脚本：

```bash
python scripts/test_dify_real.py
```

### 邮箱 IMAP 配置要点

1. 在 163/126 邮箱中开启 IMAP 服务。
2. 使用授权码，不要使用登录密码。
3. 在 `.env` 中配置：

```bash
MAILBOXES=你的邮箱:授权码:imap.163.com
```

4. 确认邮箱中有可读取的测试邮件。
5. 使用测试脚本检查能否读取未读邮件：

```bash
python scripts/test_email_real.py
```

### 验收命令与预期结果

启动服务：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

端到端验收：

```bash
bash scripts/test_e2e.sh
```

预期结果：

- 服务启动后不报错
- 飞书长连接线程启动成功，控制台可看到收到消息的日志
- `scripts/test_dify_real.py` 返回 Dify 工作流 JSON
- `scripts/test_email_real.py` 能打印邮件列表
- 邮件任务接口、统计、报警历史、导出、审计接口均可正常访问

### 趋势接口说明

当传入 `bucket=day` 或 `bucket=month` 时，`/api/v1/plugins/metrics` 会返回趋势数组 `trend`，而不是汇总 `plugins`。

- `bucket=day`：按天分组，`bucket_date` 格式为 `YYYY-MM-DD`
- `bucket=month`：按月分组，`bucket_date` 格式为 `YYYY-MM`

当同时提供 `start_time` 和 `end_time` 时，会自动补齐缺失时间桶，未命中的桶返回零值。

补零规则：

- 仅对已有数据的插件进行补零
- 缺失桶的 `total_tasks`、`completed_tasks`、`failed_tasks` 为 `0`
- `success_rate` 为 `null`
- 结果按时间升序排列

### 多插件对比趋势

通过 `compare_plugins` 可以一次比较多个插件：

```bash
curl "http://localhost:8000/api/v1/plugins/metrics?bucket=day&compare_plugins=email,hello&start_time=2026-05-01T00:00:00&end_time=2026-05-03T23:59:59"
```

返回结构示例：

```json
{
  "trend": [
    {
      "bucket_date": "2026-05-01",
      "plugins": {
        "email": {"total_tasks": 2, "completed_tasks": 2, "failed_tasks": 0, "success_rate": 1.0},
        "hello": {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0, "success_rate": 1.0}
      }
    }
  ]
}
```

说明：

- `compare_plugins` 与 `plugin_name` 不建议同时使用
- 如果同时传入，服务会优先使用 `compare_plugins` 并忽略 `plugin_name`
- 前端可以把 `trend[*].plugins` 中每个插件当作一条折线序列

### 归一化趋势

通过 `normalize=true` 可以对每个插件自己的 `total_tasks` 序列做 Min-Max 归一化，帮助不同量级的插件在同一张图上比较形状。

- 归一化是按插件独立计算的
- 返回原始 `total_tasks`，同时新增 `normalized_total_tasks`
- 每个插件的最大值会变为 `1.0`，最小值会变为 `0.0`
- 如果一个插件所有值都相同，则归一化结果全部为 `0`

### CSV 导出

通过 `export_format=csv` 可以把趋势数据导出为 CSV 文件：

```bash
curl -OJ "http://localhost:8000/api/v1/plugins/metrics?bucket=day&plugin_name=email&export_format=csv"
curl -OJ "http://localhost:8000/api/v1/plugins/metrics?bucket=day&compare_plugins=email,hello&normalize=true&export_format=csv"
```

- 响应 Content-Type 为 `text/csv; charset=utf-8`
- Content-Disposition 提供建议文件名 `trend_export.csv`
- 可直接导入 Excel 或其他分析工具

单插件 CSV 列：

- `bucket_date`
- `plugin_name`
- `total_tasks`
- `completed_tasks`
- `failed_tasks`
- `success_rate`
- `normalized_total_tasks`（仅在 `normalize=true` 时）

多插件 CSV 为宽表，列名前缀使用插件名，例如：

- `email_total_tasks`
- `email_completed_tasks`
- `hello_total_tasks`
- `hello_completed_tasks`

### 报警与飞书推送

当传入 `alert_thresholds` 时，接口会生成 `alerts` 字段。
支持多个规则同时配置，例如：

```bash
curl "http://localhost:8000/api/v1/plugins/metrics?plugin_name=email&alert_thresholds={\"success_rate\":0.8,\"failed_tasks\":5,\"total_tasks\":100}&send_feishu=true"
```

支持的规则：

- `success_rate`：低于阈值触发
- `failed_tasks`：高于阈值触发
- `total_tasks`：高于阈值触发

如果同时传入 `send_feishu=true`，则会把报警信息推送到飞书群聊。
飞书消息默认只使用第一条触发规则的信息填充模板，`alerts` 字段仍会返回全部触发规则。

示例：

```bash
curl "http://localhost:8000/api/v1/plugins/metrics?plugin_name=email&alert_thresholds={\"success_rate\":0.8,\"failed_tasks\":5}&send_feishu=true"
```

如果启用了飞书签名，请配置：

- `FEISHU_WEBHOOK_URL`
- `FEISHU_SECRET`（可选）

### 报警飞书推送频率限制

默认情况下，同一插件在 10 分钟内只发送一次飞书消息。

- 环境变量：`ALERT_FREQUENCY_LIMIT_MINUTES=10`
- 设置为 `0` 表示不限制
- 频率限制只影响飞书发送，不影响 `alerts` 字段返回
- 当前按插件整体限流，而不是按规则限流

### 自定义报警消息模板

通过 `alert_message_template` 可以自定义飞书报警消息内容。

支持变量：

- `{plugin_name}`：插件名称
- `{rule}`：报警规则名称
- `{threshold}`：阈值
- `{actual}`：当前值
- `{alert_time}`：报警时间，格式 `YYYY-MM-DD HH:MM:SS`

默认模板：

```text
【插件报警】
插件: {plugin_name}
规则: {rule} (阈值 {threshold}, 当前值 {actual})
触发时间: {alert_time}
请查看指标详情。
```

示例：

```bash
curl "http://localhost:8000/api/v1/plugins/metrics?plugin_name=email&alert_thresholds={\"success_rate\":0.8,\"failed_tasks\":5}&send_feishu=true&alert_message_template=🚨%20告警：{plugin_name}%20的%20{rule}%20异常！当前值%20{actual}%20低于阈值%20{threshold}，请及时处理。"
```

提示：飞书消息有长度限制，建议模板不要过长，通常控制在 2000 字符以内更稳妥。

### 报警历史记录

所有触发的报警都会写入 SQLite 中的 `alert_history` 表，字段包括：

- `alert_id`
- `plugin_name`
- `rule`
- `threshold`
- `actual`
- `triggered_at`
- `message_sent`

查询接口：

```bash
curl "http://localhost:8000/api/v1/plugins/alerts/history"
curl "http://localhost:8000/api/v1/plugins/alerts/history?plugin_name=email&rule=success_rate"
curl "http://localhost:8000/api/v1/plugins/alerts/history?start_time=2026-05-01T00:00:00&end_time=2026-05-31T23:59:59&limit=20&offset=0"
```

返回结构：

```json
{
  "total": 123,
  "alerts": [
    {
      "alert_id": 1,
      "plugin_name": "email",
      "rule": "success_rate",
      "threshold": 0.8,
      "actual": 0.65,
      "triggered_at": "2026-05-17T10:30:00",
      "message_sent": true
    }
  ]
}
```

- 默认按 `triggered_at` 倒序排列
- 支持分页 `limit` / `offset`
- 支持按插件名、规则、时间范围过滤

### 报警历史统计

用于仪表盘快速查看报警概况：

```bash
curl "http://localhost:8000/api/v1/plugins/alerts/history/stats"
curl "http://localhost:8000/api/v1/plugins/alerts/history/stats?plugin_name=email&rule=success_rate"
```

返回示例：

```json
{
  "total_alerts": 42,
  "sent_alerts": 30,
  "blocked_alerts": 12,
  "by_rule": {
    "success_rate": 30,
    "failed_tasks": 8,
    "total_tasks": 4
  }
}
```

### 报警历史清理

⚠️ 仅内部使用，生产环境需加权限控制。
⚠️ 这是物理删除，**不可恢复**，调用前请确认已经做好数据备份。

支持的查询参数与历史查询接口一致：

- `plugin_name`：按插件名过滤
- `rule`：按规则过滤
- `start_time`：ISO 8601 起始时间
- `end_time`：ISO 8601 结束时间

```bash
curl -X DELETE "http://localhost:8000/api/v1/plugins/alerts/history?plugin_name=email&rule=success_rate&start_time=2026-05-01T00:00:00&end_time=2026-05-31T23:59:59"
curl -X DELETE "http://localhost:8000/api/v1/plugins/alerts/history"
```

- 响应示例：`{"deleted_count": 42}`
- 删除条件按所有已传入参数同时生效，匹配后直接物理删除
- 删除操作会记录 INFO 日志，便于追溯
- 建议定期清理，或通过定时任务自动执行
- 生产环境建议在网关、反向代理或应用层补充权限控制与二次确认

非法时间参数会被忽略并记录警告，不会中断请求。

### 报警历史导出

⚠️ 仅内部使用，生产环境需加权限控制。

导出接口支持按相同条件筛选报警历史，并以 JSON 或 CSV 返回：

- `format=json`：直接返回 JSON 数组，字段与历史查询接口的 `alerts` 项一致
- `format=csv`：返回 CSV 文件，文件名 `alerts_export.csv`，使用 UTF-8 with BOM，便于 Excel 打开

支持参数：

- `plugin_name`
- `rule`
- `start_time`
- `end_time`
- `format`（默认 `json`）

建议在导出大数据量时配合 `start_time` / `end_time` 缩小范围。
当前实现会限制单次最多导出 5000 条，超出时返回 400，请缩小查询范围后重试。

每次成功导出后，系统会同步写入一条审计记录到 `export_audit_log`，包含：

- 导出时间
- 请求参数 JSON
- 导出条数
- 请求来源（优先记录客户端 IP）

JSON 示例：

```bash
curl "http://localhost:8000/api/v1/plugins/alerts/history/export?plugin_name=email&rule=success_rate&format=json"
```

CSV 示例：

```bash
curl -L -o alerts_export.csv "http://localhost:8000/api/v1/plugins/alerts/history/export?plugin_name=email&rule=success_rate&format=csv"
```

带时间范围过滤的导出：

```bash
curl "http://localhost:8000/api/v1/plugins/alerts/history/export?start_time=2026-05-01T00:00:00&end_time=2026-05-31T23:59:59&format=json"
```

### 导出审计记录查询

⚠️ 仅内部使用，生产环境需加权限控制。

查看导出审计日志：

```bash
curl "http://localhost:8000/api/v1/plugins/alerts/export/audit"
```

按时间范围过滤并分页：

```bash
curl "http://localhost:8000/api/v1/plugins/alerts/export/audit?start_time=2026-05-01T00:00:00&end_time=2026-05-31T23:59:59&limit=20&offset=0"
```

返回示例包含：

- `total`
- `logs` 数组

建议配合之前的清理接口一起使用，避免历史与审计表无限增长。

示例：

```bash
curl "http://localhost:8000/api/v1/plugins/metrics?start_time=2026-05-01T00:00:00&end_time=2026-05-31T23:59:59"
```

## 任务列表接口常用参数

- `plugin_name`：按插件名过滤
- `status`：按状态过滤
- `start_time`、`end_time`：按 `created_at` 时间范围过滤，使用 ISO 8601 格式
- `sort_by`、`order`：排序参数
- `page`、`page_size`：分页参数

### 时间范围参数说明

`start_time` 和 `end_time` 使用 ISO 8601 格式，例如：

```bash
curl "http://localhost:8000/api/v1/tasks?start_time=2026-05-01T00:00:00&end_time=2026-05-07T23:59:59"
```

如果时间格式非法，服务会忽略该参数并记录警告，不会中断请求。

## 启动服务

```bash
python scripts/init_db.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 任务列表查询

```bash
curl http://localhost:8000/api/v1/tasks
curl "http://localhost:8000/api/v1/tasks?plugin_name=email"
curl "http://localhost:8000/api/v1/tasks?status=completed&page=1&page_size=20"
curl "http://localhost:8000/api/v1/tasks?plugin_name=email&status=completed&sort_by=created_at&order=desc&page=1&page_size=10"
curl "http://localhost:8000/api/v1/tasks?start_time=2026-05-01T00:00:00&end_time=2026-05-07T23:59:59"
```

返回字段包含：

- `tasks`
- `total`
- `page`
- `page_size`

## 触发邮件任务 API

```bash
curl -X POST http://localhost:8000/api/v1/email/tasks \
  -H "Content-Type: application/json" \
  -d '{}'
```

返回示例中会包含：

- `total_emails_fetched`
- `total_new_emails`
- `report`
- `details`

## 查询任务 API

```bash
curl http://localhost:8000/api/v1/tasks/uuid
```

## 运行测试脚本

```bash
python scripts/test_email_plugin.py
python scripts/test_hello_plugin.py
python scripts/test_timestamp_plugin.py
python scripts/test_plugins_list.py
python scripts/test_plugins_market.py
python scripts/test_plugin_docs.py
python scripts/test_task_list.py
python scripts/test_plugins_metrics.py
python scripts/test_plugins_trend.py
python scripts/test_plugins_alerts.py
python scripts/test_alert_frequency.py
python scripts/test_alert_template.py
python scripts/test_alert_history.py
```

## 目录说明

- `app/main.py`：FastAPI 入口和任务 API
- `app/database.py`：SQLite 初始化与任务表 CRUD
- `app/plugins/`：插件实现与注册表
- `app/services/feishu_client.py`：公共飞书客户端
- `scripts/`：测试与初始化脚本

## 说明

当前版本实现了插件市场展示、插件运行指标、任务查询、分页、排序、过滤和时间范围筛选，且所有能力保持向后兼容。

## 项目架构（插件总览）

本服务通过 **插件注册表**（`app/plugins/registry.py`）加载业务能力，统一由任务 API 或飞书长连接触发。当前已注册插件如下：

| 插件名 | 说明 | 触发方式 | 主要依赖 |
|--------|------|----------|----------|
| `email` | 邮件分析：IMAP 读取、Dify 分析、汇总报告 | 飞书：`分析邮件` / `邮件报告` / `跑邮件`；API：`POST /api/v1/email/tasks` | IMAP 邮箱、`EMAIL_DIFY_*`、飞书 |
| `hello` | 框架示例插件 | API：`POST /api/v1/hello/tasks` | 无 |
| `timestamp` | 返回服务器时间戳 | API：`POST /api/v1/timestamp/tasks` | 无 |
| `product` | 选品分析：按关键词生成模拟选品报告 | 飞书：`选品分析 <关键词>`；API：`POST /api/v1/product/tasks` | `PRODUCT_DIFY_*`、飞书 |
| `listing` | Listing 优化：标题、五点、关键词、A+ 等建议 | 飞书：`Listing 优化 <文本>`；API：`POST /api/v1/listing/tasks` | `LISTING_DIFY_*`、飞书 |
| `ad` | 广告监控：模拟广告数据 + 规则优化建议 | 飞书：`广告报告` / `广告优化`；API：`POST /api/v1/ad/tasks` | 无（内置模拟数据） |

飞书指令由 `app/services/feishu_commands.py` 解析，创建任务后同步执行插件，并将 `result.report` 推送到群聊。

## 选品分析插件（Product Plugin）

根据用户输入的关键词，调用 Dify 工作流 `product_analyzer` 生成模拟选品报告（评分、总结、建议）。未配置 Dify 或调用失败时可回退 mock 数据。

### 飞书指令

在群内 @机器人 发送：

```text
选品分析 无线耳机
```

机器人会先回复「正在分析中...」，完成后将纯文本报告发送到群聊。

### 配置要求

在 `.env` 中配置（参见 `.env.example`）：

```bash
PRODUCT_DIFY_API_URL=http://your-dify-host/v1/workflows/run
PRODUCT_DIFY_API_KEY=app-product-workflow-key
```

另需配置飞书长连接：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`。

### API 调用示例

```bash
curl -X POST http://localhost:8000/api/v1/product/tasks \
  -H "Content-Type: application/json" \
  -d '{"keyword": "无线耳机", "chat_id": "oc_xxxxx"}'
```

### 本地测试

```bash
python scripts/test_product_plugin.py
```

## Listing 优化插件（Listing Plugin）

针对商品关键词或现有 Listing 文本，调用 Dify 工作流 `listing_optimizer`，生成亚马逊 Listing 优化建议（标题、五点、后台关键词、A+ 建议、评分与差异化等）。

### 飞书指令

```text
Listing 优化 无线耳机
```

机器人会先回复「正在分析 Listing...」，完成后发送分段清晰的纯文本报告。

### 配置要求

Listing 插件使用**独立**环境变量（无全局 Dify 回退），可与选品插件共用同一 Dify 部署实例，但需单独发布工作流并获取 API Key：

```bash
LISTING_DIFY_API_URL=http://your-dify-host/v1/workflows/run
LISTING_DIFY_API_KEY=app-listing-workflow-key
```

工作流输入变量：`product_input`。

### API 调用示例

```bash
curl -X POST http://localhost:8000/api/v1/listing/tasks \
  -H "Content-Type: application/json" \
  -d '{"product_input": "无线耳机", "chat_id": "oc_xxxxx"}'
```

### 本地测试

```bash
python scripts/test_listing_plugin.py
```

## 广告监控插件（Ad Plugin）

基于内置模拟数据生成近 7 天广告活动整体指标与关键词明细，通过规则引擎输出优化建议（如 ACOS 过高降价、无转化加否定词、CTR 偏低优化创意等）。**不调用 Dify**，不依赖外部广告 API。

### 飞书指令

```text
广告报告
```

或：

```text
广告优化
```

机器人会先回复「正在获取广告数据...」，随后发送包含整体指标与关键词建议的纯文本报告。

### 配置要求

无需额外 Dify 或广告 API 配置；仅需飞书长连接（`FEISHU_APP_ID`、`FEISHU_APP_SECRET`）即可通过群指令触发。

数据来源为插件内置模拟数据，后续可对接真实 SP-API 或报表导入。

### API 调用示例

```bash
curl -X POST http://localhost:8000/api/v1/ad/tasks \
  -H "Content-Type: application/json" \
  -d '{"chat_id": "oc_xxxxx"}'
```

### 规则说明（摘要）

| 条件 | 建议 |
|------|------|
| ACOS > 30% | 降低出价或暂停 |
| CTR < 1% | 优化创意或调整匹配方式 |
| ACOS < 20% 且转化良好 | 提高出价 |
| 无转化 | 添加为否定关键词 |
