import json
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

REQUIRED_OUTPUT_FIELDS = (
    "customer_intent",
    "has_followup",
    "next_followup_time",
    "urgency",
    "brief_summary",
)


class DifyClient:
    def __init__(self, api_url: str, api_key: str) -> None:
        if not api_url or not api_key:
            raise ValueError("DifyClient requires non-empty api_url and api_key")
        self.api_url = api_url
        self.api_key = api_key

    def analyze(self, text: str) -> dict[str, Any]:
        # Dify workflow input limit (email_text < 9999 chars)
        email_text = text[:9900] if len(text) > 9900 else text
        payload = {
            "inputs": {"email_text": email_text},
            "response_mode": "blocking",
            "user": "agent-workflow-plugin-service",
        }
        response = requests.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        if not response.ok:
            raise RuntimeError(
                f"Dify API error {response.status_code}: {response.text[:500]}"
            )
        raw = response.json()
        return self._parse_workflow_response(raw)

    def _parse_workflow_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Extract structured fields from Dify workflow blocking response."""
        outputs = self._extract_outputs(raw)
        if not outputs:
            logger.warning("Dify response has no outputs, raw keys=%s", list(raw.keys()))
            return {"_raw": raw}

        result: dict[str, Any] = {}
        for field in REQUIRED_OUTPUT_FIELDS:
            if field in outputs:
                result[field] = outputs[field]

        # Some workflows nest JSON string in a single output key
        if len(result) < len(REQUIRED_OUTPUT_FIELDS):
            for value in outputs.values():
                if isinstance(value, str):
                    try:
                        nested = json.loads(value)
                        if isinstance(nested, dict):
                            for field in REQUIRED_OUTPUT_FIELDS:
                                if field in nested and field not in result:
                                    result[field] = nested[field]
                    except json.JSONDecodeError:
                        pass
                elif isinstance(value, dict):
                    for field in REQUIRED_OUTPUT_FIELDS:
                        if field in value and field not in result:
                            result[field] = value[field]

        if result:
            return result
        return {"_raw": raw, "outputs": outputs}

    @staticmethod
    def _extract_outputs(raw: dict[str, Any]) -> dict[str, Any]:
        data = raw.get("data")
        if isinstance(data, dict):
            outputs = data.get("outputs")
            if isinstance(outputs, dict):
                return outputs
            if data.get("status") == "failed":
                raise RuntimeError(f"Dify workflow failed: {data.get('error') or data}")
        outputs = raw.get("outputs")
        if isinstance(outputs, dict):
            return outputs
        return {}
