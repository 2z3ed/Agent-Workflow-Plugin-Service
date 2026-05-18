from csv import writer
from datetime import datetime
from io import StringIO
import csv
import json
import time
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response

from app import database
from app.config import settings
from app.logger import setup_logger
from app.models import TaskCreateRequest, TaskResponse
from app.services.feishu_client import FeishuClient, get_long_conn_client, set_message_handler
from app.services.feishu_commands import handle_feishu_message
from app.task_manager import task_manager

app = FastAPI(title=settings.app_name)
logger = setup_logger(level=settings.log_level)
_last_alert_sent: dict[str, float] = {}
DEFAULT_ALERT_MESSAGE_TEMPLATE = "【插件报警】\n插件: {plugin_name}\n规则: {rule} (阈值 {threshold}, 当前值 {actual})\n触发时间: {alert_time}\n请查看指标详情。"


@app.on_event("startup")
def startup_event():
    database.init_db()
    if settings.feishu_enable_long_conn:
        set_message_handler(handle_feishu_message)
        get_long_conn_client().start_websocket()
        logger.info("Feishu long connection startup requested (email commands enabled)")


@app.on_event("shutdown")
def shutdown_event():
    if settings.feishu_enable_long_conn:
        get_long_conn_client().stop()


@app.get("/health")
def health_check():
    logger.info("Health check requested")
    return {"status": "ok"}


@app.get("/api/v1/plugins")
def list_plugins():
    from app.plugins.registry import get_plugins_metadata

    return {"plugins": get_plugins_metadata()}


@app.get("/api/v1/plugins/market")
def list_plugins_market(
    q: Optional[str] = None,
    category: Optional[str] = None,
    sort: Optional[str] = None,
    page: int = 1,
    page_size: Optional[int] = None,
):
    from app.plugins.registry import get_plugins_market

    safe_page = max(1, page)
    safe_page_size = None if page_size is None else min(100, max(1, page_size))
    plugins_result = get_plugins_market(q=q, category=category, sort=sort, page=safe_page, page_size=safe_page_size)

    if isinstance(plugins_result, tuple):
        plugins, total, current_page, current_page_size = plugins_result
        if current_page_size is None:
            return {"plugins": plugins}
        return {"plugins": plugins, "total": total, "page": current_page, "page_size": current_page_size}

    return {"plugins": plugins_result}


@app.get("/api/v1/plugins/metrics")
def list_plugins_metrics(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    plugin_name: Optional[str] = None,
    bucket: Optional[str] = None,
    compare_plugins: Optional[str] = None,
    normalize: Optional[str | bool] = None,
    export_format: Optional[str] = "json",
    alert_thresholds: Optional[str] = None,
    send_feishu: Optional[str | bool] = False,
    alert_message_template: Optional[str] = None,
):
    parsed_start_time = None
    parsed_end_time = None

    if start_time:
        try:
            datetime.fromisoformat(start_time)
            parsed_start_time = start_time
        except ValueError:
            logger.warning("Invalid start_time for plugin metrics ignored: %s", start_time)

    if end_time:
        try:
            datetime.fromisoformat(end_time)
            parsed_end_time = end_time
        except ValueError:
            logger.warning("Invalid end_time for plugin metrics ignored: %s", end_time)

    compare_list = compare_plugins
    if compare_list:
        if plugin_name:
            logger.warning("compare_plugins provided; plugin_name ignored: %s", plugin_name)
        plugin_name = None

    normalize_flag = _parse_bool(normalize)
    if bucket in {"day", "month"}:
        trend = database.get_plugins_trend(
            bucket=bucket,
            start_time=parsed_start_time,
            end_time=parsed_end_time,
            plugin_name=plugin_name,
            compare_plugins=compare_list,
            normalize=normalize_flag,
        )
        if (export_format or "json").lower() == "csv":
            csv_content = _convert_trend_to_csv(trend, normalize_flag)
            return Response(
                content=csv_content,
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="trend_export.csv"'},
            )
        return {"trend": trend}

    metrics = database.get_plugins_metrics(start_time=parsed_start_time, end_time=parsed_end_time, plugin_name=plugin_name)

    if alert_thresholds is None:
        return {"plugins": metrics}

    thresholds = _parse_alert_thresholds(alert_thresholds)
    metrics_with_alerts = [_apply_alerts_to_metric(metric, thresholds) for metric in metrics]
    if _parse_bool(send_feishu):
        _send_alerts_to_feishu(metrics_with_alerts, alert_message_template)
    return {"plugins": metrics_with_alerts}


