"""
break_glass_notifications.py
=============================
Enterprise-grade real-time notification dispatch when break-glass is activated.

Notification chain (tried in order, all non-fatal):
  1. Slack — via configured Integration (Bot Token) or BREAK_GLASS_SLACK_WEBHOOK env var
  2. PagerDuty Events API v2 — via configured Integration or BREAK_GLASS_PAGERDUTY_KEY env var
  3. Microsoft Teams — via configured Integration or BREAK_GLASS_TEAMS_WEBHOOK env var
  4. Generic webhook — BREAK_GLASS_WEBHOOK_URL (POST JSON)
  5. CRITICAL log — always fires regardless of other channels

Every channel failure is caught and logged; a broken Slack config must never
prevent break-glass from succeeding.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("egap.break_glass")

_TIMEOUT = 8  # seconds per outbound call


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slack_blocks(actor: str, service: str, environment: str, command: str, reason: str) -> List[Dict]:
    """Rich Slack Block Kit payload for break-glass alert."""
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🚨 BREAK-GLASS ACTIVATED", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Actor*\n{actor or 'unknown'}"},
                {"type": "mrkdwn", "text": f"*Service*\n{service or 'unknown'}"},
                {"type": "mrkdwn", "text": f"*Environment*\n{environment or 'unknown'}"},
                {"type": "mrkdwn", "text": f"*Time*\n<!date^{int(time.time())}^{{date_time}}|now>"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Command*\n```{command[:300]}```"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Emergency Reason*\n{reason or '_(no reason provided)_'}"},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "AIOps Platform Control Plane · Break-glass bypass logged to audit trail."}
            ],
        },
    ]


def _teams_card(actor: str, service: str, environment: str, command: str, reason: str) -> Dict:
    """Teams Adaptive Card payload."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "🚨 BREAK-GLASS ACTIVATED",
                            "weight": "Bolder",
                            "size": "Large",
                            "color": "Attention",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Actor", "value": actor or "unknown"},
                                {"title": "Service", "value": service or "unknown"},
                                {"title": "Environment", "value": environment or "unknown"},
                                {"title": "Command", "value": command[:200]},
                                {"title": "Reason", "value": reason or "(no reason provided)"},
                            ],
                        },
                        {
                            "type": "TextBlock",
                            "text": "This action bypassed all policy restrictions. Review the audit trail immediately.",
                            "wrap": True,
                            "isSubtle": True,
                        },
                    ],
                },
            }
        ],
    }


def _pagerduty_event(actor: str, service: str, environment: str, command: str, reason: str, routing_key: str) -> Dict:
    return {
        "routing_key": routing_key,
        "event_action": "trigger",
        "dedup_key": f"break-glass:{actor}:{service}:{int(time.time() // 60)}",
        "payload": {
            "summary": f"[BREAK-GLASS] {actor} bypassed policy on {service} ({environment})",
            "severity": "critical",
            "source": "opsmitra-control-plane",
            "component": service or "unknown",
            "group": environment or "unknown",
            "class": "break-glass",
            "custom_details": {
                "actor": actor,
                "service": service,
                "environment": environment,
                "command": command[:500],
                "reason": reason,
            },
        },
    }


# ---------------------------------------------------------------------------
# Channel dispatchers
# ---------------------------------------------------------------------------

def _notify_slack_via_bot(token: str, channel: str, actor: str, service: str, environment: str, command: str, reason: str) -> bool:
    try:
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"channel": channel, "blocks": _slack_blocks(actor, service, environment, command, reason),
                  "text": f"BREAK-GLASS ACTIVATED by {actor} on {service} ({environment})"},
            timeout=_TIMEOUT,
        )
        payload = resp.json()
        if payload.get("ok"):
            logger.info("[BREAK-GLASS] Slack bot notification sent to channel %s", channel)
            return True
        logger.warning("[BREAK-GLASS] Slack bot post failed: %s", payload.get("error"))
        return False
    except Exception as exc:
        logger.warning("[BREAK-GLASS] Slack bot error: %s", exc)
        return False


