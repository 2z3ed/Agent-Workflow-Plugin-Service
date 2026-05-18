import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import settings

TASKS_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    plugin_name TEXT,
    status TEXT,
    params TEXT,
    result TEXT,
    error TEXT,
    created_at DATETIME,
    completed_at DATETIME
)
"""

ALERT_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS alert_history (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_name TEXT NOT NULL,
    rule TEXT NOT NULL,
    threshold REAL,
    actual REAL,
    triggered_at DATETIME NOT NULL,
    message_sent INTEGER NOT NULL DEFAULT 0
)
"""

ALERT_HISTORY_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_alert_history_plugin_name_triggered_at
ON alert_history(plugin_name, triggered_at)
"""

EXPORT_AUDIT_LOG_SQL = """
CREATE TABLE IF NOT EXISTS export_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_time DATETIME NOT NULL,
    params TEXT NOT NULL,
    export_count INTEGER NOT NULL,
    requester TEXT
)
"""

EXPORT_AUDIT_LOG_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_export_audit_log_export_time
ON export_audit_log(export_time DESC)
"""


def _get_connection() -> sqlite3.Connection:
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def init_db() -> None:
    with _get_connection() as conn:
        conn.execute(TASKS_SQL)
        conn.execute(ALERT_HISTORY_SQL)
        conn.execute(ALERT_HISTORY_INDEX_SQL)
        conn.execute(EXPORT_AUDIT_LOG_SQL)
        conn.execute(EXPORT_AUDIT_LOG_INDEX_SQL)
        conn.commit()


def create_task(task_id: str, plugin_name: str, params: dict[str, Any], created_at: str, status: str) -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tasks (task_id, plugin_name, status, params, result, error, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, plugin_name, status, json.dumps(params, ensure_ascii=False), None, None, created_at, None),
        )
        conn.commit()


