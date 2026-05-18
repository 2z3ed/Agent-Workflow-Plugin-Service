from .email.plugin import EmailPlugin
from .hello.plugin import HelloPlugin
from .timestamp.plugin import TimestampPlugin

PLUGINS = {
    "email": EmailPlugin(),
    "hello": HelloPlugin(),
    "timestamp": TimestampPlugin(),
}


def get_plugin(name: str):
    return PLUGINS.get(name)


def get_plugins_metadata() -> list:
    return [
        {
            "name": plugin.name,
            "description": plugin.description,
            "enabled": True,
        }
        for plugin in PLUGINS.values()
    ]


def get_plugins_market(q: str = None, category: str = None, sort: str = None, page: int = 1, page_size: int | None = None):
    plugins = list(PLUGINS.values())

    if category:
        plugins = [plugin for plugin in plugins if plugin.category == category]

    if q:
        keyword = q.lower()
        plugins = [
            plugin
            for plugin in plugins
            if keyword in plugin.name.lower()
            or keyword in plugin.description.lower()
            or keyword in plugin.docs.lower()
        ]

    if sort == "name":
        plugins = sorted(plugins, key=lambda plugin: plugin.name)
    elif sort == "category":
        plugins = sorted(plugins, key=lambda plugin: plugin.category)

    total = len(plugins)
    if page_size is not None and page_size > 0:
        safe_page = max(1, page)
        safe_page_size = min(100, max(1, page_size))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        plugins = plugins[start:end]
        return (
            [
                {
                    "name": plugin.name,
                    "description": plugin.description,
                    "enabled": True,
                    "category": plugin.category,
                    "docs": plugin.docs,
                }
                for plugin in plugins
            ],
            total,
            safe_page,
            safe_page_size,
        )

    return [
        {
            "name": plugin.name,
            "description": plugin.description,
            "enabled": True,
            "category": plugin.category,
            "docs": plugin.docs,
        }
        for plugin in plugins
    ], total, page, page_size
