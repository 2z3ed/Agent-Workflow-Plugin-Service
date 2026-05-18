from datetime import datetime, timezone
from threading import Thread
from uuid import uuid4

from app import database
from app.models import TaskStatusEnum
from app.plugins.registry import get_plugin


class TaskManager:
    def create_task(self, plugin_name: str, params: dict) -> tuple[str, str]:
        task_id = str(uuid4())
        created_at = self._now()
        database.create_task(task_id, plugin_name, params, created_at, status=TaskStatusEnum.running.value)
        return task_id, created_at

    def start_async_task(self, task_id: str, plugin_name: str, params: dict) -> None:
        thread = Thread(
            target=self.execute_plugin_task,
            args=(task_id, plugin_name, params),
            daemon=True,
        )
        thread.start()

    def execute_plugin_task(self, task_id: str, plugin_name: str, params: dict) -> None:
        database.update_task_status(task_id, TaskStatusEnum.running.value)
        try:
            plugin = get_plugin(plugin_name)
            if plugin is None:
                raise ValueError(f"Plugin '{plugin_name}' not found")

            result = plugin.execute(task_id, **params)
            database.update_task_status(
                task_id,
                TaskStatusEnum.completed.value,
                result=result,
                completed_at=self._now(),
            )
        except Exception as exc:
            database.update_task_status(
                task_id,
                TaskStatusEnum.failed.value,
                error=str(exc),
                completed_at=self._now(),
            )

    def get_task(self, task_id: str):
        return database.get_task(task_id)

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


task_manager = TaskManager()