def update_task_status(
    task_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    completed_at: str | None = None,
) -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, result = ?, error = ?, completed_at = ?
            WHERE task_id = ?
            """,
            (status, json.dumps(result, ensure_ascii=False) if result is not None else None, error, completed_at, task_id),
        )
        conn.commit()


def get_task(task_id: str) -> dict[str, Any] | None:
    with _get_connection() as conn:
        cursor = conn.execute(
            "SELECT task_id, status, created_at, completed_at, result, error FROM tasks WHERE task_id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "task_id": row[0],
            "status": row[1],
            "created_at": row[2],
            "completed_at": row[3],
            "result": json.loads(row[4]) if row[4] else None,
            "error": row[5],
        }


def get_tasks(
    status: str | None = None,
    plugin_name: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    page: int = 1,
    page_size: int | None = None,
    sort_by: str = "created_at",
    order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    allowed_sort_by = {"created_at", "completed_at", "status"}
    allowed_order = {"asc", "desc"}
    safe_sort_by = sort_by if sort_by in allowed_sort_by else "created_at"
    safe_order = order if order in allowed_order else "desc"

    where_clauses = []
    params: list[Any] = []
    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if plugin_name:
        where_clauses.append("plugin_name = ?")
        params.append(plugin_name)
    if start_time:
        where_clauses.append("created_at >= ?")
        params.append(start_time)
    if end_time:
        where_clauses.append("created_at <= ?")
        params.append(end_time)

    where_clause = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    count_query = f"SELECT COUNT(*) FROM tasks{where_clause}"
    data_query = (
        f"SELECT task_id, status, plugin_name, created_at, completed_at, error FROM tasks{where_clause} "
        f"ORDER BY {safe_sort_by} {safe_order}"
    )

    safe_page = max(1, page)
    safe_page_size = None if page_size is None else max(1, page_size)

    with _get_connection() as conn:
        total = conn.execute(count_query, tuple(params)).fetchone()[0]

        if safe_page_size is not None:
            offset = (safe_page - 1) * safe_page_size
            data_query += " LIMIT ? OFFSET ?"
            query_params = tuple(params + [safe_page_size, offset])
            cursor = conn.execute(data_query, query_params)
        else:
            cursor = conn.execute(data_query, tuple(params))

        rows = cursor.fetchall()
        tasks = [
            {
                "task_id": row[0],
                "status": row[1],
                "plugin_name": row[2],
                "created_at": row[3],
                "completed_at": row[4],
                "error": row[5],
            }
            for row in rows
        ]
        return tasks, total


def save_alert_history(plugin_name: str, rule: str, threshold: float, actual: float | None, message_sent: bool) -> None:
    triggered_at = datetime.now().isoformat(timespec="seconds")
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO alert_history (plugin_name, rule, threshold, actual, triggered_at, message_sent)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (plugin_name, rule, threshold, actual, triggered_at, 1 if message_sent else 0),
        )
        conn.commit()


def get_alert_history(
    plugin_name: str | None = None,
    rule: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int | None = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where_clauses = []
    params: list[Any] = []
    if plugin_name:
        where_clauses.append("plugin_name = ?")
        params.append(plugin_name)
    if rule:
        where_clauses.append("rule = ?")
        params.append(rule)
    if start_time:
        where_clauses.append("triggered_at >= ?")
        params.append(start_time)
    if end_time:
        where_clauses.append("triggered_at <= ?")
        params.append(end_time)

    where_clause = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    count_query = f"SELECT COUNT(*) FROM alert_history{where_clause}"
    data_query = (
        f"SELECT alert_id, plugin_name, rule, threshold, actual, triggered_at, message_sent "
        f"FROM alert_history{where_clause} ORDER BY triggered_at DESC, alert_id DESC"
    )

    safe_offset = max(0, offset)
    limit_clause = ""
    query_params = tuple(params)
    if limit is not None:
        safe_limit = min(200, max(1, limit))
        limit_clause = " LIMIT ? OFFSET ?"
        query_params = tuple(params + [safe_limit, safe_offset])

    with _get_connection() as conn:
        total = conn.execute(count_query, tuple(params)).fetchone()[0]
        cursor = conn.execute(data_query + limit_clause, query_params)
        rows = cursor.fetchall()
        alerts = [
            {
                "alert_id": row[0],
                "plugin_name": row[1],
                "rule": row[2],
                "threshold": row[3],
                "actual": row[4],
                "triggered_at": row[5],
                "message_sent": bool(row[6]),
            }
            for row in rows
        ]
        return alerts, total


def get_alert_history_stats(
    plugin_name: str | None = None,
    rule: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    where_clauses = []
    params: list[Any] = []
    if plugin_name:
        where_clauses.append("plugin_name = ?")
        params.append(plugin_name)
    if rule:
        where_clauses.append("rule = ?")
        params.append(rule)
    if start_time:
        where_clauses.append("triggered_at >= ?")
        params.append(start_time)
    if end_time:
        where_clauses.append("triggered_at <= ?")
        params.append(end_time)

    where_clause = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    with _get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_alerts,
                SUM(CASE WHEN message_sent = 1 THEN 1 ELSE 0 END) AS sent_alerts,
                SUM(CASE WHEN message_sent = 0 THEN 1 ELSE 0 END) AS blocked_alerts
            FROM alert_history{where_clause}
            """,
            tuple(params),
        ).fetchone()

        total_alerts = row[0] or 0
        sent_alerts = row[1] or 0
        blocked_alerts = row[2] or 0

        by_rule_rows = conn.execute(
            f"""
            SELECT rule, COUNT(*) AS count
            FROM alert_history{where_clause}
            GROUP BY rule
            ORDER BY rule ASC
            """,
            tuple(params),
        ).fetchall()

    return {
        "total_alerts": total_alerts,
        "sent_alerts": sent_alerts,
        "blocked_alerts": blocked_alerts,
        "by_rule": {rule_name: count for rule_name, count in by_rule_rows},
    }