@app.get("/api/v1/plugins/alerts/history")
def list_alert_history(
    plugin_name: Optional[str] = None,
    rule: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    alerts, total = database.get_alert_history(plugin_name=plugin_name, rule=rule, start_time=start_time, end_time=end_time, limit=limit, offset=offset)
    return {"total": total, "alerts": alerts}


@app.get("/api/v1/plugins/alerts/history/stats")
def list_alert_history_stats(
    plugin_name: Optional[str] = None,
    rule: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
):
    return database.get_alert_history_stats(plugin_name=plugin_name, rule=rule, start_time=start_time, end_time=end_time)


@app.delete("/api/v1/plugins/alerts/history")
def delete_alert_history(
    plugin_name: Optional[str] = None,
    rule: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
):
    parsed_start_time = _validate_iso_time(start_time, "start_time")
    parsed_end_time = _validate_iso_time(end_time, "end_time")
    deleted_count = database.delete_alert_history(
        plugin_name=plugin_name,
        rule=rule,
        start_time=parsed_start_time,
        end_time=parsed_end_time,
    )
    logger.info(
        "Deleted alert history records: count=%s plugin_name=%s rule=%s start_time=%s end_time=%s",
        deleted_count,
        plugin_name,
        rule,
        parsed_start_time,
        parsed_end_time,
    )
    return {"deleted_count": deleted_count}


@app.get("/api/v1/plugins/alerts/history/export")
def export_alert_history(
    request: Request,
    plugin_name: Optional[str] = None,
    rule: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    format: str = "json",
):
    parsed_start_time = _validate_iso_time(start_time, "start_time")
    parsed_end_time = _validate_iso_time(end_time, "end_time")
    export_format = (format or "json").lower()
    if export_format not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="format 仅支持 json 或 csv")

    max_export_rows = 5000
    alerts, total = database.get_alert_history(
        plugin_name=plugin_name,
        rule=rule,
        start_time=parsed_start_time,
        end_time=parsed_end_time,
        limit=None,
    )
    if total > max_export_rows:
        raise HTTPException(status_code=400, detail="导出数据过多，请缩小时间范围后重试")

    logger.info(
        "Export alert history requested: format=%s total=%s plugin_name=%s rule=%s start_time=%s end_time=%s",
        export_format,
        total,
        plugin_name,
        rule,
        parsed_start_time,
        parsed_end_time,
    )

    requester = getattr(getattr(request, "client", None), "host", None) or "unknown"
    params_payload = {
        "plugin_name": plugin_name,
        "rule": rule,
        "start_time": parsed_start_time,
        "end_time": parsed_end_time,
        "format": export_format,
    }
    try:
        database.save_export_audit(json.dumps(params_payload, ensure_ascii=False), len(alerts), requester)
    except Exception as exc:
        logger.warning("Failed to save export audit log: %s", exc)

    if export_format == "json":
        return alerts

    buffer = StringIO()
    csv_writer = csv.writer(buffer)
    csv_writer.writerow(["alert_id", "plugin_name", "rule", "threshold", "actual", "triggered_at", "message_sent"])
    for alert in alerts:
        csv_writer.writerow(
            [
                alert.get("alert_id"),
                alert.get("plugin_name"),
                alert.get("rule"),
                alert.get("threshold"),
                alert.get("actual"),
                alert.get("triggered_at"),
                int(bool(alert.get("message_sent"))),
            ]
        )

    csv_content = buffer.getvalue().encode("utf-8-sig").decode("utf-8-sig")
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": 'attachment; filename="alerts_export.csv"'},
    )


