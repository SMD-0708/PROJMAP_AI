"""路径状态机管理器

解决两大痛点：
1. AI 污染: AI 分不清主线文件
2. 废线干扰: 废弃代码持续干扰

提供严格的状态管理和转换规则。
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable
from collections import defaultdict

from projmap.models import ProjMap, Node, NodeStatus, NodeType

logger = logging.getLogger(__name__)


class StateTransition(Enum):
    """状态转换类型"""
    ACTIVATE = "activate"           # 休眠/归档 -> 主线
    BRANCH = "branch"               # 主线/休眠 -> 分支
    DORMANT = "dormant"             # 主线/分支 -> 休眠
    ARCHIVE = "archive"             # 任何 -> 归档
    RESTORE = "restore"             # 归档 -> 休眠


@dataclass
class StateChange:
    """状态变更记录"""
    node_id: str
    from_status: NodeStatus
    to_status: NodeStatus
    timestamp: datetime
    reason: str
    triggered_by: str  # 谁触发的变更


@dataclass
class StateRule:
    """状态规则"""
    from_status: NodeStatus
    to_status: NodeStatus
    allowed: bool
    requires_reason: bool = False
    requires_confirmation: bool = False
    description: str = ""


class PathStateMachine:
    """路径状态机
    
    管理节点状态的转换，确保状态变更的可追溯性和合理性。
    核心原则：
    - 主线 (active_main): 只有一条，当前活跃的核心路径
    - 分支 (active_branch): 可以有多个，并行开发的路径
    - 休眠 (dormant): 暂时不活跃，但可能恢复
    - 归档 (archived): 已废弃，不再维护
    """
    
    # 状态转换规则
    TRANSITION_RULES = [
        # 激活规则
        StateRule(NodeStatus.DORMANT, NodeStatus.ACTIVE_MAIN, True, True, True, "从休眠激活为主线"),
        StateRule(NodeStatus.DORMANT, NodeStatus.ACTIVE_BRANCH, True, False, False, "从休眠激活为分支"),
        StateRule(NodeStatus.ARCHIVED, NodeStatus.ACTIVE_MAIN, True, True, True, "从归档恢复为主线（谨慎）"),
        StateRule(NodeStatus.ARCHIVED, NodeStatus.ACTIVE_BRANCH, True, True, True, "从归档恢复为分支（谨慎）"),
        
        # 分支规则
        StateRule(NodeStatus.ACTIVE_MAIN, NodeStatus.ACTIVE_BRANCH, True, False, False, "主线转为分支"),
        StateRule(NodeStatus.DORMANT, NodeStatus.ACTIVE_BRANCH, True, False, False, "休眠转为分支"),
        
        # 休眠规则
        StateRule(NodeStatus.ACTIVE_MAIN, NodeStatus.DORMANT, True, True, False, "主线休眠"),
        StateRule(NodeStatus.ACTIVE_BRANCH, NodeStatus.DORMANT, True, False, False, "分支休眠"),
        
        # 归档规则
        StateRule(NodeStatus.ACTIVE_MAIN, NodeStatus.ARCHIVED, True, True, True, "主线归档（重大决策）"),
        StateRule(NodeStatus.ACTIVE_BRANCH, NodeStatus.ARCHIVED, True, False, False, "分支归档"),
        StateRule(NodeStatus.DORMANT, NodeStatus.ARCHIVED, True, False, False, "休眠归档"),
        
        # 恢复规则
        StateRule(NodeStatus.ARCHIVED, NodeStatus.DORMANT, True, False, False, "归档恢复为休眠"),
        
        # 禁止的规则
        StateRule(NodeStatus.ACTIVE_MAIN, NodeStatus.ACTIVE_MAIN, False, description="已是主线"),
        StateRule(NodeStatus.ARCHIVED, NodeStatus.ARCHIVED, False, description="已是归档"),
    ]
    
    def __init__(self, projmap: ProjMap, history_dir: Optional[str] = None):
        self.projmap = projmap
        self._change_history: list[StateChange] = []
        self._node_map = {n.id: n for n in projmap.nodes}
        self._callbacks: list[Callable[[StateChange], None]] = []
        
        # 设置历史记录目录
        if history_dir:
            self._history_dir = history_dir
        elif projmap.metadata and projmap.metadata.file_path:
            self._history_dir = os.path.join(
                os.path.dirname(projmap.metadata.file_path),
                ".projmap",
                "state_history"
            )
        else:
            self._history_dir = ".projmap/state_history"
        
        # 加载历史记录
        self._load_history()
        
        # 注册自动保存回调
        self.register_callback(self._auto_save_callback)
        
        logger.info(f"状态机初始化完成，历史记录目录: {self._history_dir}")
    
    def _get_history_file(self) -> str:
        """获取历史记录文件路径"""
        return os.path.join(self._history_dir, "transitions.jsonl")
    
    def _load_history(self):
        """从历史文件加载变更记录"""
        history_file = self._get_history_file()
        
        if not os.path.exists(history_file):
            logger.debug(f"历史记录文件不存在: {history_file}")
            return
        
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        change = StateChange(
                            node_id=data["node_id"],
                            from_status=NodeStatus(data["from_status"]),
                            to_status=NodeStatus(data["to_status"]),
                            timestamp=datetime.fromisoformat(data["timestamp"]),
                            reason=data["reason"],
                            triggered_by=data["triggered_by"],
                        )
                        self._change_history.append(change)
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"解析历史记录行失败: {e}")
                        continue
            
            logger.info(f"已加载 {len(self._change_history)} 条历史记录")
        except Exception as e:
            logger.error(f"加载历史记录失败: {e}")
    
    def _save_change_to_file(self, change: StateChange):
        """将变更保存到文件"""
        try:
            # 确保目录存在
            os.makedirs(self._history_dir, exist_ok=True)
            
            history_file = self._get_history_file()
            
            # 追加写入 JSON Lines 格式
            with open(history_file, "a", encoding="utf-8") as f:
                data = {
                    "node_id": change.node_id,
                    "from_status": change.from_status.value,
                    "to_status": change.to_status.value,
                    "timestamp": change.timestamp.isoformat(),
                    "reason": change.reason,
                    "triggered_by": change.triggered_by,
                }
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
            
            logger.debug(f"变更已保存到文件: {change.node_id} {change.from_status.value} -> {change.to_status.value}")
        except Exception as e:
            logger.error(f"保存变更到文件失败: {e}")
    
    def _auto_save_callback(self, change: StateChange):
        """自动保存回调"""
        self._save_change_to_file(change)
    
    def export_history(self, output_path: str) -> bool:
        """导出历史记录到指定文件"""
        try:
            data = {
                "exported_at": datetime.now().isoformat(),
                "total_changes": len(self._change_history),
                "changes": [
                    {
                        "node_id": c.node_id,
                        "node_name": self._node_map.get(c.node_id, Node(id=c.node_id, name="Unknown", file_path="")).name,
                        "from_status": c.from_status.value,
                        "to_status": c.to_status.value,
                        "timestamp": c.timestamp.isoformat(),
                        "reason": c.reason,
                        "triggered_by": c.triggered_by,
                    }
                    for c in self._change_history
                ],
            }
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"历史记录已导出到: {output_path}")
            return True
        except Exception as e:
            logger.error(f"导出历史记录失败: {e}")
            return False
    
    def get_transition_rule(
        self,
        from_status: NodeStatus,
        to_status: NodeStatus,
    ) -> Optional[StateRule]:
        """获取状态转换规则"""
        for rule in self.TRANSITION_RULES:
            if rule.from_status == from_status and rule.to_status == to_status:
                return rule
        return None
    
    def can_transition(
        self,
        node_id: str,
        to_status: NodeStatus,
    ) -> tuple[bool, str]:
        """检查是否可以进行状态转换"""
        node = self._node_map.get(node_id)
        if not node:
            return False, f"节点不存在: {node_id}"
        
        from_status = node.status
        
        # 相同状态
        if from_status == to_status:
            return False, f"节点已经是 {to_status.value} 状态"
        
        # 检查规则
        rule = self.get_transition_rule(from_status, to_status)
        if not rule:
            return False, f"不允许从 {from_status.value} 转换为 {to_status.value}"
        
        if not rule.allowed:
            return False, rule.description
        
        # 特殊规则：主线唯一性
        if to_status == NodeStatus.ACTIVE_MAIN:
            current_main = self.get_active_main()
            if current_main and current_main.id != node_id:
                return False, f"已存在主线节点: {current_main.name}，请先将其降级"
        
        return True, "可以转换"
    
    def transition(
        self,
        node_id: str,
        to_status: NodeStatus,
        reason: str = "",
        triggered_by: str = "user",
    ) -> tuple[bool, str]:
        """执行状态转换"""
        can_trans, message = self.can_transition(node_id, to_status)
        if not can_trans:
            return False, message
        
        node = self._node_map[node_id]
        from_status = node.status
        
        # 处理主线唯一性
        if to_status == NodeStatus.ACTIVE_MAIN:
            current_main = self.get_active_main()
            if current_main:
                # 将当前主线降级为分支
                self._do_transition(
                    current_main.id,
                    NodeStatus.ACTIVE_BRANCH,
                    f"自动降级：新的主线节点 {node.name} 被激活",
                    "system",
                )
        
        # 执行转换
        success, msg = self._do_transition(node_id, to_status, reason, triggered_by)
        return success, msg
    
    def _do_transition(
        self,
        node_id: str,
        to_status: NodeStatus,
        reason: str,
        triggered_by: str,
    ) -> tuple[bool, str]:
        """内部执行状态转换"""
        node = self._node_map.get(node_id)
        if not node:
            return False, f"节点不存在: {node_id}"
        
        from_status = node.status
        
        # 更新状态
        node.status = to_status
        
        # 记录变更
        change = StateChange(
            node_id=node_id,
            from_status=from_status,
            to_status=to_status,
            timestamp=datetime.now(),
            reason=reason or f"状态从 {from_status.value} 转换为 {to_status.value}",
            triggered_by=triggered_by,
        )
        self._change_history.append(change)
        
        # 触发回调
        for callback in self._callbacks:
            callback(change)
        
        return True, f"节点 {node.name} 状态已更新为 {to_status.value}"
    
    def batch_transition(
        self,
        transitions: list[tuple[str, NodeStatus, str]],
        stop_on_error: bool = False,
    ) -> list[tuple[bool, str]]:
        """批量状态转换
        
        Args:
            transitions: 转换列表，每个元素为 (node_id, to_status, reason)
            stop_on_error: 遇到错误时是否停止
        
        Returns:
            每个转换的结果列表
        """
        logger.info(f"开始批量状态转换，共 {len(transitions)} 个")
        results = []
        
        for i, (node_id, to_status, reason) in enumerate(transitions):
            try:
                success, message = self.transition(node_id, to_status, reason, "batch")
                results.append((success, message))
                
                if not success and stop_on_error:
                    logger.warning(f"批量转换在第 {i+1} 个处停止: {message}")
                    break
                    
            except Exception as e:
                error_msg = f"批量转换失败: {e}"
                logger.error(error_msg)
                results.append((False, error_msg))
                
                if stop_on_error:
                    break
        
        success_count = sum(1 for r in results if r[0])
        logger.info(f"批量状态转换完成: {success_count}/{len(results)} 成功")
        
        return results
    
    def bulk_update_status(
        self,
        node_ids: list[str],
        to_status: NodeStatus,
        reason: str = "",
    ) -> dict:
        """批量更新多个节点到同一状态
        
        Args:
            node_ids: 节点ID列表
            to_status: 目标状态
            reason: 转换原因
        
        Returns:
            包含成功和失败列表的字典
        """
        logger.info(f"批量更新 {len(node_ids)} 个节点到 {to_status.value}")
        
        result = {
            "success": [],
            "failed": [],
            "skipped": [],
        }
        
        for node_id in node_ids:
            # 检查节点是否存在
            if node_id not in self._node_map:
                result["failed"].append({"node_id": node_id, "reason": "节点不存在"})
                continue
            
            # 检查是否可以转换
            can_trans, message = self.can_transition(node_id, to_status)
            if not can_trans:
                if "已经是" in message:
                    result["skipped"].append({"node_id": node_id, "reason": message})
                else:
                    result["failed"].append({"node_id": node_id, "reason": message})
                continue
            
            # 执行转换
            success, msg = self.transition(node_id, to_status, reason, "bulk")
            if success:
                result["success"].append(node_id)
            else:
                result["failed"].append({"node_id": node_id, "reason": msg})
        
        logger.info(f"批量更新完成: {len(result['success'])} 成功, "
                   f"{len(result['failed'])} 失败, {len(result['skipped'])} 跳过")
        
        return result
    
    def get_active_main(self) -> Optional[Node]:
        """获取当前主线节点"""
        for node in self.projmap.nodes:
            if node.status == NodeStatus.ACTIVE_MAIN:
                return node
        return None
    
    def get_active_branches(self) -> list[Node]:
        """获取所有活跃分支节点"""
        return [n for n in self.projmap.nodes if n.status == NodeStatus.ACTIVE_BRANCH]
    
    def get_dormant_nodes(self) -> list[Node]:
        """获取所有休眠节点"""
        return [n for n in self.projmap.nodes if n.status == NodeStatus.DORMANT]
    
    def get_archived_nodes(self) -> list[Node]:
        """获取所有归档节点"""
        return [n for n in self.projmap.nodes if n.status == NodeStatus.ARCHIVED]
    
    def get_active_path(self) -> list[Node]:
        """获取当前活跃路径（主线 + 分支）"""
        return [
            n for n in self.projmap.nodes
            if n.status in (NodeStatus.ACTIVE_MAIN, NodeStatus.ACTIVE_BRANCH)
        ]
    
    def get_change_history(self, node_id: Optional[str] = None) -> list[StateChange]:
        """获取状态变更历史"""
        if node_id:
            return [c for c in self._change_history if c.node_id == node_id]
        return self._change_history.copy()
    
    def register_callback(self, callback: Callable[[StateChange], None]):
        """注册状态变更回调"""
        self._callbacks.append(callback)
    
    def auto_archive_unused(
        self,
        days_threshold: int = 30,
        dry_run: bool = True,
    ) -> list[dict]:
        """自动归档长时间未使用的休眠节点
        
        Args:
            days_threshold: 休眠天数阈值
            dry_run: 是否为试运行模式（不实际执行）
        
        Returns:
            建议归档的节点列表
        """
        suggestions = []
        
        for node in self.projmap.nodes:
            if node.status != NodeStatus.DORMANT:
                continue
            
            # 检查最后修改时间
            if node.last_modified:
                days_inactive = (datetime.now() - node.last_modified).days
                
                if days_inactive >= days_threshold:
                    suggestion = {
                        "node_id": node.id,
                        "name": node.name,
                        "file_path": node.file_path,
                        "days_inactive": days_inactive,
                        "suggested_action": "archive",
                        "reason": f"已休眠 {days_inactive} 天",
                    }
                    suggestions.append(suggestion)
                    
                    if not dry_run:
                        self.transition(
                            node.id,
                            NodeStatus.ARCHIVED,
                            f"自动归档：休眠超过 {days_threshold} 天",
                            "auto",
                        )
        
        return suggestions
    
    def get_context_for_llm(
        self,
        include_dormant: bool = False,
        include_archived: bool = False,
    ) -> dict:
        """获取用于 LLM 的上下文
        
        解决 AI 污染问题：只返回主线和分支节点，
        可选是否包含休眠节点，默认不包含归档节点。
        """
        active_nodes = self.get_active_path()
        
        result = {
            "active_main": None,
            "active_branches": [],
            "dormant_nodes": [],
            "archived_count": 0,
        }
        
        main = self.get_active_main()
        if main:
            result["active_main"] = {
                "id": main.id,
                "name": main.name,
                "file_path": main.file_path,
                "description": main.description,
            }
        
        for node in self.get_active_branches():
            result["active_branches"].append({
                "id": node.id,
                "name": node.name,
                "file_path": node.file_path,
                "description": node.description,
            })
        
        if include_dormant:
            for node in self.get_dormant_nodes():
                result["dormant_nodes"].append({
                    "id": node.id,
                    "name": node.name,
                    "file_path": node.file_path,
                    "description": node.description,
                })
        
        if include_archived:
            result["archived_nodes"] = [
                {
                    "id": node.id,
                    "name": node.name,
                    "file_path": node.file_path,
                }
                for node in self.get_archived_nodes()
            ]
        else:
            result["archived_count"] = len(self.get_archived_nodes())
        
        return result
    
    def generate_state_report(self) -> dict:
        """生成状态报告"""
        main = self.get_active_main()
        branches = self.get_active_branches()
        dormant = self.get_dormant_nodes()
        archived = self.get_archived_nodes()
        
        return {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_nodes": len(self.projmap.nodes),
                "active_main": 1 if main else 0,
                "active_branches": len(branches),
                "dormant": len(dormant),
                "archived": len(archived),
            },
            "active_main": {
                "id": main.id if main else None,
                "name": main.name if main else None,
                "file_path": main.file_path if main else None,
            },
            "active_branches": [
                {"id": n.id, "name": n.name, "file_path": n.file_path}
                for n in branches
            ],
            "recent_changes": [
                {
                    "node_id": c.node_id,
                    "node_name": self._node_map.get(c.node_id, Node(id=c.node_id, name="Unknown", file_path="")).name,
                    "from": c.from_status.value,
                    "to": c.to_status.value,
                    "timestamp": c.timestamp.isoformat(),
                    "reason": c.reason,
                }
                for c in self._change_history[-10:]  # 最近10条
            ],
        }


def isolate_dormant_files(projmap: ProjMap, move_to: Optional[str] = None) -> list[dict]:
    """隔离休眠文件
    
    解决废线干扰问题：将休眠状态的文件移动到指定目录。
    
    Args:
        projmap: ProjMap 对象
        move_to: 目标目录，如果为 None 则只返回建议
    
    Returns:
        被隔离的文件列表
    """
    machine = PathStateMachine(projmap)
    dormant_nodes = machine.get_dormant_nodes()
    
    result = []
    for node in dormant_nodes:
        item = {
            "node_id": node.id,
            "name": node.name,
            "file_path": node.file_path,
            "action": "move_to_dormant",
        }
        
        if move_to and os.path.exists(node.file_path):
            # 实际移动文件
            try:
                import shutil
                
                if not os.path.exists(move_to):
                    os.makedirs(move_to, exist_ok=True)
                
                filename = os.path.basename(node.file_path)
                dest_path = os.path.join(move_to, filename)
                
                shutil.move(node.file_path, dest_path)
                item["moved_to"] = dest_path
                item["success"] = True
            except Exception as e:
                item["error"] = str(e)
                item["success"] = False
        
        result.append(item)
    
    return result
