"""决策追溯系统

解决"决策遗忘"痛点：参数来源、方案取舍遗忘
提供完整的决策历史追溯和参数变更追踪。
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional
from collections import defaultdict

from projmap.models import ProjMap, Decision, DecisionType, Node


@dataclass
class ParameterChange:
    """参数变更记录"""
    parameter_name: str
    old_value: Any
    new_value: Any
    timestamp: datetime
    decision_id: str
    reason: str


@dataclass
class DecisionChain:
    """决策链"""
    root_decision: Decision
    related_decisions: list[Decision] = field(default_factory=list)
    consequences: list[dict] = field(default_factory=list)


class DecisionTracer:
    """决策追溯器
    
    提供决策的全生命周期追溯，包括：
    - 参数变更历史
    - 决策因果关系
    - 方案取舍记录
    - 决策影响分析
    """
    
    def __init__(self, projmap: ProjMap):
        self.projmap = projmap
        self._decision_map = {d.id: d for d in projmap.decisions}
        self._node_map = {n.id: n for n in projmap.nodes}
    
    def trace_parameter(
        self,
        parameter_name: str,
        node_id: Optional[str] = None,
    ) -> list[ParameterChange]:
        """追溯参数的完整变更历史"""
        changes = []
        
        # 筛选相关决策
        relevant_decisions = self.projmap.decisions
        if node_id:
            relevant_decisions = [d for d in relevant_decisions if d.node_id == node_id]
        
        # 按时间排序
        sorted_decisions = sorted(relevant_decisions, key=lambda d: d.timestamp)
        
        last_value = None
        for decision in sorted_decisions:
            if parameter_name in decision.parameters:
                new_value = decision.parameters[parameter_name]
                
                change = ParameterChange(
                    parameter_name=parameter_name,
                    old_value=last_value,
                    new_value=new_value,
                    timestamp=decision.timestamp,
                    decision_id=decision.id,
                    reason=decision.reason or "",
                )
                changes.append(change)
                last_value = new_value
        
        return changes
    
    def get_parameter_current_value(
        self,
        parameter_name: str,
        node_id: Optional[str] = None,
    ) -> tuple[Any, Optional[Decision]]:
        """获取参数的当前值及最后修改的决策"""
        changes = self.trace_parameter(parameter_name, node_id)
        if not changes:
            return None, None
        
        last_change = changes[-1]
        decision = self._decision_map.get(last_change.decision_id)
        return last_change.new_value, decision
    
    def trace_decision_chain(self, decision_id: str) -> Optional[DecisionChain]:
        """追溯决策的完整链条"""
        decision = self._decision_map.get(decision_id)
        if not decision:
            return None
        
        chain = DecisionChain(root_decision=decision)
        
        # 查找相关决策（同一节点的其他决策）
        for d in self.projmap.decisions:
            if d.node_id == decision.node_id and d.id != decision_id:
                chain.related_decisions.append(d)
        
        # 按时间排序
        chain.related_decisions.sort(key=lambda d: d.timestamp)
        
        # 分析决策影响
        chain.consequences = self._analyze_consequences(decision)
        
        return chain
    
    def _analyze_consequences(self, decision: Decision) -> list[dict]:
        """分析决策的影响"""
        consequences = []
        
        # 1. 检查后续决策是否引用了此决策的参数
        for d in self.projmap.decisions:
            if d.timestamp > decision.timestamp:
                for param_name in decision.parameters:
                    if param_name in d.parameters:
                        consequences.append({
                            "type": "parameter_influence",
                            "decision_id": d.id,
                            "parameter": param_name,
                            "description": f"影响了后续决策 {d.id} 的参数 {param_name}",
                        })
        
        # 2. 检查是否有依赖此节点的其他节点
        node = self._node_map.get(decision.node_id)
        if node:
            # 这里可以添加更多影响分析逻辑
            pass
        
        return consequences
    
    def get_alternatives_analysis(self, decision_id: str) -> Optional[dict]:
        """获取方案取舍的详细分析"""
        decision = self._decision_map.get(decision_id)
        if not decision:
            return None
        
        return {
            "decision_id": decision.id,
            "selected": decision.content,
            "reason": decision.reason,
            "alternatives": [
                {
                    "name": alt.name,
                    "reason_rejected": alt.reason_rejected,
                }
                for alt in decision.alternatives
            ],
            "timestamp": decision.timestamp.isoformat(),
            "node": {
                "id": decision.node_id,
                "name": self._node_map.get(decision.node_id, Node(id=decision.node_id, name="Unknown", file_path="")).name,
            },
        }
    
    def search_by_keyword(self, keyword: str) -> list[Decision]:
        """按关键词搜索决策"""
        keyword_lower = keyword.lower()
        results = []
        
        for decision in self.projmap.decisions:
            # 搜索内容
            if keyword_lower in decision.content.lower():
                results.append(decision)
                continue
            
            # 搜索原因
            if decision.reason and keyword_lower in decision.reason.lower():
                results.append(decision)
                continue
            
            # 搜索备选方案
            for alt in decision.alternatives:
                if keyword_lower in alt.name.lower():
                    results.append(decision)
                    break
            
            # 搜索参数
            for param_name, param_value in decision.parameters.items():
                if keyword_lower in param_name.lower():
                    results.append(decision)
                    break
                if isinstance(param_value, str) and keyword_lower in param_value.lower():
                    results.append(decision)
                    break
        
        return results
    
    def get_decisions_by_time_range(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[Decision]:
        """按时间范围获取决策"""
        results = []
        
        for decision in self.projmap.decisions:
            if start and decision.timestamp < start:
                continue
            if end and decision.timestamp > end:
                continue
            results.append(decision)
        
        return sorted(results, key=lambda d: d.timestamp)
    
    def get_decision_statistics(self) -> dict:
        """获取决策统计信息"""
        stats = {
            "total_decisions": len(self.projmap.decisions),
            "by_type": defaultdict(int),
            "by_node": defaultdict(int),
            "by_time": defaultdict(int),
            "parameters_tracked": set(),
        }
        
        for decision in self.projmap.decisions:
            # 按类型统计
            stats["by_type"][decision.type.value] += 1
            
            # 按节点统计
            stats["by_node"][decision.node_id] += 1
            
            # 按月统计
            month_key = decision.timestamp.strftime("%Y-%m")
            stats["by_time"][month_key] += 1
            
            # 收集参数
            stats["parameters_tracked"].update(decision.parameters.keys())
        
        # 转换 set 为 list
        stats["parameters_tracked"] = sorted(list(stats["parameters_tracked"]))
        
        return dict(stats)
    
    def generate_decision_report(self, node_id: Optional[str] = None) -> dict:
        """生成决策报告"""
        decisions = self.projmap.decisions
        if node_id:
            decisions = [d for d in decisions if d.node_id == node_id]
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "node_id": node_id,
            "total_decisions": len(decisions),
            "decisions": [],
        }
        
        for decision in sorted(decisions, key=lambda d: d.timestamp, reverse=True):
            decision_data = {
                "id": decision.id,
                "type": decision.type.value,
                "content": decision.content,
                "timestamp": decision.timestamp.isoformat(),
                "reason": decision.reason,
                "parameters": decision.parameters,
                "alternatives_count": len(decision.alternatives),
            }
            
            # 添加节点信息
            node = self._node_map.get(decision.node_id)
            if node:
                decision_data["node"] = {
                    "id": node.id,
                    "name": node.name,
                    "file_path": node.file_path,
                }
            
            report["decisions"].append(decision_data)
        
        return report
    
    def find_abandoned_approaches(self) -> list[dict]:
        """查找被放弃的方案"""
        abandoned = []
        
        for decision in self.projmap.decisions:
            if decision.type == DecisionType.ABANDONED:
                abandoned.append({
                    "decision_id": decision.id,
                    "content": decision.content,
                    "reason": decision.reason,
                    "timestamp": decision.timestamp.isoformat(),
                    "node_id": decision.node_id,
                    "node_name": self._node_map.get(decision.node_id, Node(id=decision.node_id, name="Unknown", file_path="")).name,
                })
            
            # 也包括有备选方案的决策
            for alt in decision.alternatives:
                abandoned.append({
                    "decision_id": decision.id,
                    "content": alt.name,
                    "reason": alt.reason_rejected,
                    "timestamp": decision.timestamp.isoformat(),
                    "node_id": decision.node_id,
                    "node_name": self._node_map.get(decision.node_id, Node(id=decision.node_id, name="Unknown", file_path="")).name,
                    "parent_decision": decision.content,
                })
        
        return sorted(abandoned, key=lambda x: x["timestamp"], reverse=True)
    
    def export_parameter_history(self, parameter_name: str) -> str:
        """导出参数历史为 Markdown"""
        changes = self.trace_parameter(parameter_name)
        
        lines = [
            f"# 参数历史: {parameter_name}",
            "",
            f"**总变更次数**: {len(changes)}",
            "",
            "## 变更记录",
            "",
            "| 时间 | 旧值 | 新值 | 原因 |",
            "|------|------|------|------|",
        ]
        
        for change in changes:
            old_val = str(change.old_value) if change.old_value is not None else "-"
            new_val = str(change.new_value)
            reason = change.reason or "-"
            time_str = change.timestamp.strftime("%Y-%m-%d %H:%M")
            
            lines.append(f"| {time_str} | {old_val} | {new_val} | {reason} |")
        
        lines.append("")
        
        # 当前值
        current_value, last_decision = self.get_parameter_current_value(parameter_name)
        if current_value is not None:
            lines.extend([
                "## 当前值",
                "",
                f"**值**: {current_value}",
            ])
            if last_decision:
                lines.append(f"**最后修改**: {last_decision.timestamp.strftime('%Y-%m-%d %H:%M')}")
                if last_decision.reason:
                    lines.append(f"**修改原因**: {last_decision.reason}")
        
        return "\n".join(lines)


def generate_decision_timeline(projmap: ProjMap) -> list[dict]:
    """生成决策时间线"""
    tracer = DecisionTracer(projmap)
    
    timeline = []
    for decision in sorted(projmap.decisions, key=lambda d: d.timestamp):
        node = tracer._node_map.get(decision.node_id)
        
        event = {
            "timestamp": decision.timestamp.isoformat(),
            "type": decision.type.value,
            "title": decision.content[:50] + "..." if len(decision.content) > 50 else decision.content,
            "node_name": node.name if node else "Unknown",
            "node_id": decision.node_id,
            "has_alternatives": len(decision.alternatives) > 0,
            "parameters_count": len(decision.parameters),
        }
        
        timeline.append(event)
    
    return timeline