@app.get("/api/v1/plugins/alerts/export/audit")
def list_export_audit(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    parsed_start_time = _validate_iso_time(start_time, "start_time")
    parsed_end_time = _validate_iso_time(end_time, "end_time")
    logs, total = database.get_export_audit_logs(
        start_time=parsed_start_time,
        end_time=parsed_end_time,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "logs": logs}


@app.post("/api/v1/{plugin_name}/tasks", response_model=TaskResponse)
def create_plugin_task(plugin_name: str, request: TaskCreateRequest, background_tasks: BackgroundTasks):
    task_id, created_at = task_manager.create_task(plugin_name, request.model_dump(exclude_none=True))
    background_tasks.add_task(task_manager.execute_plugin_task, task_id, plugin_name, request.model_dump(exclude_none=True))
    logger.info("Async task %s for plugin %s scheduled", task_id, plugin_name)
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=500, detail="Task creation failed")
    return TaskResponse(
        task_id=task["task_id"],
        status=task["status"],
        created_at=created_at,
        completed_at=task.get("completed_at"),
        result=task.get("result"),
        error=task.get("error"),
    )


@app.get("/api/v1/tasks")
def list_tasks(status: Optional[str] = None, plugin_name: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None, page: int = 1, page_size: Optional[int] = 20, sort_by: str = "created_at", order: str = "desc"):
    safe_page = max(1, page)
    safe_page_size = None if page_size is None else min(100, max(1, page_size))
    safe_sort_by = sort_by if sort_by in {"created_at", "completed_at", "status"} else "created_at"
    safe_order = order if order in {"asc", "desc"} else "desc"
    parsed_start_time = None
    parsed_end_time = None

    if start_time:
        try:
            datetime.fromisoformat(start_time)
            parsed_start_time = start_time
        except ValueError:
            logger.warning("Invalid start_time ignored: %s", start_time)

    if end_time:
        try:
            datetime.fromisoformat(end_time)
            parsed_end_time = end_time
        except ValueError:
            logger.warning("Invalid end_time ignored: %s", end_time)

    tasks, total = database.get_tasks(status=status, plugin_name=plugin_name, start_time=parsed_start_time, end_time=parsed_end_time, page=safe_page, page_size=safe_page_size, sort_by=safe_sort_by, order=safe_order)
    if safe_page_size is None:
        return {"tasks": tasks, "total": total}
    return {"tasks": tasks, "total": total, "page": safe_page, "page_size": safe_page_size}


@app.get("/api/v1/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(
        task_id=task["task_id"],
        status=task["status"],
        created_at=task["created_at"],
        completed_at=task.get("completed_at"),
        result=task.get("result"),
        error=task.get("error"),
    )


def _validate_iso_time(value: Optional[str], field_name: str) -> Optional[str]:
    if not value:
        return None
    try:
        datetime.fromisoformat(value)
        return value
    except ValueError:
        logger.warning("Invalid %s ignored: %s", field_name, value)
        return None


def _parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes", "on"}
    return False


def _parse_alert_thresholds(alert_thresholds: str) -> dict[str, float]:
    try:
        parsed = json.loads(alert_thresholds)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="alert_thresholds 格式不正确") from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="alert_thresholds 格式不正确")

    thresholds: dict[str, float] = {}
    for rule, threshold in parsed.items():
        if rule != "success_rate":
            logger.warning("Unsupported alert rule ignored: %s", rule)
            continue
        try:
            thresholds[rule] = float(threshold)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"alert_thresholds 中 {rule} 阈值不正确")
    return thresholds


def _apply_alerts_to_metric(metric: dict, thresholds: dict[str, float]) -> dict:
    updated = dict(metric)
    alerts = []
    success_rate_threshold = thresholds.get("success_rate")
    if success_rate_threshold is not None:
        actual = updated.get("success_rate")
        if actual is not None and actual < success_rate_threshold:
            alerts.append(
                {
                    "rule": "success_rate",
                    "threshold": success_rate_threshold,
                    "actual": actual,
                    "message": f"成功率低于阈值 {success_rate_threshold}",
                }
            )
    updated["alerts"] = alerts
    return updated


