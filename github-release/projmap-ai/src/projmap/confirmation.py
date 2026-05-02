"""待确认标注模块

核心功能：
1. AI不确定的内容明确标注
2. 用户可以确认、修正或忽略
3. 提供判定规则和视觉呈现标准

判定规则：
- AI置信度低于阈值（默认0.7）
- 多个可能的功能标签
- 无法从骨架确定关系
- 冷启动推断的节点
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum

from projmap.models import ProjMap, Node, InferenceSource


class ConfirmationStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    IGNORED = "ignored"


class UncertaintyType(Enum):
    LOW_CONFIDENCE = "low_confidence"
    MULTIPLE_TAGS = "multiple_tags"
    UNKNOWN_RELATION = "unknown_relation"
    COLD_START = "cold_start"
    MISSING_CONTEXT = "missing_context"
    CONFLICTING_INFO = "conflicting_info"


@dataclass
class ConfirmationItem:
    item_id: str
    node_id: str
    uncertainty_type: UncertaintyType
    field_name: str
    suggested_value: Any
    alternatives: list[Any] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    status: ConfirmationStatus = ConfirmationStatus.PENDING
    user_correction: Optional[Any] = None
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None


@dataclass
class ConfirmationSession:
    session_id: str
    created_at: datetime
    items: list[ConfirmationItem] = field(default_factory=list)
    total_items: int = 0
    confirmed_count: int = 0
    corrected_count: int = 0
    ignored_count: int = 0


CONFIRMATION_THRESHOLDS = {
    "confidence_low": 0.7,
    "confidence_very_low": 0.5,
    "max_alternatives": 3,
    "min_function_tags": 1,
    "max_function_tags": 5,
}


class UncertaintyDetector:
    """不确定性检测器"""
    
    def __init__(self, thresholds: Optional[dict] = None):
        self.thresholds = thresholds or CONFIRMATION_THRESHOLDS
    
    def detect(self, node: Node) -> list[ConfirmationItem]:
        items = []
        
        if node.confidence is not None and node.confidence < self.thresholds["confidence_low"]:
            items.append(self._create_low_confidence_item(node))
        
        if node.function_tags and len(node.function_tags) > self.thresholds["max_function_tags"]:
            items.append(self._create_multiple_tags_item(node))
        
        if not node.function_tags:
            items.append(self._create_missing_tags_item(node))
        
        if node.inferred_by and node.inferred_by != InferenceSource.MANUAL:
            items.append(self._create_cold_start_item(node))
        
        if node.tech_tags:
            conflicting = self._detect_conflicting_tags(node.tech_tags)
            if conflicting:
                items.append(self._create_conflict_item(node, conflicting))
        
        return items
    
    def _create_low_confidence_item(self, node: Node) -> ConfirmationItem:
        return ConfirmationItem(
            item_id=f"{node.id}_low_confidence",
            node_id=node.id,
            uncertainty_type=UncertaintyType.LOW_CONFIDENCE,
            field_name="all",
            suggested_value={
                "function_tags": node.function_tags,
                "description": node.description,
            },
            confidence=node.confidence or 0.0,
            reasoning=f"AI推断置信度({node.confidence:.2f})低于阈值({self.thresholds['confidence_low']})",
        )
    
    def _create_multiple_tags_item(self, node: Node) -> ConfirmationItem:
        return ConfirmationItem(
            item_id=f"{node.id}_multiple_tags",
            node_id=node.id,
            uncertainty_type=UncertaintyType.MULTIPLE_TAGS,
            field_name="function_tags",
            suggested_value=node.function_tags[:self.thresholds["max_function_tags"]],
            alternatives=node.function_tags[self.thresholds["max_function_tags"]:],
            confidence=0.6,
            reasoning=f"检测到{len(node.function_tags)}个功能标签，超过建议数量{self.thresholds['max_function_tags']}",
        )
    
    def _create_missing_tags_item(self, node: Node) -> ConfirmationItem:
        return ConfirmationItem(
            item_id=f"{node.id}_missing_tags",
            node_id=node.id,
            uncertainty_type=UncertaintyType.MISSING_CONTEXT,
            field_name="function_tags",
            suggested_value=["utility"],
            alternatives=["data_processing", "configuration", "unknown"],
            confidence=0.3,
            reasoning="未能推断出功能标签，请手动确认",
        )
    
    def _create_cold_start_item(self, node: Node) -> ConfirmationItem:
        inference_names = {
            InferenceSource.FILE_NAME: "文件名推断",
            InferenceSource.IMPORT_ANALYSIS: "导入分析",
            InferenceSource.SKELETON: "骨架分析",
            InferenceSource.CODE_PATTERN: "代码模式",
            InferenceSource.UNKNOWN: "未知来源",
        }
        
        return ConfirmationItem(
            item_id=f"{node.id}_cold_start",
            node_id=node.id,
            uncertainty_type=UncertaintyType.COLD_START,
            field_name="all",
            suggested_value={
                "function_tags": node.function_tags,
                "description": node.description,
            },
            confidence=node.confidence or 0.5,
            reasoning=f"此节点通过{inference_names.get(node.inferred_by, '自动推断')}生成，建议确认",
        )
    
    def _detect_conflicting_tags(self, tech_tags: list) -> list:
        conflicts = []
        
        conflict_groups = [
            {"sklearn", "tensorflow", "torch", "keras"},
            {"flask", "fastapi", "django"},
            {"pandas", "polars", "dask"},
        ]
        
        tag_names = {t.name.lower() for t in tech_tags}
        
        for group in conflict_groups:
            found = tag_names & group
            if len(found) > 1:
                conflicts.append(list(found))
        
        return conflicts
    
    def _create_conflict_item(self, node: Node, conflicts: list) -> ConfirmationItem:
        return ConfirmationItem(
            item_id=f"{node.id}_conflict",
            node_id=node.id,
            uncertainty_type=UncertaintyType.CONFLICTING_INFO,
            field_name="tech_tags",
            suggested_value=conflicts[0][0] if conflicts else "",
            alternatives=conflicts[0][1:] if conflicts else [],
            confidence=0.4,
            reasoning=f"检测到可能冲突的技术标签: {', '.join(conflicts[0])}",
        )


class ConfirmationManager:
    """待确认标注管理器"""
    
    def __init__(self, projmap: ProjMap, thresholds: Optional[dict] = None):
        self.projmap = projmap
        self.detector = UncertaintyDetector(thresholds)
        self._sessions: dict[str, ConfirmationSession] = {}
        self._current_session: Optional[ConfirmationSession] = None
    
    def create_session(self) -> ConfirmationSession:
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        all_items = []
        for node in self.projmap.nodes:
            if node.needs_confirmation:
                items = self.detector.detect(node)
                all_items.extend(items)
        
        session = ConfirmationSession(
            session_id=session_id,
            created_at=datetime.now(),
            items=all_items,
            total_items=len(all_items),
        )
        
        self._sessions[session_id] = session
        self._current_session = session
        
        return session
    
    def get_pending_items(self, session_id: Optional[str] = None) -> list[ConfirmationItem]:
        session = self._get_session(session_id)
        return [item for item in session.items if item.status == ConfirmationStatus.PENDING]
    
    def confirm_item(
        self,
        item_id: str,
        action: str,
        correction: Optional[Any] = None,
        session_id: Optional[str] = None,
        user: Optional[str] = None,
    ) -> ConfirmationItem:
        session = self._get_session(session_id)
        
        item = next((i for i in session.items if i.item_id == item_id), None)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        if action == "confirm":
            item.status = ConfirmationStatus.CONFIRMED
            self._apply_confirmation(item)
        elif action == "correct":
            item.status = ConfirmationStatus.CORRECTED
            item.user_correction = correction
            self._apply_correction(item, correction)
        elif action == "ignore":
            item.status = ConfirmationStatus.IGNORED
        
        item.confirmed_at = datetime.now()
        item.confirmed_by = user
        
        self._update_session_counts(session)
        
        return item
    
    def confirm_all_pending(self, session_id: Optional[str] = None) -> int:
        session = self._get_session(session_id)
        count = 0
        
        for item in session.items:
            if item.status == ConfirmationStatus.PENDING:
                item.status = ConfirmationStatus.CONFIRMED
                item.confirmed_at = datetime.now()
                self._apply_confirmation(item)
                count += 1
        
        self._update_session_counts(session)
        return count
    
    def get_session_summary(self, session_id: Optional[str] = None) -> dict:
        session = self._get_session(session_id)
        
        return {
            "session_id": session.session_id,
            "created_at": session.created_at.isoformat(),
            "total_items": session.total_items,
            "pending": session.total_items - session.confirmed_count - session.corrected_count - session.ignored_count,
            "confirmed": session.confirmed_count,
            "corrected": session.corrected_count,
            "ignored": session.ignored_count,
            "progress": (session.confirmed_count + session.corrected_count + session.ignored_count) / max(1, session.total_items) * 100,
        }
    
    def _get_session(self, session_id: Optional[str]) -> ConfirmationSession:
        if session_id:
            return self._sessions.get(session_id, self._current_session or self.create_session())
        return self._current_session or self.create_session()
    
    def _apply_confirmation(self, item: ConfirmationItem):
        node = next((n for n in self.projmap.nodes if n.id == item.node_id), None)
        if node:
            node.needs_confirmation = False
            node.confidence = max(node.confidence or 0.5, 0.8)
    
    def _apply_correction(self, item: ConfirmationItem, correction: Any):
        node = next((n for n in self.projmap.nodes if n.id == item.node_id), None)
        if node:
            node.needs_confirmation = False
            node.confidence = 1.0
            node.inferred_by = InferenceSource.MANUAL
            
            if item.field_name == "function_tags" and isinstance(correction, list):
                node.function_tags = correction
            elif item.field_name == "description" and isinstance(correction, str):
                node.description = correction
            elif item.field_name == "all" and isinstance(correction, dict):
                if "function_tags" in correction:
                    node.function_tags = correction["function_tags"]
                if "description" in correction:
                    node.description = correction["description"]
    
    def _update_session_counts(self, session: ConfirmationSession):
        session.confirmed_count = sum(
            1 for i in session.items if i.status == ConfirmationStatus.CONFIRMED
        )
        session.corrected_count = sum(
            1 for i in session.items if i.status == ConfirmationStatus.CORRECTED
        )
        session.ignored_count = sum(
            1 for i in session.items if i.status == ConfirmationStatus.IGNORED
        )


VISUAL_STYLES = {
    "pending": {
        "border_style": "dashed",
        "border_color": "#f0ad4e",
        "background_color": "#fff8e6",
        "icon": "❓",
        "badge_text": "待确认",
        "badge_color": "#f0ad4e",
        "opacity": 0.9,
    },
    "confirmed": {
        "border_style": "solid",
        "border_color": "#5cb85c",
        "background_color": "#ffffff",
        "icon": "✓",
        "badge_text": None,
        "badge_color": None,
        "opacity": 1.0,
    },
    "corrected": {
        "border_style": "solid",
        "border_color": "#5bc0de",
        "background_color": "#ffffff",
        "icon": "✎",
        "badge_text": "已修正",
        "badge_color": "#5bc0de",
        "opacity": 1.0,
    },
    "ignored": {
        "border_style": "dotted",
        "border_color": "#999999",
        "background_color": "#f5f5f5",
        "icon": "○",
        "badge_text": None,
        "badge_color": None,
        "opacity": 0.6,
    },
}


def get_visual_style(status: ConfirmationStatus) -> dict:
    return VISUAL_STYLES.get(status, VISUAL_STYLES["pending"])


def generate_confirmation_ui_data(item: ConfirmationItem) -> dict:
    style = get_visual_style(item.status)
    
    return {
        "item_id": item.item_id,
        "node_id": item.node_id,
        "uncertainty_type": item.uncertainty_type.value,
        "field_name": item.field_name,
        "suggested_value": item.suggested_value,
        "alternatives": item.alternatives,
        "confidence": item.confidence,
        "reasoning": item.reasoning,
        "status": item.status.value,
        "visual_style": style,
        "actions": _get_available_actions(item.status),
    }


def _get_available_actions(status: ConfirmationStatus) -> list[dict]:
    if status == ConfirmationStatus.PENDING:
        return [
            {"action": "confirm", "label": "确认", "icon": "✓", "primary": True},
            {"action": "correct", "label": "修正", "icon": "✎", "primary": False},
            {"action": "ignore", "label": "忽略", "icon": "○", "primary": False},
        ]
    return []


def batch_detect_uncertainties(projmap: ProjMap) -> dict:
    detector = UncertaintyDetector()
    
    results = {
        "total_nodes": len(projmap.nodes),
        "nodes_needing_confirmation": 0,
        "by_type": {},
        "by_confidence_range": {
            "very_low": 0,
            "low": 0,
            "medium": 0,
            "high": 0,
        },
        "items": [],
    }
    
    for node in projmap.nodes:
        items = detector.detect(node)
        
        if items:
            results["nodes_needing_confirmation"] += 1
            
            for item in items:
                results["items"].append({
                    "node_id": node.id,
                    "node_name": node.name,
                    "uncertainty_type": item.uncertainty_type.value,
                    "confidence": item.confidence,
                })
                
                type_key = item.uncertainty_type.value
                results["by_type"][type_key] = results["by_type"].get(type_key, 0) + 1
        
        if node.confidence is not None:
            if node.confidence < 0.5:
                results["by_confidence_range"]["very_low"] += 1
            elif node.confidence < 0.7:
                results["by_confidence_range"]["low"] += 1
            elif node.confidence < 0.9:
                results["by_confidence_range"]["medium"] += 1
            else:
                results["by_confidence_range"]["high"] += 1
    
    return results