def save_export_audit(params_json: str, export_count: int, requester: str | None) -> None:
    export_time = datetime.now().isoformat(timespec="seconds")
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO export_audit_log (export_time, params, export_count, requester)
            VALUES (?, ?, ?, ?)
            """,
            (export_time, params_json, export_count, requester),
        )
        conn.commit()


def get_export_audit_logs(
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where_clauses = []
    params: list[Any] = []
    if start_time:
        where_clauses.append("export_time >= ?")
        params.append(start_time)
    if end_time:
        where_clauses.append("export_time <= ?")
        params.append(end_time)

    where_clause = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    safe_limit = min(200, max(1, limit))
    safe_offset = max(0, offset)

    with _get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM export_audit_log{where_clause}", tuple(params)).fetchone()[0]
        cursor = conn.execute(
            f"""
            SELECT id, export_time, params, export_count, requester
            FROM export_audit_log{where_clause}
            ORDER BY export_time DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [safe_limit, safe_offset]),
        )
        rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "export_time": row[1],
            "params": json.loads(row[2]) if row[2] else {},
            "export_count": row[3],
            "requester": row[4],
        }
        for row in rows
    ], total


def delete_alert_history(
    plugin_name: str | None = None,
    rule: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> int:
    where_clauses = []
    params: list[Any] = []
    if plugin_name:
        where_clauses.append("plugin_name = ?")
        params.append(plugin_name)
    if rule:
        where_clauses.append("rule = ?")
        params.append(rule)
    if start_time:
        where_clauses.append("triggered_at >= ?")
        params.append(start_time)
    if end_time:
        where_clauses.append("triggered_at <= ?")
        params.append(end_time)

    where_clause = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    with _get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM alert_history{where_clause}", tuple(params))
        conn.commit()
        return cursor.rowcount or 0


def get_plugins_metrics(start_time: str | None = None, end_time: str | None = None, plugin_name: str | None = None) -> list[dict[str, Any]]:
    where_clauses = []
    params: list[Any] = []
    if start_time:
        where_clauses.append("created_at >= ?")
        params.append(start_time)
    if end_time:
        where_clauses.append("created_at <= ?")
        params.append(end_time)
    if plugin_name:
        where_clauses.append("plugin_name = ?")
        params.append(plugin_name)

    where_clause = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    with _get_connection() as conn:
        cursor = conn.execute(
            f"""
            SELECT
                plugin_name,
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_tasks,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_tasks,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_tasks,
                MAX(created_at) AS last_execution_at,
                AVG(CASE WHEN status = 'completed' AND completed_at IS NOT NULL THEN (julianday(completed_at) - julianday(created_at)) * 86400.0 END) AS avg_execution_seconds
            FROM tasks{where_clause}
            GROUP BY plugin_name
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        metrics = []
        for row in rows:
            total_tasks = row[1] or 0
            completed_tasks = row[2] or 0
            failed_tasks = row[3] or 0
            running_tasks = row[4] or 0
            pending_tasks = row[5] or 0
            avg_execution_seconds = float(row[7]) if row[7] is not None else None
            success_rate = (completed_tasks / total_tasks) if total_tasks > 0 else None
            metrics.append(
                {
                    "plugin_name": row[0],
                    "total_tasks": total_tasks,
                    "completed_tasks": completed_tasks,
                    "failed_tasks": failed_tasks,
                    "running_tasks": running_tasks,
                    "pending_tasks": pending_tasks,
                    "last_execution_at": row[6],
                    "avg_execution_seconds": avg_execution_seconds,
                    "success_rate": success_rate,
                    "status_breakdown": {
                        "completed": completed_tasks,
                        "failed": failed_tasks,
                        "running": running_tasks,
                        "pending": pending_tasks,
                    },
                }
            )
        return metrics


def _iter_buckets(start_time: str, end_time: str, bucket: str) -> list[str]:
    start_dt = datetime.fromisoformat(start_time)
    end_dt = datetime.fromisoformat(end_time)
    buckets: list[str] = []

    if bucket == "day":
        current = start_dt.date()
        end_date = end_dt.date()
        while current <= end_date:
            buckets.append(current.strftime("%Y-%m-%d"))
            current = current + timedelta(days=1)
        return buckets

    current = datetime(start_dt.year, start_dt.month, 1)
    end_month = datetime(end_dt.year, end_dt.month, 1)
    while current <= end_month:
        buckets.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1)
        else:
            current = datetime(current.year, current.month + 1, 1)
    return buckets


def _bucket_expression(bucket: str) -> str:
    if bucket == "day":
        return "strftime('%Y-%m-%d', created_at)"
    if bucket == "month":
        return "strftime('%Y-%m', created_at)"
    return ""


def _parse_compare_plugins(compare_plugins: str | list[str] | None) -> list[str]:
    if compare_plugins is None:
        return []
    if isinstance(compare_plugins, list):
        items = compare_plugins
    else:
        items = compare_plugins.split(",")
    return [item.strip() for item in items if item.strip()]


def _parse_bool(value: bool | str | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes", "on"}
    return False


def _normalize_series(values: list[int | float]) -> list[float]:
    if not values:
        return []
    min_val = min(values)
    max_val = max(values)
    if max_val == min_val:
        return [0.0 for _ in values]
    return [round((value - min_val) / (max_val - min_val), 4) for value in values]


def get_plugins_trend(
    bucket: str,
    start_time: str | None = None,
    end_time: str | None = None,
    plugin_name: str | None = None,
    compare_plugins: str | list[str] | None = None,
    normalize: bool | str | None = False,
) -> list[dict[str, Any]]:
    bucket_expr = _bucket_expression(bucket)
    if not bucket_expr:
        return []

    compare_list = _parse_compare_plugins(compare_plugins)
    if compare_list:
        plugin_name = None

    where_clauses = []
    params: list[Any] = []
    if start_time:
        where_clauses.append("created_at >= ?")
        params.append(start_time)
    if end_time:
        where_clauses.append("created_at <= ?")
        params.append(end_time)
    if plugin_name:
        where_clauses.append("plugin_name = ?")
        params.append(plugin_name)
    elif compare_list:
        placeholders = ",".join(["?"] * len(compare_list))
        where_clauses.append(f"plugin_name IN ({placeholders})")
        params.extend(compare_list)

    where_clause = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    with _get_connection() as conn:
        cursor = conn.execute(
            f"""
            SELECT
                {bucket_expr} AS bucket_date,
                plugin_name,
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_tasks
            FROM tasks{where_clause}
            GROUP BY bucket_date, plugin_name
            ORDER BY bucket_date ASC, plugin_name ASC
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        raw_records = [
            {
                "bucket_date": row[0],
                "plugin_name": row[1],
                "total_tasks": row[2] or 0,
                "completed_tasks": row[3] or 0,
                "failed_tasks": row[4] or 0,
                "success_rate": (row[3] / row[2]) if row[2] else None,
            }
            for row in rows
        ]

    if not (start_time and end_time):
        trend = _build_trend_without_fill(raw_records, compare_list)
        return _apply_normalize_to_trend(trend, _parse_bool(normalize))

    bucket_dates = _iter_buckets(start_time, end_time, bucket)
    if compare_list:
        trend = _trend_compare_with_fill(raw_records, bucket_dates, compare_list)
        return _apply_normalize_to_trend(trend, _parse_bool(normalize))

    plugin_names = sorted({record["plugin_name"] for record in raw_records})
    if not plugin_names:
        return []

    filled_records: list[dict[str, Any]] = []
    for plugin in plugin_names:
        plugin_records = {record["bucket_date"]: record for record in raw_records if record["plugin_name"] == plugin}
        for bucket_date in bucket_dates:
            record = plugin_records.get(bucket_date)
            if record is None:
                filled_records.append(
                    {
                        "bucket_date": bucket_date,
                        "plugin_name": plugin,
                        "total_tasks": 0,
                        "completed_tasks": 0,
                        "failed_tasks": 0,
                        "success_rate": None,
                    }
                )
            else:
                filled_records.append(record)

    filled_records.sort(key=lambda item: (item["bucket_date"], item["plugin_name"]))
    return _apply_normalize_to_trend(filled_records, _parse_bool(normalize))


def _build_trend_without_fill(raw_records: list[dict[str, Any]], compare_list: list[str]) -> list[dict[str, Any]]:
    if compare_list:
        return _trend_compare_records(raw_records, compare_list)
    return raw_records


def _apply_normalize_to_trend(trend: list[dict[str, Any]], normalize: bool) -> list[dict[str, Any]]:
    if not normalize:
        return trend
    if trend and "plugins" in trend[0]:
        plugin_series: dict[str, list[int]] = {}
        for item in trend:
            for plugin, payload in item["plugins"].items():
                plugin_series.setdefault(plugin, []).append(payload["total_tasks"])
        normalized_lookup = {plugin: _normalize_series(values) for plugin, values in plugin_series.items()}
        for index, item in enumerate(trend):
            for plugin, payload in item["plugins"].items():
                normalized_values = normalized_lookup.get(plugin, [])
                payload["normalized_total_tasks"] = normalized_values[index] if index < len(normalized_values) else 0.0
        return trend

    plugin_series: dict[str, list[int]] = {}
    for item in trend:
        plugin_series.setdefault(item["plugin_name"], []).append(item["total_tasks"])

    normalized_lookup = {plugin: _normalize_series(values) for plugin, values in plugin_series.items()}
    counters: dict[str, int] = {plugin: 0 for plugin in normalized_lookup}
    for item in trend:
        plugin = item["plugin_name"]
        index = counters.get(plugin, 0)
        normalized_values = normalized_lookup.get(plugin, [])
        item["normalized_total_tasks"] = normalized_values[index] if index < len(normalized_values) else 0.0
        counters[plugin] = index + 1
    return trend


def _trend_compare_records(raw_records: list[dict[str, Any]], compare_list: list[str]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in raw_records:
        bucket_date = record["bucket_date"]
        grouped.setdefault(bucket_date, {"bucket_date": bucket_date, "plugins": {}})
        grouped[bucket_date]["plugins"][record["plugin_name"]] = {
            "total_tasks": record["total_tasks"],
            "completed_tasks": record["completed_tasks"],
            "failed_tasks": record["failed_tasks"],
            "success_rate": record["success_rate"],
        }

    trend = []
    for bucket_date in sorted(grouped.keys()):
        plugins_map = grouped[bucket_date]["plugins"]
        for plugin in compare_list:
            plugins_map.setdefault(
                plugin,
                {
                    "total_tasks": 0,
                    "completed_tasks": 0,
                    "failed_tasks": 0,
                    "success_rate": None,
                },
            )
        trend.append({"bucket_date": bucket_date, "plugins": dict(sorted(plugins_map.items()))})
    return trend


def _trend_compare_with_fill(raw_records: list[dict[str, Any]], bucket_dates: list[str], compare_list: list[str]) -> list[dict[str, Any]]:
    lookup = {(record["bucket_date"], record["plugin_name"]): record for record in raw_records}
    trend = []
    for bucket_date in bucket_dates:
        plugins_map = {}
        for plugin in compare_list:
            record = lookup.get((bucket_date, plugin))
            if record is None:
                plugins_map[plugin] = {"total_tasks": 0, "completed_tasks": 0, "failed_tasks": 0, "success_rate": None}
            else:
                plugins_map[plugin] = {
                    "total_tasks": record["total_tasks"],
                    "completed_tasks": record["completed_tasks"],
                    "failed_tasks": record["failed_tasks"],
                    "success_rate": record["success_rate"],
                }
        trend.append({"bucket_date": bucket_date, "plugins": plugins_map})
    return trend
