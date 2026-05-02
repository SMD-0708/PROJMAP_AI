"""Webhook推送模块

功能：脉络更新时主动推送变更摘要到协作平台。
设计原则：只推送骨架/变更摘要，不上传完整代码，保护用户隐私。
"""

import json
import hashlib
import hmac
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Callable
import urllib.request
import urllib.error
from enum import Enum


class WebhookEvent(Enum):
    PROJMAP_CREATED = "projmap.created"
    PROJMAP_UPDATED = "projmap.updated"
    NODE_STATUS_CHANGED = "node.status_changed"
    DECISION_ADDED = "decision.added"
    NODE_ABANDONED = "node.abandoned"
    NODE_REVIVED = "node.revived"
    TECH_TAG_ADDED = "tech_tag.added"
    INFERENCE_CONFIRMED = "inference.confirmed"


@dataclass
class WebhookPayload:
    event: str
    timestamp: str
    project_name: str
    project_root: str
    summary: dict
    changes: list[dict]
    signature: Optional[str] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class WebhookConfig:
    url: str
    secret: Optional[str] = None
    events: list[str] = field(default_factory=lambda: [e.value for e in WebhookEvent])
    enabled: bool = True
    timeout: int = 10
    retries: int = 3


class WebhookManager:
    """Webhook管理器"""
    
    def __init__(self, config: Optional[WebhookConfig] = None):
        self.config = config
        self._listeners: list[Callable] = []
    
    def add_listener(self, listener: Callable):
        self._listeners.append(listener)
    
    def remove_listener(self, listener: Callable):
        if listener in self._listeners:
            self._listeners.remove(listener)
    
    def emit(self, event: WebhookEvent, projmap_data: dict, changes: Optional[list[dict]] = None):
        if not self.config or not self.config.enabled:
            return
        
        if event.value not in self.config.events:
            return
        
        payload = self._build_payload(event, projmap_data, changes or [])
        
        if self.config.secret:
            payload.signature = self._sign_payload(payload)
        
        self._send_webhook(payload)
        
        for listener in self._listeners:
            try:
                listener(event, payload)
            except Exception:
                pass
    
    def _build_payload(self, event: WebhookEvent, projmap_data: dict, changes: list[dict]) -> WebhookPayload:
        metadata = projmap_data.get("metadata", {})
        
        summary = {
            "total_nodes": len(projmap_data.get("nodes", [])),
            "total_edges": len(projmap_data.get("edges", [])),
            "total_decisions": len(projmap_data.get("decisions", [])),
            "active_main": projmap_data.get("active_state", {}).get("active_main"),
            "active_branches_count": len(projmap_data.get("active_state", {}).get("active_branches", [])),
        }
        
        return WebhookPayload(
            event=event.value,
            timestamp=datetime.now().isoformat(),
            project_name=metadata.get("project_name", "Unknown"),
            project_root=metadata.get("project_root", ""),
            summary=summary,
            changes=self._sanitize_changes(changes),
        )
    
    def _sanitize_changes(self, changes: list[dict]) -> list[dict]:
        sanitized = []
        for change in changes:
            sanitized_change = {
                "type": change.get("type"),
                "node_id": change.get("node_id"),
                "node_name": change.get("node_name"),
                "file_path": change.get("file_path"),
            }
            
            if "reason" in change:
                sanitized_change["reason"] = change["reason"][:200]
            
            if "decision_id" in change:
                sanitized_change["decision_id"] = change["decision_id"]
            
            sanitized.append(sanitized_change)
        
        return sanitized
    
    def _sign_payload(self, payload: WebhookPayload) -> str:
        message = payload.to_json().encode("utf-8")
        secret = self.config.secret.encode("utf-8")
        signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
        return f"sha256={signature}"
    
    def _send_webhook(self, payload: WebhookPayload):
        if not self.config or not self.config.url:
            return
        
        headers = {
            "Content-Type": "application/json",
            "X-ProjMap-Event": payload.event,
            "X-ProjMap-Timestamp": payload.timestamp,
        }
        
        if payload.signature:
            headers["X-ProjMap-Signature"] = payload.signature
        
        data = payload.to_json().encode("utf-8")
        req = urllib.request.Request(
            self.config.url,
            data=data,
            headers=headers,
            method="POST",
        )
        
        for attempt in range(self.config.retries):
            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                    if 200 <= response.status < 300:
                        return
            except urllib.error.URLError:
                if attempt == self.config.retries - 1:
                    raise
            except Exception:
                if attempt == self.config.retries - 1:
                    raise


class WebhookIntegration:
    """Webhook集成工具类"""
    
    @staticmethod
    def create_github_webhook_config(repo_url: str, secret: str) -> WebhookConfig:
        return WebhookConfig(
            url=f"{repo_url}/hooks/projmap",
            secret=secret,
            events=[
                WebhookEvent.PROJMAP_UPDATED.value,
                WebhookEvent.NODE_STATUS_CHANGED.value,
                WebhookEvent.DECISION_ADDED.value,
            ],
        )
    
    @staticmethod
    def create_slack_webhook_config(webhook_url: str) -> WebhookConfig:
        return WebhookConfig(
            url=webhook_url,
            events=[
                WebhookEvent.NODE_ABANDONED.value,
                WebhookEvent.DECISION_ADDED.value,
            ],
        )
    
    @staticmethod
    def create_discord_webhook_config(webhook_url: str) -> WebhookConfig:
        return WebhookConfig(
            url=webhook_url,
            events=[
                WebhookEvent.NODE_ABANDONED.value,
                WebhookEvent.NODE_REVIVED.value,
            ],
        )
    
    @staticmethod
    def format_for_slack(payload: WebhookPayload) -> dict:
        color_map = {
            "projmap.created": "#36a64f",
            "projmap.updated": "#1f6feb",
            "node.status_changed": "#9e6a03",
            "decision.added": "#58a6ff",
            "node.abandoned": "#f85149",
            "node.revived": "#238636",
        }
        
        return {
            "attachments": [
                {
                    "color": color_map.get(payload.event, "#808080"),
                    "title": f"ProjMap: {payload.event}",
                    "fields": [
                        {"title": "项目", "value": payload.project_name, "short": True},
                        {"title": "时间", "value": payload.timestamp, "short": True},
                        {"title": "节点数", "value": str(payload.summary.get("total_nodes", 0)), "short": True},
                        {"title": "决策数", "value": str(payload.summary.get("total_decisions", 0)), "short": True},
                    ],
                    "footer": "ProjMap",
                }
            ]
        }
    
    @staticmethod
    def format_for_discord(payload: WebhookPayload) -> dict:
        return {
            "embeds": [
                {
                    "title": f"ProjMap Update: {payload.event}",
                    "description": f"Project: **{payload.project_name}**",
                    "fields": [
                        {"name": "Nodes", "value": str(payload.summary.get("total_nodes", 0)), "inline": True},
                        {"name": "Decisions", "value": str(payload.summary.get("total_decisions", 0)), "inline": True},
                    ],
                    "timestamp": payload.timestamp,
                }
            ]
        }


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    expected_sig = f"sha256={expected}"
    return hmac.compare_digest(signature, expected_sig)
