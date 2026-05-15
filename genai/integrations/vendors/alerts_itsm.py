import datetime
from typing import List

import requests

from ..base import BaseAdapter, BaseAlertsAdapter, NormalizedAlertResult
from ..registry import IntegrationRegistry
from .common import credential_metadata, credential_secret, parse_timestamp


class AlertmanagerAdapter(BaseAlertsAdapter):
    def test_connection(self) -> bool:
        try:
            base = self.integration.endpoint_url.rstrip("/")
            response = requests.get(f"{base}/-/ready", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def fetch_alert_state(self) -> List[NormalizedAlertResult]:
        base = self.integration.endpoint_url.rstrip("/")
        response = requests.get(f"{base}/api/v2/alerts", timeout=10)
        response.raise_for_status()
        results: List[NormalizedAlertResult] = []
        for item in response.json() or []:
            labels = {str(k): str(v) for k, v in (item.get("labels") or {}).items()}
            annotations = item.get("annotations") or {}
            results.append(
                NormalizedAlertResult(
                    alert_name=str(labels.get("alertname") or "AlertmanagerAlert"),
                    status=str((item.get("status") or {}).get("state") or item.get("status") or "unknown"),
                    severity=str(labels.get("severity") or "warning"),
                    description=str(annotations.get("summary") or annotations.get("description") or ""),
                    starts_at=parse_timestamp(item.get("startsAt")),
                    labels=labels,
                )
            )
        return results


class PagerDutyAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            response = requests.get(
                f"{self.integration.endpoint_url.rstrip('/') or 'https://api.pagerduty.com'}/users/me",
                headers={"Authorization": f"Token token={credential_secret(self.integration)}", "Accept": "application/vnd.pagerduty+json;version=2"},
                timeout=8,
            )
            return response.status_code == 200
        except Exception:
            return False

    def create_incident_ticket(self, incident):
        metadata = credential_metadata(self.integration)
        service_id = str(metadata.get("service_id") or "")
        escalation_policy_id = str(metadata.get("escalation_policy_id") or "")
        body = {
            "incident": {
                "type": "incident",
                "title": f"{incident.incident_number or incident.incident_key} {incident.title}",
                "service": {"id": service_id, "type": "service_reference"} if service_id else None,
                "escalation_policy": {"id": escalation_policy_id, "type": "escalation_policy_reference"} if escalation_policy_id else None,
                "urgency": "high" if incident.severity in {"critical", "high"} else "low",
                "body": {"type": "incident_body", "details": incident.summary or incident.reasoning or incident.title},
            }
        }
        body["incident"] = {key: value for key, value in body["incident"].items() if value}
        response = requests.post(
            f"{self.integration.endpoint_url.rstrip('/') or 'https://api.pagerduty.com'}/incidents",
            headers={
                "Authorization": f"Token token={credential_secret(self.integration)}",
                "Accept": "application/vnd.pagerduty+json;version=2",
                "Content-Type": "application/json",
                "From": str(metadata.get("from_email") or "opsmitra@example.com"),
            },
            json=body,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json().get("incident") or {}
        return {
            "external_id": payload.get("id") or "",
            "external_key": payload.get("incident_number") or payload.get("id") or "",
            "external_url": payload.get("html_url") or "",
            "message": "PagerDuty incident created.",
            "raw": payload,
        }


class ServiceNowAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            metadata = credential_metadata(self.integration)
            auth = (str(metadata.get("username") or ""), credential_secret(self.integration)) if metadata.get("username") else None
            headers = {"Authorization": f"Bearer {credential_secret(self.integration)}"} if not auth and credential_secret(self.integration) else {}
            response = requests.get(
                f"{self.integration.endpoint_url.rstrip('/')}/api/now/table/incident",
                params={"sysparm_limit": 1},
                auth=auth,
                headers=headers,
                timeout=8,
            )
            return response.status_code == 200
        except Exception:
            return False

    def create_incident_ticket(self, incident):
        metadata = credential_metadata(self.integration)
        auth = (str(metadata.get("username") or ""), credential_secret(self.integration)) if metadata.get("username") else None
        headers = {"Authorization": f"Bearer {credential_secret(self.integration)}"} if not auth and credential_secret(self.integration) else {}
        body = {
            "short_description": f"{incident.incident_number or incident.incident_key} {incident.title}",
            "description": incident.summary or incident.reasoning or incident.title,
            "impact": str(metadata.get("impact") or ("1" if incident.severity == "critical" else "2")),
            "urgency": str(metadata.get("urgency") or ("1" if incident.severity in {"critical", "high"} else "2")),
            "category": str(metadata.get("category") or "software"),
            "cmdb_ci": incident.primary_service or "",
        }
        response = requests.post(
            f"{self.integration.endpoint_url.rstrip('/')}/api/now/table/incident",
            auth=auth,
            headers={**headers, "Content-Type": "application/json", "Accept": "application/json"},
            json=body,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json().get("result") or {}
        number = str(payload.get("number") or payload.get("sys_id") or "")
        instance = self.integration.endpoint_url.rstrip("/")
        return {
            "external_id": payload.get("sys_id") or "",
            "external_key": number,
            "external_url": f"{instance}/nav_to.do?uri=incident.do?sys_id={payload.get('sys_id')}" if payload.get("sys_id") else "",
            "message": "ServiceNow incident created.",
            "raw": payload,
        }


class JiraAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            metadata = credential_metadata(self.integration)
            email = str(metadata.get("email") or metadata.get("username") or "")
            auth = (email, credential_secret(self.integration)) if email and credential_secret(self.integration) else None
            headers = {"Authorization": f"Bearer {credential_secret(self.integration)}"} if not auth and credential_secret(self.integration) else {}
            response = requests.get(
                f"{self.integration.endpoint_url.rstrip('/')}/rest/api/3/myself",
                auth=auth,
                headers=headers,
                timeout=8,
            )
            return response.status_code == 200
        except Exception:
            return False

    def create_incident_ticket(self, incident):
        metadata = credential_metadata(self.integration)
        email = str(metadata.get("email") or metadata.get("username") or "")
        auth = (email, credential_secret(self.integration)) if email and credential_secret(self.integration) else None
        headers = {"Authorization": f"Bearer {credential_secret(self.integration)}"} if not auth and credential_secret(self.integration) else {}
        project_key = str(metadata.get("project_key") or "")
        issue_type = str(metadata.get("issue_type") or "Bug")
        body = {
            "fields": {
                "project": {"key": project_key},
                "summary": f"{incident.incident_number or incident.incident_key} {incident.title}",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": incident.summary or incident.reasoning or incident.title}],
                        }
                    ],
                },
                "issuetype": {"name": issue_type},
            }
        }
        response = requests.post(
            f"{self.integration.endpoint_url.rstrip('/')}/rest/api/3/issue",
            auth=auth,
            headers={**headers, "Content-Type": "application/json", "Accept": "application/json"},
            json=body,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        key = str(payload.get("key") or payload.get("id") or "")
        return {
            "external_id": payload.get("id") or "",
            "external_key": key,
            "external_url": f"{self.integration.endpoint_url.rstrip('/')}/browse/{key}" if key else "",
            "message": "Jira issue created.",
            "raw": payload,
        }


class OpsgenieAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            response = requests.get(
                f"{self.integration.endpoint_url.rstrip('/') or 'https://api.opsgenie.com'}/v2/account",
                headers={"Authorization": f"GenieKey {credential_secret(self.integration)}"},
                timeout=8,
            )
            return response.status_code == 200
        except Exception:
            return False

    def create_incident_ticket(self, incident):
        response = requests.post(
            f"{self.integration.endpoint_url.rstrip('/') or 'https://api.opsgenie.com'}/v2/alerts",
            headers={"Authorization": f"GenieKey {credential_secret(self.integration)}", "Content-Type": "application/json"},
            json={
                "message": f"{incident.incident_number or incident.incident_key} {incident.title}",
                "description": incident.summary or incident.reasoning or incident.title,
                "priority": "P1" if incident.severity == "critical" else "P2",
                "alias": str(incident.incident_key),
                "tags": ["opsmitra", incident.application or "application"],
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        request_id = str(payload.get("requestId") or "")
        return {"external_id": request_id, "external_key": request_id, "external_url": "", "message": "Opsgenie alert created.", "raw": payload}


class SlackAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            response = requests.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {credential_secret(self.integration)}"},
                timeout=8,
            )
            payload = response.json()
            return response.status_code == 200 and bool(payload.get("ok"))
        except Exception:
            return False

    def create_incident_ticket(self, incident):
        metadata = credential_metadata(self.integration)
        channel = str(metadata.get("channel") or "")
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {credential_secret(self.integration)}", "Content-Type": "application/json"},
            json={
                "channel": channel,
                "text": f"{incident.incident_number or incident.incident_key} {incident.title}\n{incident.summary or incident.reasoning or ''}",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(str(payload.get("error") or "slack_post_failed"))
        return {
            "external_id": str(payload.get("ts") or ""),
            "external_key": str(payload.get("channel") or channel),
            "external_url": "",
            "message": "Slack notification posted.",
            "raw": payload,
        }


class TeamsAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        return bool(self.integration.endpoint_url and self.integration.endpoint_url.startswith("https://"))

    def create_incident_ticket(self, incident):
        response = requests.post(
            self.integration.endpoint_url,
            json={
                "text": f"**{incident.incident_number or incident.incident_key} {incident.title}**\n\n{incident.summary or incident.reasoning or ''}"
            },
            timeout=15,
        )
        response.raise_for_status()
        return {
            "external_id": str(incident.incident_key),
            "external_key": "teams-notification",
            "external_url": "",
            "message": "Microsoft Teams notification posted.",
            "raw": {"status_code": response.status_code},
        }


IntegrationRegistry.register("alertmanager", AlertmanagerAdapter)
IntegrationRegistry.register("pagerduty", PagerDutyAdapter)
IntegrationRegistry.register("servicenow", ServiceNowAdapter)
IntegrationRegistry.register("jira", JiraAdapter)
IntegrationRegistry.register("opsgenie", OpsgenieAdapter)
IntegrationRegistry.register("slack", SlackAdapter)
IntegrationRegistry.register("teams", TeamsAdapter)