def _send_alerts_to_feishu(metrics_with_alerts: list[dict], alert_message_template: Optional[str]) -> None:
    if not settings.feishu_webhook_url and not (settings.feishu_app_id and settings.feishu_app_secret):
        logger.warning("未配置飞书 Webhook 或 App 凭证，跳过报警飞书推送")
        return

    alerts = []
    for metric in metrics_with_alerts:
        for alert in metric.get("alerts", []):
            alerts.append((metric, alert))

    if not alerts:
        return

    limit_minutes = settings.alert_frequency_limit_minutes
    messages = []
    for metric, alert in alerts:
        plugin = metric.get("plugin_name")
        rule = alert.get("rule")
        cache_key = f"{plugin}_{rule}"
        now_ts = time.time()
        last_sent_ts = _last_alert_sent.get(cache_key)
        if limit_minutes > 0 and last_sent_ts is not None and (now_ts - last_sent_ts) < limit_minutes * 60:
            logger.info("插件 %s 的 %s 报警在 %s 分钟内已发送过，本次跳过", plugin, rule, limit_minutes)
            continue

        messages.append(
            _render_alert_message(
                plugin_name=plugin,
                rule=rule,
                threshold=alert.get("threshold"),
                actual=alert.get("actual"),
                alert_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                template=alert_message_template,
            )
        )
        _last_alert_sent[cache_key] = now_ts

    if not messages:
        return

    message = "\n\n".join(messages)
    sent_ok = False
    try:
        sent_ok = FeishuClient(
            webhook_url=settings.feishu_webhook_url or None,
            secret=settings.feishu_secret or None,
        ).send_text(message)
        if sent_ok:
            logger.info("飞书报警推送成功")
        else:
            logger.error("飞书报警推送返回失败")
    except Exception as exc:
        logger.error("飞书报警推送失败: %s", exc)

    for metric, alert in alerts:
        try:
            database.save_alert_history(
                plugin_name=metric.get("plugin_name", ""),
                rule=alert.get("rule", ""),
                threshold=float(alert.get("threshold", 0)),
                actual=alert.get("actual"),
                message_sent=sent_ok,
            )
        except Exception as exc:
            logger.warning("保存报警历史失败: %s", exc)


def _render_alert_message(
    plugin_name: str,
    rule: str,
    threshold: float | int | str,
    actual: float | int | str | None,
    alert_time: str,
    template: Optional[str],
) -> str:
    if template is None or not template.strip():
        template = DEFAULT_ALERT_MESSAGE_TEMPLATE

    message = template
    replacements = {
        "{plugin_name}": str(plugin_name),
        "{rule}": str(rule),
        "{threshold}": str(threshold),
        "{actual}": str(actual),
        "{alert_time}": alert_time,
    }

    for placeholder, value in replacements.items():
        message = message.replace(placeholder, value)

    if "{" in message and "}" in message:
        logger.warning("报警模板中可能存在未识别变量，保留原样: %s", template)

    return message


def _convert_trend_to_csv(trend: list[dict], normalize: bool) -> str:
    buffer = StringIO()
    csv_writer = writer(buffer)

    if not trend:
        csv_writer.writerow(["bucket_date"])
        return buffer.getvalue()

    if "plugins" in trend[0]:
        plugins = sorted(trend[0]["plugins"].keys())
        columns = ["bucket_date"]
        for plugin in plugins:
            columns.extend([
                f"{plugin}_total_tasks",
                f"{plugin}_completed_tasks",
                f"{plugin}_failed_tasks",
                f"{plugin}_success_rate",
            ])
            if normalize:
                columns.append(f"{plugin}_normalized_total_tasks")
        csv_writer.writerow(columns)
        for item in trend:
            row = [item["bucket_date"]]
            for plugin in plugins:
                payload = item["plugins"].get(plugin, {})
                row.extend([
                    payload.get("total_tasks", 0),
                    payload.get("completed_tasks", 0),
                    payload.get("failed_tasks", 0),
                    payload.get("success_rate"),
                ])
                if normalize:
                    row.append(payload.get("normalized_total_tasks"))
            csv_writer.writerow(row)
    else:
        columns = ["bucket_date", "plugin_name", "total_tasks", "completed_tasks", "failed_tasks", "success_rate"]
        if normalize:
            columns.append("normalized_total_tasks")
        csv_writer.writerow(columns)
        for item in trend:
            row = [
                item.get("bucket_date"),
                item.get("plugin_name"),
                item.get("total_tasks", 0),
                item.get("completed_tasks", 0),
                item.get("failed_tasks", 0),
                item.get("success_rate"),
            ]
            if normalize:
                row.append(item.get("normalized_total_tasks"))
            csv_writer.writerow(row)

    return buffer.getvalue()
