"""ProjMap 数据模型定义

本模块定义了 .projmap 文件格式的核心数据结构。
设计原则：
1. 使用 dataclass 简化代码，提供类型安全
2. 支持从/到 JSON 的序列化/反序列化
3. 与 schemas/projmap-v1.json 保持一致
4. 支持技术标签、决策追溯、执行状态等增强功能
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import json
import hashlib


class NodeStatus(Enum):
    ACTIVE_MAIN = "active_main"
    ACTIVE_BRANCH = "active_branch"
    DORMANT = "dormant"
    ARCHIVED = "archived"


class NodeType(Enum):
    FILE = "file"
    MODULE = "module"
    PACKAGE = "package"
    DIRECTORY = "directory"


class EdgeType(Enum):
    IMPORTS = "imports"
    CALLS = "calls"
    READS = "reads"
    WRITES = "writes"
    DEPENDS_ON = "depends_on"
    CONTAINS = "contains"


class FlowType(Enum):
    DATA = "data"
    CONTROL = "control"
    DEPENDENCY = "dependency"


class EdgeStatus(Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    ABANDONED = "abandoned"


class ExecutionStatus(Enum):
    UNKNOWN = "unknown"
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"
    BLOCKED = "blocked"
    PENDING = "pending"


class DecisionType(Enum):
    PARAMETER = "parameter"
    ARCHITECTURE = "architecture"
    ALGORITHM = "algorithm"
    ABANDONED = "abandoned"
    MILESTONE = "milestone"
    FAILURE = "failure"
    METHOD_SELECTION = "method_selection"
    PARAMETER_DETERMINATION = "parameter_determination"
    ARCHITECTURE_TRADEOFF = "architecture_tradeoff"
    PATH_ABANDONMENT = "path_abandonment"


class DecisionSource(Enum):
    CODE_COMMENT = "code_comment"
    GIT_COMMIT = "git_commit"
    AI_CHAT = "ai_chat"
    MANUAL = "manual"
    AUTO_INFERRED = "auto_inferred"


class DecisionResult(Enum):
    ADOPTED = "adopted"
    ABANDONED = "abandoned"
    PENDING = "pending"
    DEFERRED = "deferred"


class InferenceSource(Enum):
    UNKNOWN = "unknown"
    LLM = "llm"
    RULE = "rule"
    MANUAL = "manual"
    GIT = "git"


@dataclass
class TechTag:
    """技术标签"""
    name: str
    category: str
    domain: str
    confidence: float = 1.0
    decision_id: Optional[str] = None
    source: str = "auto"
    line_number: Optional[int] = None

    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "category": self.category,
            "domain": self.domain,
        }
        if self.confidence != 1.0:
            result["confidence"] = self.confidence
        if self.decision_id:
            result["decision_id"] = self.decision_id
        if self.source != "auto":
            result["source"] = self.source
        if self.line_number:
            result["line_number"] = self.line_number
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "TechTag":
        return cls(
            name=data["name"],
            category=data["category"],
            domain=data["domain"],
            confidence=data.get("confidence", 1.0),
            decision_id=data.get("decision_id"),
            source=data.get("source", "auto"),
            line_number=data.get("line_number"),
        )


@dataclass
class Artifact:
    """产出物"""
    name: str
    file_path: str
    artifact_type: str
    size: int = 0
    created_at: Optional[datetime] = None
    description: str = ""

    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "file_path": self.file_path,
            "artifact_type": self.artifact_type,
        }
        if self.size > 0:
            result["size"] = self.size
        if self.created_at:
            result["created_at"] = self.created_at.isoformat()
        if self.description:
            result["description"] = self.description
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Artifact":
        return cls(
            name=data["name"],
            file_path=data["file_path"],
            artifact_type=data["artifact_type"],
            size=data.get("size", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            description=data.get("description", ""),
        )


@dataclass
class FailureInfo:
    """失败信息"""
    error_type: str
    error_message: str
    occurred_at: datetime
    stack_trace: str = ""
    attempted_solutions: list[str] = field(default_factory=list)
    resolved: bool = False
    resolution: str = ""

    def to_dict(self) -> dict:
        result = {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "occurred_at": self.occurred_at.isoformat(),
        }
        if self.stack_trace:
            result["stack_trace"] = self.stack_trace
        if self.attempted_solutions:
            result["attempted_solutions"] = self.attempted_solutions
        if self.resolved:
            result["resolved"] = self.resolved
        if self.resolution:
            result["resolution"] = self.resolution
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "FailureInfo":
        return cls(
            error_type=data["error_type"],
            error_message=data["error_message"],
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            stack_trace=data.get("stack_trace", ""),
            attempted_solutions=data.get("attempted_solutions", []),
            resolved=data.get("resolved", False),
            resolution=data.get("resolution", ""),
        )


@dataclass
class TodoItem:
    """待办事项"""
    id: str
    content: str
    priority: str = "medium"
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "content": self.content,
        }
        if self.priority != "medium":
            result["priority"] = self.priority
        if self.status != "pending":
            result["status"] = self.status
        result["created_at"] = self.created_at.isoformat()
        if self.due_date:
            result["due_date"] = self.due_date.isoformat()
        if self.completed_at:
            result["completed_at"] = self.completed_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "TodoItem":
        return cls(
            id=data["id"],
            content=data["content"],
            priority=data.get("priority", "medium"),
            status=data.get("status", "pending"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            due_date=datetime.fromisoformat(data["due_date"]) if data.get("due_date") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


@dataclass
class AbandonInfo:
    """废弃信息（用于废线节点）"""
    abandoned_method: str
    abandon_reason: str
    attempted_solutions: list[str] = field(default_factory=list)
    can_revive: bool = True
    revive_condition: str = ""
    abandoned_at: datetime = field(default_factory=datetime.now)
    abandoned_by: str = ""

    def to_dict(self) -> dict:
        result = {
            "abandoned_method": self.abandoned_method,
            "abandon_reason": self.abandon_reason,
        }
        if self.attempted_solutions:
            result["attempted_solutions"] = self.attempted_solutions
        if not self.can_revive:
            result["can_revive"] = self.can_revive
        if self.revive_condition:
            result["revive_condition"] = self.revive_condition
        result["abandoned_at"] = self.abandoned_at.isoformat()
        if self.abandoned_by:
            result["abandoned_by"] = self.abandoned_by
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "AbandonInfo":
        return cls(
            abandoned_method=data["abandoned_method"],
            abandon_reason=data["abandon_reason"],
            attempted_solutions=data.get("attempted_solutions", []),
            can_revive=data.get("can_revive", True),
            revive_condition=data.get("revive_condition", ""),
            abandoned_at=datetime.fromisoformat(data["abandoned_at"]) if data.get("abandoned_at") else datetime.now(),
            abandoned_by=data.get("abandoned_by", ""),
        )


@dataclass
class Alternative:
    name: str
    reason_rejected: Optional[str] = None

    def to_dict(self) -> dict:
        result = {"name": self.name}
        if self.reason_rejected:
            result["reason_rejected"] = self.reason_rejected
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Alternative":
        return cls(
            name=data["name"],
            reason_rejected=data.get("reason_rejected"),
        )


@dataclass
class FollowUp:
    """后续跟进"""
    follow_up_type: str
    description: str
    trigger_condition: str = ""
    due_date: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed: bool = False
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        result = {
            "follow_up_type": self.follow_up_type,
            "description": self.description,
        }
        if self.trigger_condition:
            result["trigger_condition"] = self.trigger_condition
        if self.due_date:
            result["due_date"] = self.due_date.isoformat()
        result["created_at"] = self.created_at.isoformat()
        if self.completed:
            result["completed"] = self.completed
        if self.completed_at:
            result["completed_at"] = self.completed_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "FollowUp":
        return cls(
            follow_up_type=data["follow_up_type"],
            description=data["description"],
            trigger_condition=data.get("trigger_condition", ""),
            due_date=datetime.fromisoformat(data["due_date"]) if data.get("due_date") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            completed=data.get("completed", False),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


@dataclass
class Decision:
    id: str
    node_id: str
    type: DecisionType
    content: str
    timestamp: datetime
    reason: Optional[str] = None
    alternatives: list[Alternative] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    source: DecisionSource = DecisionSource.MANUAL
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    decision_result: DecisionResult = DecisionResult.ADOPTED
    decision_basis: str = ""
    follow_ups: list[FollowUp] = field(default_factory=list)
    tech_tag: Optional[str] = None
    related_decisions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "node_id": self.node_id,
            "type": self.type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.reason:
            result["reason"] = self.reason
        if self.alternatives:
            result["alternatives"] = [a.to_dict() for a in self.alternatives]
        if self.parameters:
            result["parameters"] = self.parameters
        if self.source != DecisionSource.MANUAL:
            result["source"] = self.source.value
        if self.file_path:
            result["file_path"] = self.file_path
        if self.line_number:
            result["line_number"] = self.line_number
        if self.decision_result != DecisionResult.ADOPTED:
            result["decision_result"] = self.decision_result.value
        if self.decision_basis:
            result["decision_basis"] = self.decision_basis
        if self.follow_ups:
            result["follow_ups"] = [f.to_dict() for f in self.follow_ups]
        if self.tech_tag:
            result["tech_tag"] = self.tech_tag
        if self.related_decisions:
            result["related_decisions"] = self.related_decisions
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Decision":
        return cls(
            id=data["id"],
            node_id=data["node_id"],
            type=DecisionType(data["type"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            reason=data.get("reason"),
            alternatives=[Alternative.from_dict(a) for a in data.get("alternatives", [])],
            parameters=data.get("parameters", {}),
            source=DecisionSource(data.get("source", "manual")),
            file_path=data.get("file_path"),
            line_number=data.get("line_number"),
            decision_result=DecisionResult(data.get("decision_result", "adopted")),
            decision_basis=data.get("decision_basis", ""),
            follow_ups=[FollowUp.from_dict(f) for f in data.get("follow_ups", [])],
            tech_tag=data.get("tech_tag"),
            related_decisions=data.get("related_decisions", []),
        )


@dataclass
class Node:
    id: str
    name: str
    file_path: str
    status: NodeStatus
    file_name: Optional[str] = None
    type: NodeType = NodeType.FILE
    function_tags: list[str] = field(default_factory=list)
    description: Optional[str] = None
    is_entry: bool = False
    language: Optional[str] = None
    children: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    execution_status: ExecutionStatus = ExecutionStatus.UNKNOWN
    input_sources: list[str] = field(default_factory=list)
    output_targets: list[str] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    failure_info: Optional[FailureInfo] = None
    next_steps: list[str] = field(default_factory=list)
    todos: list[TodoItem] = field(default_factory=list)
    tech_tags: list[TechTag] = field(default_factory=list)
    inferred_by: InferenceSource = InferenceSource.UNKNOWN
    confidence: float = 0.0
    needs_confirmation: bool = False
    abandon_info: Optional[AbandonInfo] = None
    main_file: bool = True
    status_changed_at: Optional[datetime] = None
    status_changed_reason: str = ""

    def __post_init__(self):
        if self.file_name is None:
            import os
            self.file_name = os.path.basename(self.file_path)
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "file_path": self.file_path,
            "status": self.status.value,
        }
        if self.file_name:
            result["file_name"] = self.file_name
        if self.type != NodeType.FILE:
            result["type"] = self.type.value
        if self.function_tags:
            result["function_tags"] = self.function_tags
        if self.description:
            result["description"] = self.description
        if self.is_entry:
            result["is_entry"] = self.is_entry
        if self.language:
            result["language"] = self.language
        if self.children:
            result["children"] = self.children
        if self.exports:
            result["exports"] = self.exports
        if self.imports:
            result["imports"] = self.imports
        if self.created_at:
            result["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            result["updated_at"] = self.updated_at.isoformat()
        if self.execution_status != ExecutionStatus.UNKNOWN:
            result["execution_status"] = self.execution_status.value
        if self.input_sources:
            result["input_sources"] = self.input_sources
        if self.output_targets:
            result["output_targets"] = self.output_targets
        if self.artifacts:
            result["artifacts"] = [a.to_dict() for a in self.artifacts]
        if self.failure_info:
            result["failure_info"] = self.failure_info.to_dict()
        if self.next_steps:
            result["next_steps"] = self.next_steps
        if self.todos:
            result["todos"] = [t.to_dict() for t in self.todos]
        if self.tech_tags:
            result["tech_tags"] = [t.to_dict() for t in self.tech_tags]
        if self.inferred_by != InferenceSource.UNKNOWN:
            result["inferred_by"] = self.inferred_by.value
        if self.confidence > 0:
            result["confidence"] = self.confidence
        if self.needs_confirmation:
            result["needs_confirmation"] = self.needs_confirmation
        if self.abandon_info:
            result["abandon_info"] = self.abandon_info.to_dict()
        if not self.main_file:
            result["main_file"] = self.main_file
        if self.status_changed_at:
            result["status_changed_at"] = self.status_changed_at.isoformat()
        if self.status_changed_reason:
            result["status_changed_reason"] = self.status_changed_reason
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        return cls(
            id=data["id"],
            name=data["name"],
            file_path=data["file_path"],
            status=NodeStatus(data["status"]),
            file_name=data.get("file_name"),
            type=NodeType(data.get("type", "file")),
            function_tags=data.get("function_tags", []),
            description=data.get("description"),
            is_entry=data.get("is_entry", False),
            language=data.get("language"),
            children=data.get("children", []),
            exports=data.get("exports", []),
            imports=data.get("imports", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            execution_status=ExecutionStatus(data.get("execution_status", "unknown")),
            input_sources=data.get("input_sources", []),
            output_targets=data.get("output_targets", []),
            artifacts=[Artifact.from_dict(a) for a in data.get("artifacts", [])],
            failure_info=FailureInfo.from_dict(data["failure_info"]) if data.get("failure_info") else None,
            next_steps=data.get("next_steps", []),
            todos=[TodoItem.from_dict(t) for t in data.get("todos", [])],
            tech_tags=[TechTag.from_dict(t) for t in data.get("tech_tags", [])],
            inferred_by=InferenceSource(data.get("inferred_by", "unknown")),
            confidence=data.get("confidence", 0.0),
            needs_confirmation=data.get("needs_confirmation", False),
            abandon_info=AbandonInfo.from_dict(data["abandon_info"]) if data.get("abandon_info") else None,
            main_file=data.get("main_file", True),
            status_changed_at=datetime.fromisoformat(data["status_changed_at"]) if data.get("status_changed_at") else None,
            status_changed_reason=data.get("status_changed_reason", ""),
        )


@dataclass
class Edge:
    id: str
    source: str
    target: str
    type: EdgeType
    description: Optional[str] = None
    decision_id: Optional[str] = None
    weight: float = 1.0
    flow_type: FlowType = FlowType.DEPENDENCY
    flow_label: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    edge_status: EdgeStatus = EdgeStatus.ACTIVE
    status_changed_at: Optional[datetime] = None
    abandon_reason: str = ""

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "type": self.type.value,
        }
        if self.description:
            result["description"] = self.description
        if self.decision_id:
            result["decision_id"] = self.decision_id
        if self.weight != 1.0:
            result["weight"] = self.weight
        if self.flow_type != FlowType.DEPENDENCY:
            result["flow_type"] = self.flow_type.value
        if self.flow_label:
            result["flow_label"] = self.flow_label
        if self.parameters:
            result["parameters"] = self.parameters
        if self.edge_status != EdgeStatus.ACTIVE:
            result["edge_status"] = self.edge_status.value
        if self.status_changed_at:
            result["status_changed_at"] = self.status_changed_at.isoformat()
        if self.abandon_reason:
            result["abandon_reason"] = self.abandon_reason
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Edge":
        return cls(
            id=data["id"],
            source=data["source"],
            target=data["target"],
            type=EdgeType(data["type"]),
            description=data.get("description"),
            decision_id=data.get("decision_id"),
            weight=data.get("weight", 1.0),
            flow_type=FlowType(data.get("flow_type", "dependency")),
            flow_label=data.get("flow_label", ""),
            parameters=data.get("parameters", {}),
            edge_status=EdgeStatus(data.get("edge_status", "active")),
            status_changed_at=datetime.fromisoformat(data["status_changed_at"]) if data.get("status_changed_at") else None,
            abandon_reason=data.get("abandon_reason", ""),
        )


@dataclass
class ActiveState:
    active_main: Optional[str] = None
    active_branches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {}
        if self.active_main:
            result["active_main"] = self.active_main
        if self.active_branches:
            result["active_branches"] = self.active_branches
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ActiveState":
        return cls(
            active_main=data.get("active_main"),
            active_branches=data.get("active_branches", []),
        )


@dataclass
class GeneratorInfo:
    name: str = "projmap-cli"
    version: str = "0.1.0"

    def to_dict(self) -> dict:
        return {"name": self.name, "version": self.version}

    @classmethod
    def from_dict(cls, data: dict) -> "GeneratorInfo":
        return cls(
            name=data.get("name", "projmap-cli"),
            version=data.get("version", "0.1.0"),
        )


@dataclass
class Metadata:
    project_name: str
    project_root: str
    created_at: datetime
    description: Optional[str] = None
    updated_at: Optional[datetime] = None
    generator: Optional[GeneratorInfo] = None
    trust_level: int = 1
    llm_model: Optional[str] = None

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = self.created_at
        if self.generator is None:
            self.generator = GeneratorInfo()

    def to_dict(self) -> dict:
        result = {
            "project_name": self.project_name,
            "project_root": self.project_root,
            "created_at": self.created_at.isoformat(),
        }
        if self.description:
            result["description"] = self.description
        if self.updated_at:
            result["updated_at"] = self.updated_at.isoformat()
        if self.generator:
            result["generator"] = self.generator.to_dict()
        if self.trust_level != 1:
            result["trust_level"] = self.trust_level
        if self.llm_model:
            result["llm_model"] = self.llm_model
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Metadata":
        return cls(
            project_name=data["project_name"],
            project_root=data["project_root"],
            created_at=datetime.fromisoformat(data["created_at"]),
            description=data.get("description"),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            generator=GeneratorInfo.from_dict(data["generator"]) if data.get("generator") else None,
            trust_level=data.get("trust_level", 1),
            llm_model=data.get("llm_model"),
        )


@dataclass
class ProjMap:
    version: str = "1.1"
    metadata: Optional[Metadata] = None
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    active_state: Optional[ActiveState] = None

    def to_dict(self) -> dict:
        result = {"version": self.version}
        if self.metadata:
            result["metadata"] = self.metadata.to_dict()
        result["nodes"] = [n.to_dict() for n in self.nodes]
        result["edges"] = [e.to_dict() for e in self.edges]
        if self.decisions:
            result["decisions"] = [d.to_dict() for d in self.decisions]
        if self.active_state:
            result["active_state"] = self.active_state.to_dict()
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "ProjMap":
        return cls(
            version=data.get("version", "1.0"),
            metadata=Metadata.from_dict(data["metadata"]) if data.get("metadata") else None,
            nodes=[Node.from_dict(n) for n in data.get("nodes", [])],
            edges=[Edge.from_dict(e) for e in data.get("edges", [])],
            decisions=[Decision.from_dict(d) for d in data.get("decisions", [])],
            active_state=ActiveState.from_dict(data["active_state"]) if data.get("active_state") else None,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ProjMap":
        return cls.from_dict(json.loads(json_str))

    def save(self, file_path: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, file_path: str) -> "ProjMap":
        with open(file_path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())


def generate_node_id(file_path: str) -> str:
    return "node_" + hashlib.md5(file_path.encode()).hexdigest()[:12]


def generate_edge_id(source_id: str, target_id: str, edge_type: EdgeType) -> str:
    combined = f"{source_id}_{target_id}_{edge_type.value}"
    return "edge_" + hashlib.md5(combined.encode()).hexdigest()[:12]


def generate_decision_id(node_id: str, decision_type: DecisionType) -> str:
    timestamp = datetime.now().isoformat()
    combined = f"{node_id}_{decision_type.value}_{timestamp}"
    return "decision_" + hashlib.md5(combined.encode()).hexdigest()[:12]


def generate_todo_id() -> str:
    timestamp = datetime.now().isoformat()
    return "todo_" + hashlib.md5(timestamp.encode()).hexdigest()[:8]
