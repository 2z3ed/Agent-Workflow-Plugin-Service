import logging
from typing import Any

from app.plugins.base import Plugin

logger = logging.getLogger(__name__)

# 固定演示数据：近 7 天单广告活动
_CAMPAIGN_NAME = "SP-主力推广-无线耳机"
_OVERALL_METRICS = {
    "impressions": 12_500,
    "clicks": 380,
    "spend": 342.50,
    "sales": 1250.00,
}

_KEYWORD_ROWS: list[dict[str, Any]] = [
    {
        "keyword": "wireless earbuds",
        "impressions": 5200,
        "clicks": 156,
        "spend": 142.30,
        "sales": 648.00,
        "orders": 12,
    },
    {
        "keyword": "bluetooth earphones",
        "impressions": 4100,
        "clicks": 98,
        "spend": 118.50,
        "sales": 338.00,
        "orders": 6,
    },
    {
        "keyword": "noise cancelling headphones",
        "impressions": 1800,
        "clicks": 12,
        "spend": 45.20,
        "sales": 0.0,
        "orders": 0,
    },
    {
        "keyword": "free shipping earbuds",
        "impressions": 1400,
        "clicks": 114,
        "spend": 36.50,
        "sales": 0.0,
        "orders": 0,
    },
]


def _pct(value: float) -> str:
    return f"{value:.1f}%"


def _compute_keyword_metrics(row: dict[str, Any]) -> dict[str, Any]:
    impressions = row["impressions"]
    clicks = row["clicks"]
    spend = row["spend"]
    sales = row["sales"]
    orders = row["orders"]

    ctr = (clicks / impressions * 100) if impressions else 0.0
    acos = (spend / sales * 100) if sales > 0 else None
    cvr = (orders / clicks * 100) if clicks else 0.0

    return {
        **row,
        "ctr": ctr,
        "acos": acos,
        "cvr": cvr,
    }


def _suggest_for_keyword(kw: dict[str, Any]) -> str:
    parts: list[str] = []
    acos = kw.get("acos")
    ctr = kw["ctr"]
    orders = kw["orders"]
    sales = kw["sales"]

    if orders == 0 or sales <= 0:
        parts.append("❌ 无转化，建议添加为否定关键词")
    elif acos is not None and acos > 30:
        parts.append(f"⚠️ ACOS {_pct(acos)} 高于阈值，建议降低出价 15% 或暂停投放")
    elif acos is not None and acos < 20 and orders >= 2:
        parts.append(f"✅ ACOS {_pct(acos)} 表现良好，建议提高出价 10%")

    if ctr < 1.0:
        parts.append(f"CTR {_pct(ctr)} 偏低，建议优化创意或调整匹配方式")

    if not parts:
        parts.append("📊 指标正常，建议维持当前出价并持续观察")

    return "；".join(parts)


def _build_overall_metrics() -> dict[str, Any]:
    m = _OVERALL_METRICS
    impressions = m["impressions"]
    clicks = m["clicks"]
    spend = m["spend"]
    sales = m["sales"]
    ctr = clicks / impressions * 100 if impressions else 0.0
    acos = spend / sales * 100 if sales > 0 else 0.0
    roas = sales / spend if spend > 0 else 0.0
    return {
        "campaign": _CAMPAIGN_NAME,
        "period_days": 7,
        "impressions": impressions,
        "clicks": clicks,
        "spend": spend,
        "sales": sales,
        "ctr": ctr,
        "acos": acos,
        "roas": roas,
    }


def _format_report(overall: dict[str, Any], keywords: list[dict[str, Any]]) -> str:
    lines = [
        f"📊 广告数据报告（近{overall['period_days']}天）",
        f"活动：{overall['campaign']}",
        "",
        "整体指标：",
        f"- 曝光：{overall['impressions']:,}",
        f"- 点击：{overall['clicks']:,} (CTR {_pct(overall['ctr'])})",
        f"- 花费：${overall['spend']:,.2f}",
        f"- 销售额：${overall['sales']:,.2f}",
        f"- ACOS：{_pct(overall['acos'])}",
        f"- ROAS：{overall['roas']:.2f}",
        "",
        "关键词优化建议：",
    ]

    for kw in keywords:
        acos_text = _pct(kw["acos"]) if kw["acos"] is not None else "—"
        lines.append(
            f"- 「{kw['keyword']}」：曝光 {kw['impressions']:,} | "
            f"点击 {kw['clicks']} (CTR {_pct(kw['ctr'])}) | "
            f"花费 ${kw['spend']:.2f} | ACOS {acos_text} → {kw['suggestion']}"
        )

    lines.append("")
    lines.append("— 以上为系统自动分析建议，请结合业务目标调整后执行。")
    return "\n".join(lines)


class AdOptimizerPlugin(Plugin):
    name = "ad"
    description = "生成模拟广告数据并通过规则引擎输出优化建议"
    category = "business"
    docs = """
# 广告监控与优化插件

针对飞书群指令「广告报告」或「广告优化」，生成近 7 天模拟广告指标与关键词优化建议。

## 输入参数
- chat_id: 飞书群 chat_id（可选）

## 输出
- report: 纯文本报告（发飞书）
- metrics: 整体指标
- keywords: 关键词明细及建议
"""

    def execute(self, task_id: str, **params) -> dict:
        chat_id = params.get("chat_id")
        logger.info("Ad plugin task %s chat_id=%s", task_id, chat_id)

        overall = _build_overall_metrics()
        keyword_results: list[dict[str, Any]] = []

        for row in _KEYWORD_ROWS:
            kw = _compute_keyword_metrics(row)
            kw["suggestion"] = _suggest_for_keyword(kw)
            keyword_results.append(kw)

        report = _format_report(overall, keyword_results)

        return {
            "chat_id": chat_id,
            "metrics": overall,
            "keywords": [
                {
                    "keyword": k["keyword"],
                    "impressions": k["impressions"],
                    "clicks": k["clicks"],
                    "ctr": round(k["ctr"], 2),
                    "spend": k["spend"],
                    "sales": k["sales"],
                    "acos": round(k["acos"], 2) if k["acos"] is not None else None,
                    "orders": k["orders"],
                    "suggestion": k["suggestion"],
                }
                for k in keyword_results
            ],
            "report": report,
            "task_id": task_id,
        }
