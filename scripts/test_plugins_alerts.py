import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

BASE_URL = "http://localhost:8000"


def fetch(params=None):
    response = requests.get(f"{BASE_URL}/api/v1/plugins/metrics", params=params or {}, timeout=10)
    return response


if __name__ == "__main__":
    multi_rules_response = fetch({"alert_thresholds": '{"success_rate":0.8,"failed_tasks":0,"total_tasks":0}'})
    multi_rules_response.raise_for_status()
    multi_rules_data = multi_rules_response.json()
    print("multi rules data:", multi_rules_data)
    for plugin in multi_rules_data.get("plugins", []):
        if plugin["plugin_name"] == "email":
            assert any(alert["rule"] == "success_rate" for alert in plugin["alerts"])
            assert any(alert["rule"] == "failed_tasks" for alert in plugin["alerts"])

    single_rule_response = fetch({"alert_thresholds": '{"success_rate":0.8}'})
    single_rule_response.raise_for_status()
    single_rule_data = single_rule_response.json()
    print("single rule data:", single_rule_data)
    for plugin in single_rule_data.get("plugins", []):
        assert all(alert["rule"] == "success_rate" for alert in plugin["alerts"])

    with patch("app.main.FeishuClient.send_text", return_value=True) as mock_send:
        push_response = fetch({"alert_thresholds": '{"success_rate":0.8,"failed_tasks":0}', "send_feishu": "true"})
        push_response.raise_for_status()
        push_data = push_response.json()
        print("push data:", push_data)
        if any(plugin.get("alerts") for plugin in push_data.get("plugins", [])):
            assert mock_send.called
            sent_message = mock_send.call_args[0][0]
            assert "规则: success_rate" in sent_message or "规则: failed_tasks" in sent_message

    with patch("app.main.FeishuClient.send_text", return_value=True) as mock_send:
        template_response = fetch({"alert_thresholds": '{"success_rate":0.8,"failed_tasks":0}', "send_feishu": "true", "alert_message_template": "{plugin_name}-{rule}-{threshold}-{actual}-{alert_time}"})
        template_response.raise_for_status()
        template_data = template_response.json()
        print("template data:", template_data)
        if any(plugin.get("alerts") for plugin in template_data.get("plugins", [])):
            assert mock_send.called
            sent_message = mock_send.call_args[0][0]
            assert "email-" in sent_message

    print("plugin multi-rule alert validation passed")
