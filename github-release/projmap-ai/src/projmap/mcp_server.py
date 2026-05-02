"""ProjMap MCP Server 接口模块

MCP (Model Context Protocol) 是AI编程工具的标准接口协议。
本模块实现ProjMap作为MCP Server，让AI编程工具（Trae/Cursor/灵码）能直接读取和更新脉络。

设计原则：
- ProjMap是"脉络数据的生产者和标准定义者"，而非"协作平台"
- 不自建用户认证、实时编辑、消息通知等协作功能
- 提供标准化数据接口，让现有协作平台来集成
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, Callable
from enum import Enum

from projmap.models import ProjMap, Node, Edge, Decision, NodeStatus, NodeType
from projmap.generator import generate_projmap
from projmap.state_machine import PathStateMachine
from projmap.decision_tracer import DecisionTracer
from projmap.project_navigator import ProjectNavigator
from projmap.tech_tags import TechTagManager, TechTagRecognizer


class MCPToolName(Enum):
    GET_PROJECT_MAP = "get_project_map"
    GET_NODE_DETAIL = "get_node_detail"
    GET_ACTIVE_CONTEXT = "get_active_context"
    SEARCH_DECISIONS = "search_decisions"
    SEARCH_FAILURES = "search_failures"
    GET_NAVIGATION_PATH = "get_navigation_path"
    UPDATE_NODE_STATUS = "update_node_status"
    ADD_DECISION = "add_decision"
    ADD_TECH_TAG = "add_tech_tag"
    GET_SKELETON = "get_skeleton"
    DEEP_ANALYZE_NODE = "deep_analyze_node"
    CONFIRM_INFERENCE = "confirm_inference"
    ABANDON_NODE = "abandon_node"
    REVIVE_NODE = "revive_node"


@dataclass
class MCPToolDefinition:
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    usage_scenario: str


MCP_TOOLS: list[MCPToolDefinition] = [
    MCPToolDefinition(
        name="get_project_map",
        description="获取项目的完整脉络图数据，包含所有节点、边和决策记录",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {
                    "type": "string",
                    "description": ".projmap 文件路径"
                },
                "include_dormant": {
                    "type": "boolean",
                    "description": "是否包含休眠节点",
                    "default": False
                },
                "trust_level": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "description": "信任梯度档位，控制返回数据详细程度"
                }
            },
            "required": ["projmap_path"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "version": {"type": "string"},
                "metadata": {"type": "object"},
                "nodes": {"type": "array"},
                "edges": {"type": "array"},
                "decisions": {"type": "array"},
                "active_state": {"type": "object"}
            }
        },
        usage_scenario="AI需要了解项目整体结构时调用，如：'这个项目是做什么的？'、'给我看项目脉络'"
    ),
    MCPToolDefinition(
        name="get_node_detail",
        description="获取指定节点的详细信息，包括技术标签、决策记录、失败信息等",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "node_id": {"type": "string", "description": "节点ID"},
                "include_code": {
                    "type": "boolean",
                    "description": "是否包含代码片段",
                    "default": False
                }
            },
            "required": ["projmap_path", "node_id"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "node": {"type": "object"},
                "tech_tags": {"type": "array"},
                "decisions": {"type": "array"},
                "dependencies": {"type": "array"},
                "dependents": {"type": "array"}
            }
        },
        usage_scenario="AI需要深入了解某个模块时调用，如：'data_processor.py 是做什么的？'"
    ),
    MCPToolDefinition(
        name="get_active_context",
        description="获取当前活跃的开发上下文，过滤掉废弃路径，避免AI污染",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "include_branches": {
                    "type": "boolean",
                    "description": "是否包含活跃分支",
                    "default": True
                }
            },
            "required": ["projmap_path"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "active_main": {"type": "object"},
                "active_branches": {"type": "array"},
                "recent_decisions": {"type": "array"},
                "pending_todos": {"type": "array"}
            }
        },
        usage_scenario="AI开始编程任务前调用，获取当前工作焦点，避免被废弃代码干扰"
    ),
    MCPToolDefinition(
        name="search_decisions",
        description="搜索决策记录，追溯历史决策和参数变更",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "query": {"type": "string", "description": "搜索关键词"},
                "decision_type": {
                    "type": "string",
                    "enum": ["parameter", "architecture", "algorithm", "method_selection", "path_abandonment"]
                },
                "node_id": {"type": "string", "description": "限定节点ID"}
            },
            "required": ["projmap_path", "query"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "total": {"type": "integer"}
            }
        },
        usage_scenario="AI需要了解为什么做出某个决策时调用，如：'为什么用XGBoost而不是RandomForest？'"
    ),
    MCPToolDefinition(
        name="search_failures",
        description="搜索失败记录，查找相似错误和解决方案",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "error_message": {"type": "string", "description": "错误信息"},
                "error_type": {"type": "string", "description": "错误类型"}
            },
            "required": ["projmap_path", "error_message"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "similar_failures": {"type": "array"},
                "solutions": {"type": "array"}
            }
        },
        usage_scenario="AI遇到错误时调用，查找项目中是否有类似问题和解决方案"
    ),
    MCPToolDefinition(
        name="get_navigation_path",
        description="获取项目阅读路径推荐，帮助快速理解项目",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "path_type": {
                    "type": "string",
                    "enum": ["quick_start", "architecture", "data_flow", "custom"],
                    "description": "路径类型"
                },
                "target_node": {"type": "string", "description": "目标节点（自定义路径时）"}
            },
            "required": ["projmap_path", "path_type"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "path_name": {"type": "string"},
                "nodes": {"type": "array"},
                "estimated_time": {"type": "integer"}
            }
        },
        usage_scenario="AI需要引导用户理解项目时调用，如：'帮我快速了解这个项目'"
    ),
    MCPToolDefinition(
        name="update_node_status",
        description="更新节点状态（主线/分支/休眠/归档）",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "node_id": {"type": "string"},
                "new_status": {
                    "type": "string",
                    "enum": ["active_main", "active_branch", "dormant", "archived"]
                },
                "reason": {"type": "string", "description": "状态变更原因"}
            },
            "required": ["projmap_path", "node_id", "new_status"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"}
            }
        },
        usage_scenario="AI帮助用户管理项目状态时调用，如：'这个实验已经废弃了'"
    ),
    MCPToolDefinition(
        name="add_decision",
        description="添加决策记录，记录技术选型的理由和备选方案",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "node_id": {"type": "string"},
                "decision_type": {"type": "string"},
                "content": {"type": "string"},
                "reason": {"type": "string"},
                "alternatives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "reason_rejected": {"type": "string"}
                        }
                    }
                },
                "decision_basis": {"type": "string"}
            },
            "required": ["projmap_path", "node_id", "decision_type", "content"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "decision_id": {"type": "string"},
                "success": {"type": "boolean"}
            }
        },
        usage_scenario="AI帮助用户记录决策时调用，如：'记录一下为什么选择这个方案'"
    ),
    MCPToolDefinition(
        name="add_tech_tag",
        description="为节点添加技术标签",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "node_id": {"type": "string"},
                "tag_name": {"type": "string"},
                "domain": {
                    "type": "string",
                    "enum": ["fintech", "research", "software", "custom"]
                },
                "category": {"type": "string"}
            },
            "required": ["projmap_path", "node_id", "tag_name"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "tag": {"type": "object"}
            }
        },
        usage_scenario="AI识别到代码使用的技术方法时调用"
    ),
    MCPToolDefinition(
        name="get_skeleton",
        description="获取项目骨架信息，用于快速理解项目结构",
        input_schema={
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "项目根目录"},
                "file_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要提取的文件类型"
                }
            },
            "required": ["project_path"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "files": {"type": "array"},
                "summary": {"type": "object"}
            }
        },
        usage_scenario="AI需要快速扫描项目结构时调用，不加载完整脉络"
    ),
    MCPToolDefinition(
        name="deep_analyze_node",
        description="深度分析指定节点，读取完整代码进行语义理解",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "node_id": {"type": "string"},
                "analysis_depth": {
                    "type": "string",
                    "enum": ["function", "class", "file"],
                    "description": "分析深度"
                }
            },
            "required": ["projmap_path", "node_id"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "analysis_result": {"type": "object"},
                "new_decisions": {"type": "array"},
                "new_tags": {"type": "array"}
            }
        },
        usage_scenario="用户点击节点请求深度分析时调用"
    ),
    MCPToolDefinition(
        name="confirm_inference",
        description="确认AI推断的内容",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "node_id": {"type": "string"},
                "corrections": {
                    "type": "object",
                    "description": "用户修正的内容"
                }
            },
            "required": ["projmap_path", "node_id"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "success": {"type": "boolean"}
            }
        },
        usage_scenario="用户确认AI推断的节点信息时调用"
    ),
    MCPToolDefinition(
        name="abandon_node",
        description="废弃节点，强制记录废弃原因",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "node_id": {"type": "string"},
                "abandoned_method": {"type": "string"},
                "abandon_reason": {"type": "string"},
                "attempted_solutions": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "revive_condition": {"type": "string"}
            },
            "required": ["projmap_path", "node_id", "abandoned_method", "abandon_reason"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "decision_id": {"type": "string"}
            }
        },
        usage_scenario="标记废弃路径时调用，确保决策被记录"
    ),
    MCPToolDefinition(
        name="revive_node",
        description="唤醒废弃节点",
        input_schema={
            "type": "object",
            "properties": {
                "projmap_path": {"type": "string"},
                "node_id": {"type": "string"},
                "revive_reason": {"type": "string"}
            },
            "required": ["projmap_path", "node_id", "revive_reason"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "success": {"type": "boolean"}
            }
        },
        usage_scenario="重新激活废弃路径时调用"
    ),
]


class MCPServer:
    """ProjMap MCP Server 实现
    
    提供标准MCP接口，让AI编程工具能直接操作ProjMap数据。
    """
    
    def __init__(self, project_root: str = "."):
        self.project_root = project_root
        self._projmap_cache: dict[str, ProjMap] = {}
    
    def _load_projmap(self, projmap_path: str) -> ProjMap:
        if projmap_path not in self._projmap_cache:
            self._projmap_cache[projmap_path] = ProjMap.load(projmap_path)
        return self._projmap_cache[projmap_path]
    
    def _save_projmap(self, projmap_path: str, projmap: ProjMap):
        projmap.save(projmap_path)
        self._projmap_cache[projmap_path] = projmap
    
    def get_tool_definitions(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in MCP_TOOLS
        ]
    
    def execute_tool(self, tool_name: str, arguments: dict) -> dict:
        handler = getattr(self, f"_handle_{tool_name}", None)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        
        try:
            return handler(arguments)
        except Exception as e:
            return {"error": str(e)}
    
    def _handle_get_project_map(self, args: dict) -> dict:
        projmap = self._load_projmap(args["projmap_path"])
        include_dormant = args.get("include_dormant", False)
        trust_level = args.get("trust_level", 2)
        
        if not include_dormant:
            nodes = [n for n in projmap.nodes if n.status != NodeStatus.DORMANT]
        else:
            nodes = projmap.nodes
        
        node_ids = {n.id for n in nodes}
        edges = [e for e in projmap.edges if e.source in node_ids and e.target in node_ids]
        
        return {
            "version": projmap.version,
            "metadata": {
                "project_name": projmap.metadata.project_name if projmap.metadata else "",
                "project_root": projmap.metadata.project_root if projmap.metadata else "",
                "description": projmap.metadata.description if projmap.metadata else "",
            },
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "file_path": n.file_path,
                    "status": n.status.value,
                    "tech_tags": [t.name for t in n.tech_tags] if n.tech_tags else [],
                    "needs_confirmation": n.needs_confirmation,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": e.id,
                    "source": e.source,
                    "target": e.target,
                    "type": e.type.value,
                    "flow_label": e.flow_label,
                }
                for e in edges
            ],
            "decisions": [
                {
                    "id": d.id,
                    "node_id": d.node_id,
                    "type": d.type.value,
                    "content": d.content,
                    "reason": d.reason,
                }
                for d in projmap.decisions
            ],
            "active_state": {
                "active_main": projmap.active_state.active_main if projmap.active_state else None,
                "active_branches": projmap.active_state.active_branches if projmap.active_state else [],
            }
        }
    
    def _handle_get_node_detail(self, args: dict) -> dict:
        projmap = self._load_projmap(args["projmap_path"])
        node_id = args["node_id"]
        
        node = next((n for n in projmap.nodes if n.id == node_id), None)
        if not node:
            return {"error": f"Node not found: {node_id}"}
        
        node_decisions = [d for d in projmap.decisions if d.node_id == node_id]
        
        dependencies = [
            {"node_id": e.target, "type": e.type.value}
            for e in projmap.edges if e.source == node_id
        ]
        dependents = [
            {"node_id": e.source, "type": e.type.value}
            for e in projmap.edges if e.target == node_id
        ]
        
        result = {
            "node": {
                "id": node.id,
                "name": node.name,
                "file_path": node.file_path,
                "status": node.status.value,
                "execution_status": node.execution_status.value if node.execution_status else "unknown",
                "description": node.description,
                "function_tags": node.function_tags,
                "tech_tags": [
                    {
                        "name": t.name,
                        "category": t.category,
                        "domain": t.domain,
                        "decision_id": t.decision_id,
                    }
                    for t in (node.tech_tags or [])
                ],
                "inferred_by": node.inferred_by.value if node.inferred_by else "unknown",
                "confidence": node.confidence,
                "needs_confirmation": node.needs_confirmation,
            },
            "decisions": [
                {
                    "id": d.id,
                    "type": d.type.value,
                    "content": d.content,
                    "reason": d.reason,
                    "alternatives": [
                        {"name": a.name, "reason_rejected": a.reason_rejected}
                        for a in (d.alternatives or [])
                    ],
                    "timestamp": d.timestamp.isoformat() if d.timestamp else None,
                }
                for d in node_decisions
            ],
            "dependencies": dependencies,
            "dependents": dependents,
        }
        
        if node.abandon_info:
            result["abandon_info"] = {
                "abandoned_method": node.abandon_info.abandoned_method,
                "abandon_reason": node.abandon_info.abandon_reason,
                "can_revive": node.abandon_info.can_revive,
                "revive_condition": node.abandon_info.revive_condition,
            }
        
        if node.failure_info:
            result["failure_info"] = {
                "error_type": node.failure_info.error_type,
                "error_message": node.failure_info.error_message,
                "resolved": node.failure_info.resolved,
                "resolution": node.failure_info.resolution,
            }
        
        return result
    
    def _handle_get_active_context(self, args: dict) -> dict:
        projmap = self._load_projmap(args["projmap_path"])
        machine = PathStateMachine(projmap)
        
        context = machine.get_context_for_llm(
            include_dormant=args.get("include_branches", True)
        )
        
        recent_decisions = sorted(
            projmap.decisions,
            key=lambda d: d.timestamp if d.timestamp else datetime.min,
            reverse=True
        )[:5]
        
        pending_todos = []
        for n in projmap.nodes:
            if n.todos:
                pending_todos.extend([
                    {"node_id": n.id, "description": t.description, "priority": t.priority}
                    for t in n.todos if t.status == "pending"
                ])
        
        return {
            "active_main": context.get("active_main"),
            "active_branches": context.get("active_branches", []),
            "recent_decisions": [
                {
                    "id": d.id,
                    "content": d.content[:100],
                    "node_id": d.node_id,
                }
                for d in recent_decisions
            ],
            "pending_todos": pending_todos[:10],
            "unconfirmed_inferences": [
                {"node_id": n.id, "name": n.name}
                for n in projmap.nodes if n.needs_confirmation
            ],
        }
    
    def _handle_search_decisions(self, args: dict) -> dict:
        projmap = self._load_projmap(args["projmap_path"])
        tracer = DecisionTracer(projmap)
        
        query = args["query"]
        decision_type = args.get("decision_type")
        node_id = args.get("node_id")
        
        results = []
        for d in projmap.decisions:
            if query.lower() in d.content.lower() or (d.reason and query.lower() in d.reason.lower()):
                if decision_type and d.type.value != decision_type:
                    continue
                if node_id and d.node_id != node_id:
                    continue
                results.append(d)
        
        return {
            "results": [
                {
                    "id": d.id,
                    "node_id": d.node_id,
                    "type": d.type.value,
                    "content": d.content,
                    "reason": d.reason,
                    "alternatives": [a.name for a in (d.alternatives or [])],
                    "timestamp": d.timestamp.isoformat() if d.timestamp else None,
                }
                for d in results[:20]
            ],
            "total": len(results),
        }
    
    def _handle_search_failures(self, args: dict) -> dict:
        from projmap.failure_retrieval import FailureRetrieval
        
        projmap = self._load_projmap(args["projmap_path"])
        retriever = FailureRetrieval(projmap)
        
        error_message = args["error_message"]
        error_type = args.get("error_type")
        
        patterns = retriever.search_failures(error_message, error_type)
        
        return {
            "similar_failures": [
                {
                    "error_type": p.error_type,
                    "error_message": p.error_message,
                    "solution": p.solution,
                    "resolved": p.resolved,
                }
                for p in patterns[:10]
            ],
            "solutions": [
                p.solution for p in patterns if p.solution and p.resolved
            ][:5],
        }
    
    def _handle_get_navigation_path(self, args: dict) -> dict:
        projmap = self._load_projmap(args["projmap_path"])
        navigator = ProjectNavigator(projmap)
        
        path_type = args["path_type"]
        
        if path_type == "quick_start":
            path = navigator.get_quick_start_path()
        elif path_type == "architecture":
            path = navigator.get_architecture_overview()
        else:
            path = navigator.get_quick_start_path()
        
        return {
            "path_name": path.name,
            "description": path.description,
            "nodes": [
                {
                    "order": rn.reading_order,
                    "node_id": rn.node.id,
                    "name": rn.node.name,
                    "file_path": rn.node.file_path,
                    "importance": rn.importance_score,
                    "why": rn.why_important,
                }
                for rn in path.nodes
            ],
            "estimated_time": path.estimated_time,
        }
    
    def _handle_update_node_status(self, args: dict) -> dict:
        projmap = self._load_projmap(args["projmap_path"])
        machine = PathStateMachine(projmap)
        
        node_id = args["node_id"]
        new_status = NodeStatus(args["new_status"])
        reason = args.get("reason", "")
        
        success, message = machine.transition(node_id, new_status, reason)
        
        if success:
            self._save_projmap(args["projmap_path"], projmap)
        
        return {"success": success, "message": message}
    
    def _handle_add_decision(self, args: dict) -> dict:
        from projmap.models import DecisionType, Alternative, DecisionSource, generate_decision_id
        
        projmap = self._load_projmap(args["projmap_path"])
        
        node_id = args["node_id"]
        decision_type = DecisionType(args["decision_type"])
        content = args["content"]
        reason = args.get("reason", "")
        decision_basis = args.get("decision_basis", "")
        
        alternatives = []
        for alt in args.get("alternatives", []):
            alternatives.append(Alternative(
                name=alt["name"],
                reason_rejected=alt.get("reason_rejected", ""),
            ))
        
        decision = Decision(
            id=generate_decision_id(node_id, decision_type),
            node_id=node_id,
            type=decision_type,
            content=content,
            reason=reason,
            alternatives=alternatives,
            decision_basis=decision_basis,
            timestamp=datetime.now(),
            source=DecisionSource.MANUAL,
        )
        
        projmap.decisions.append(decision)
        self._save_projmap(args["projmap_path"], projmap)
        
        return {"success": True, "decision_id": decision.id}
    
    def _handle_add_tech_tag(self, args: dict) -> dict:
        projmap = self._load_projmap(args["projmap_path"])
        manager = TechTagManager(projmap)
        
        try:
            tag = manager.add_manual_tag(
                node_id=args["node_id"],
                tag_name=args["tag_name"],
                category=args.get("category", "custom"),
                domain=args.get("domain", "custom"),
            )
            self._save_projmap(args["projmap_path"], projmap)
            return {"success": True, "tag": {"name": tag.name, "domain": tag.domain}}
        except ValueError as e:
            return {"success": False, "error": str(e)}
    
    def _handle_get_skeleton(self, args: dict) -> dict:
        from projmap.skeleton_extractor import SkeletonExtractor
        
        extractor = SkeletonExtractor(args["project_path"])
        skeleton = extractor.extract(file_types=args.get("file_types"))
        
        return skeleton
    
    def _handle_deep_analyze_node(self, args: dict) -> dict:
        return {
            "analysis_result": {"message": "Deep analysis requires LLM integration"},
            "new_decisions": [],
            "new_tags": [],
        }
    
    def _handle_confirm_inference(self, args: dict) -> dict:
        from projmap.tech_tags import InferenceAnnotator
        
        projmap = self._load_projmap(args["projmap_path"])
        annotator = InferenceAnnotator(projmap)
        
        annotator.confirm_inference(args["node_id"])
        
        corrections = args.get("corrections", {})
        if corrections:
            node = next((n for n in projmap.nodes if n.id == args["node_id"]), None)
            if node:
                if "name" in corrections:
                    node.name = corrections["name"]
                if "description" in corrections:
                    node.description = corrections["description"]
                if "function_tags" in corrections:
                    node.function_tags = corrections["function_tags"]
        
        self._save_projmap(args["projmap_path"], projmap)
        return {"success": True}
    
    def _handle_abandon_node(self, args: dict) -> dict:
        from projmap.tech_tags import AbandonmentManager
        
        projmap = self._load_projmap(args["projmap_path"])
        manager = AbandonmentManager(projmap)
        
        try:
            node, decision = manager.abandon_node(
                node_id=args["node_id"],
                abandoned_method=args["abandoned_method"],
                abandon_reason=args["abandon_reason"],
                attempted_solutions=args.get("attempted_solutions", []),
                can_revive=True,
                revive_condition=args.get("revive_condition", ""),
            )
            self._save_projmap(args["projmap_path"], projmap)
            return {"success": True, "decision_id": decision.id}
        except ValueError as e:
            return {"success": False, "error": str(e)}
    
    def _handle_revive_node(self, args: dict) -> dict:
        from projmap.tech_tags import AbandonmentManager
        
        projmap = self._load_projmap(args["projmap_path"])
        manager = AbandonmentManager(projmap)
        
        try:
            node, decision = manager.revive_node(
                node_id=args["node_id"],
                revive_reason=args["revive_reason"],
            )
            self._save_projmap(args["projmap_path"], projmap)
            return {"success": True}
        except ValueError as e:
            return {"success": False, "error": str(e)}


def generate_mcp_config(output_path: str = "mcp_config.json") -> str:
    server = MCPServer()
    config = {
        "name": "projmap",
        "version": "2.0.0",
        "description": "ProjMap MCP Server - 项目脉络认知系统",
        "tools": server.get_tool_definitions(),
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    return output_path
