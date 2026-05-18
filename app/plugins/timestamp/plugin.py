from datetime import datetime, timezone

from app.plugins.base import Plugin


class TimestampPlugin(Plugin):
    name = "timestamp"
    description = "返回当前服务器时间戳（UTC 和本地时间）"
    category = "utility"
    docs = """
# 时间戳插件

返回当前服务器的 UTC 时间和本地时间，可用于调试或同步。

## 输入参数
无

## 输出示例
{
  "utc_timestamp": "2026-05-17T10:00:00Z",
  "local_timestamp": "2026-05-17T18:00:00",
  "timezone_local": "Asia/Shanghai",
  "task_id": "xxx"
}
"""

    def execute(self, task_id: str, **params) -> dict:
        utc_now = datetime.now(timezone.utc)
        local_now = datetime.now().astimezone()
        return {
            "utc_timestamp": utc_now.isoformat(),
            "local_timestamp": local_now.isoformat(),
            "timezone_local": str(local_now.tzinfo),
            "task_id": task_id,
        }