def _notify_slack_via_webhook(webhook_url: str, actor: str, service: str, environment: str, command: str, reason: str) -> bool:
    try:
        resp = requests.post(
            webhook_url,
            json={"blocks": _slack_blocks(actor, service, environment, command, reason),
                  "text": f"BREAK-GLASS ACTIVATED by {actor} on {service} ({environment})"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            logger.info("[BREAK-GLASS] Slack webhook notification sent.")
            return True
        logger.warning("[BREAK-GLASS] Slack webhook HTTP %s", resp.status_code)
        return False
    except Exception as exc:
        logger.warning("[BREAK-GLASS] Slack webhook error: %s", exc)
        return False


def _notify_pagerduty(routing_key: str, actor: str, service: str, environment: str, command: str, reason: str) -> bool:
    try:
        resp = requests.post(
            "https://events.pagerduty.com/v2/enqueue",
            json=_pagerduty_event(actor, service, environment, command, reason, routing_key),
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code in (200, 202):
            logger.info("[BREAK-GLASS] PagerDuty event triggered.")
            return True
        logger.warning("[BREAK-GLASS] PagerDuty HTTP %s: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.warning("[BREAK-GLASS] PagerDuty error: %s", exc)
        return False


def _notify_teams(webhook_url: str, actor: str, service: str, environment: str, command: str, reason: str) -> bool:
    try:
        resp = requests.post(
            webhook_url,
            json=_teams_card(actor, service, environment, command, reason),
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            logger.info("[BREAK-GLASS] Teams notification sent.")
            return True
        logger.warning("[BREAK-GLASS] Teams HTTP %s", resp.status_code)
        return False
    except Exception as exc:
        logger.warning("[BREAK-GLASS] Teams error: %s", exc)
        return False


def _notify_generic_webhook(webhook_url: str, actor: str, service: str, environment: str, command: str, reason: str) -> bool:
    try:
        resp = requests.post(
            webhook_url,
            json={
                "event": "break_glass_activated",
                "actor": actor,
                "service": service,
                "environment": environment,
                "command": command[:500],
                "reason": reason,
                "timestamp": time.time(),
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code < 300:
            logger.info("[BREAK-GLASS] Generic webhook notification sent.")
            return True
        logger.warning("[BREAK-GLASS] Generic webhook HTTP %s", resp.status_code)
        return False
    except Exception as exc:
        logger.warning("[BREAK-GLASS] Generic webhook error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Integration-DB channel resolution
# ---------------------------------------------------------------------------

def _resolve_db_channels() -> Dict[str, Any]:
    """
    Resolve notification channels from configured Integration records.
    Returns dict with keys: slack_token, slack_channel, pagerduty_key, teams_url.
    Non-fatal — returns empty dict if DB is unavailable.
    """
    result: Dict[str, Any] = {}
    try:
        from genai.models import Integration
        from genai.integrations.vendors.common import credential_secret, credential_metadata

        slack_int = Integration.objects.filter(
            integration_type="slack", enabled=True, category="notifications"
        ).first()
        if slack_int:
            result["slack_token"] = credential_secret(slack_int)
            result["slack_channel"] = str(
                credential_metadata(slack_int).get("channel")
                or (slack_int.metadata_json or {}).get("break_glass_channel")
                or credential_metadata(slack_int).get("default_channel")
                or ""
            )

        pd_int = Integration.objects.filter(
            integration_type="pagerduty", enabled=True
        ).first()
        if pd_int:
            result["pagerduty_key"] = credential_secret(pd_int)

        teams_int = Integration.objects.filter(
            integration_type="teams", enabled=True, category="notifications"
        ).first()
        if teams_int:
            result["teams_url"] = teams_int.endpoint_url or ""

    except Exception as exc:
        logger.debug("[BREAK-GLASS] DB channel resolution error (non-fatal): %s", exc)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dispatch_break_glass_notifications(
    *,
    actor: str,
    command: str,
    service: str,
    environment: str,
    reason: str,
) -> Dict[str, Any]:
    """
    Fire all configured break-glass notification channels.

    Always emits CRITICAL log first (synchronous, zero dependencies).
    Then attempts each channel and records success/failure per channel.
    All channel failures are non-fatal.

    Returns a summary dict suitable for storing in audit records.
    """
    # 1. Always log at CRITICAL level — caught by any log aggregator
    logger.critical(
        "[BREAK-GLASS ACTIVATED] actor=%s service=%s environment=%s command=%s reason=%s",
        actor, service, environment, command[:120], reason or "(no reason provided)",
    )

    results: Dict[str, bool] = {}

    # Resolve channels from DB integrations
    db_channels = _resolve_db_channels()

    # 2. Slack — DB integration takes priority, then env var webhook
    slack_token = db_channels.get("slack_token") or ""
    slack_channel = db_channels.get("slack_channel") or ""
    slack_webhook = os.getenv("BREAK_GLASS_SLACK_WEBHOOK", "")

    if slack_token and slack_channel:
        results["slack_bot"] = _notify_slack_via_bot(slack_token, slack_channel, actor, service, environment, command, reason)
    elif slack_webhook:
        results["slack_webhook"] = _notify_slack_via_webhook(slack_webhook, actor, service, environment, command, reason)
    else:
        results["slack"] = False
        logger.debug("[BREAK-GLASS] No Slack channel configured.")

    # 3. PagerDuty — DB integration or env var routing key
    pd_key = db_channels.get("pagerduty_key") or os.getenv("BREAK_GLASS_PAGERDUTY_KEY", "")
    if pd_key:
        results["pagerduty"] = _notify_pagerduty(pd_key, actor, service, environment, command, reason)
    else:
        results["pagerduty"] = False
        logger.debug("[BREAK-GLASS] No PagerDuty key configured.")

    # 4. Teams — DB integration or env var webhook
    teams_url = db_channels.get("teams_url") or os.getenv("BREAK_GLASS_TEAMS_WEBHOOK", "")
    if teams_url:
        results["teams"] = _notify_teams(teams_url, actor, service, environment, command, reason)
    else:
        results["teams"] = False
        logger.debug("[BREAK-GLASS] No Teams webhook configured.")

    # 5. Generic webhook fallback
    generic_webhook = os.getenv("BREAK_GLASS_WEBHOOK_URL", "")
    if generic_webhook:
        results["generic_webhook"] = _notify_generic_webhook(generic_webhook, actor, service, environment, command, reason)

    notified = any(v for v in results.values())
    if not notified:
        logger.warning(
            "[BREAK-GLASS] No notification channels delivered. "
            "Configure BREAK_GLASS_SLACK_WEBHOOK, BREAK_GLASS_PAGERDUTY_KEY, or BREAK_GLASS_TEAMS_WEBHOOK."
        )

    return {
        "channels": results,
        "any_delivered": notified,
        "actor": actor,
        "service": service,
        "environment": environment,
    }
