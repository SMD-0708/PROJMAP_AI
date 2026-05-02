"""决策点管理器

提供决策点的创建、查询、更新和删除功能。
支持参数溯源和失败方案记录。
"""

import os
from datetime import datetime
from typing import Optional

from projmap.models import (
    Decision,
    DecisionType,
    Alternative,
    ProjMap,
    generate_decision_id,
)


class DecisionManager:
    def __init__(self, projmap: ProjMap):
        self.projmap = projmap

    def add_decision(
        self,
        node_id: str,
        decision_type: str,
        content: str,
        reason: Optional[str] = None,
        alternatives: Optional[list[dict]] = None,
        parameters: Optional[dict] = None,
    ) -> Decision:
        if isinstance(decision_type, str):
            decision_type = DecisionType(decision_type)
        
        decision_id = generate_decision_id(node_id, decision_type)
        
        alt_objects = []
        if alternatives:
            for alt in alternatives:
                alt_objects.append(Alternative(
                    name=alt.get("name", ""),
                    reason_rejected=alt.get("reason_rejected"),
                ))
        
        decision = Decision(
            id=decision_id,
            node_id=node_id,
            type=decision_type,
            content=content,
            timestamp=datetime.now(),
            reason=reason,
            alternatives=alt_objects,
            parameters=parameters or {},
        )
        
        self.projmap.decisions.append(decision)
        
        return decision

    def get_decisions_by_node(self, node_id: str) -> list[Decision]:
        return [d for d in self.projmap.decisions if d.node_id == node_id]

    def get_decisions_by_type(self, decision_type: str) -> list[Decision]:
        if isinstance(decision_type, str):
            decision_type = DecisionType(decision_type)
        return [d for d in self.projmap.decisions if d.type == decision_type]

    def get_decision(self, decision_id: str) -> Optional[Decision]:
        for d in self.projmap.decisions:
            if d.id == decision_id:
                return d
        return None

    def update_decision(
        self,
        decision_id: str,
        content: Optional[str] = None,
        reason: Optional[str] = None,
        parameters: Optional[dict] = None,
    ) -> Optional[Decision]:
        decision = self.get_decision(decision_id)
        if not decision:
            return None
        
        if content:
            decision.content = content
        if reason:
            decision.reason = reason
        if parameters:
            decision.parameters.update(parameters)
        
        return decision

    def add_alternative(
        self,
        decision_id: str,
        name: str,
        reason_rejected: Optional[str] = None,
    ) -> Optional[Decision]:
        decision = self.get_decision(decision_id)
        if not decision:
            return None
        
        decision.alternatives.append(Alternative(
            name=name,
            reason_rejected=reason_rejected,
        ))
        
        return decision

    def delete_decision(self, decision_id: str) -> bool:
        for i, d in enumerate(self.projmap.decisions):
            if d.id == decision_id:
                self.projmap.decisions.pop(i)
                return True
        return False

    def search_decisions(self, keyword: str) -> list[Decision]:
        keyword_lower = keyword.lower()
        results = []
        
        for d in self.projmap.decisions:
            if keyword_lower in d.content.lower():
                results.append(d)
            elif d.reason and keyword_lower in d.reason.lower():
                results.append(d)
            elif any(keyword_lower in a.name.lower() for a in d.alternatives):
                results.append(d)
        
        return results

    def get_parameter_history(self, param_name: str) -> list[dict]:
        history = []
        
        for d in self.projmap.decisions:
            if param_name in d.parameters:
                history.append({
                    "decision_id": d.id,
                    "node_id": d.node_id,
                    "value": d.parameters[param_name],
                    "timestamp": d.timestamp.isoformat(),
                    "reason": d.reason,
                })
        
        return sorted(history, key=lambda x: x["timestamp"])

    def get_failed_attempts(self, node_id: Optional[str] = None) -> list[Decision]:
        failures = []
        
        for d in self.projmap.decisions:
            if d.type in (DecisionType.ABANDONED, DecisionType.FAILURE):
                if node_id is None or d.node_id == node_id:
                    failures.append(d)
        
        return failures

    def export_decisions_report(self) -> dict:
        report = {
            "total_decisions": len(self.projmap.decisions),
            "by_type": {},
            "by_node": {},
            "recent": [],
        }
        
        for dt in DecisionType:
            report["by_type"][dt.value] = len(self.get_decisions_by_type(dt))
        
        node_map = {n.id: n.name for n in self.projmap.nodes}
        
        for d in self.projmap.decisions:
            node_name = node_map.get(d.node_id, d.node_id)
            if node_name not in report["by_node"]:
                report["by_node"][node_name] = []
            report["by_node"][node_name].append({
                "id": d.id,
                "type": d.type.value,
                "content": d.content,
                "timestamp": d.timestamp.isoformat(),
            })
        
        sorted_decisions = sorted(
            self.projmap.decisions,
            key=lambda x: x.timestamp,
            reverse=True,
        )
        report["recent"] = [
            {
                "id": d.id,
                "node": node_map.get(d.node_id, d.node_id),
                "type": d.type.value,
                "content": d.content,
                "timestamp": d.timestamp.isoformat(),
            }
            for d in sorted_decisions[:10]
        ]
        
        return report


def create_decision(
    projmap: ProjMap,
    node_id: str,
    decision_type: str,
    content: str,
    **kwargs,
) -> Decision:
    manager = DecisionManager(projmap)
    return manager.add_decision(node_id, decision_type, content, **kwargs)
