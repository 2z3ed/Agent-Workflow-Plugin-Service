from abc import ABC, abstractmethod


class Plugin(ABC):
    name: str
    description: str = ""
    category: str = "uncategorized"
    docs: str = ""

    @abstractmethod
    def execute(self, task_id: str, **params) -> dict:
        pass
