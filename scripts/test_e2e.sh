# #!/usr/bin/env bash
# set -euo pipefail

# curl -X POST http://localhost:8000/api/v1/email/tasks -H "Content-Type: application/json" -d '{}'
# curl "http://localhost:8000/api/v1/tasks?plugin_name=email&limit=1"
# curl "http://localhost:8000/api/v1/plugins/alerts/history"
# curl "http://localhost:8000/api/v1/plugins/alerts/history/stats"
# curl "http://localhost:8000/api/v1/plugins/alerts/history/export?format=json"
# curl "http://localhost:8000/api/v1/plugins/alerts/export/audit"
#!/bin/bash
# 端到端验收脚本

set -e

echo "=== 开始端到端验收 ==="

echo "1. 测试邮箱读取..."
python scripts/test_email_fetcher.py || exit 1

echo "2. 测试 Dify 调用..."
python scripts/test_dify.py || exit 1

echo "3. 测试飞书消息发送（可选）..."
python scripts/test_feishu_longconn.py || echo "⚠️ 飞书发送测试失败，继续..."

echo "4. 触发邮件分析任务..."
TASK_RESP=$(curl -s -X POST http://localhost:8000/api/v1/email/tasks \
  -H "Content-Type: application/json" -d '{}')
TASK_ID=$(echo $TASK_RESP | jq -r '.task_id')
echo "任务ID: $TASK_ID"

echo "5. 等待任务完成（10秒）..."
sleep 10

echo "6. 查询任务结果..."
curl -s "http://localhost:8000/api/v1/tasks/$TASK_ID" | jq .

echo "7. 检查飞书群是否收到汇总报告（请人工确认）"
read -p "按回车继续..."

echo "8. 测试报警接口..."
curl -s "http://localhost:8000/api/v1/plugins/metrics?alert_thresholds={\"success_rate\":0.9}&send_feishu=true" | jq .

echo "=== 验收完成 ==="