from datetime import datetime

from app.plugins.base import Plugin


class HelloPlugin(Plugin):
    name = "hello"
    description = "示例插件，返回问候语和时间戳，用于验证框架扩展性"
    category = "example"
    docs = """
# Hello 示例插件

返回一个简单的问候语和时间戳，用于验证框架扩展性。

## 输入参数
- name: 被问候者的名字，默认 "World"

## 输出示例
{
  "message": "Hello, Agent!",
  "timestamp": "2026-05-17T10:00:00",
  "plugin": "hello",
  "task_id": "xxx"
}
"""

    def execute(self, task_id: str, **params) -> dict:
        name = params.get("name", "World")
        return {
            "message": f"Hello, {name}!",
            "timestamp": datetime.now().isoformat(),
            "plugin": self.name,
            "task_id": task_id,
        }
