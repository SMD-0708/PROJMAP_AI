"""工作区管理器

解决"迷失症"痛点：中断后忘记进度
提供会话管理、进度保存和恢复功能。
"""

import os
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Optional
from pathlib import Path

from projmap.models import ProjMap, Node, NodeStatus


@dataclass
class WorkSession:
    """工作会话"""
    session_id: str
    started_at: datetime
    last_active_at: datetime
    active_nodes: list[str] = field(default_factory=list)  # 当前活跃的节点ID
    context_notes: str = ""  # 上下文笔记
    tasks: list[dict] = field(default_factory=list)  # 待办任务
    bookmarks: list[str] = field(default_factory=list)  # 书签
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat(),
            "active_nodes": self.active_nodes,
            "context_notes": self.context_notes,
            "tasks": self.tasks,
            "bookmarks": self.bookmarks,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "WorkSession":
        return cls(
            session_id=data["session_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            last_active_at=datetime.fromisoformat(data["last_active_at"]),
            active_nodes=data.get("active_nodes", []),
            context_notes=data.get("context_notes", ""),
            tasks=data.get("tasks", []),
            bookmarks=data.get("bookmarks", []),
        )


@dataclass
class ProgressCheckpoint:
    """进度检查点"""
    checkpoint_id: str
    timestamp: datetime
    description: str
    active_main: Optional[str] = None
    active_branches: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    notes: str = ""


class WorkspaceManager:
    """工作区管理器
    
    管理工作会话和进度，确保中断后能快速恢复工作状态。
    核心功能：
    - 会话管理（开始、暂停、恢复）
    - 进度检查点
    - 上下文笔记
    - 任务追踪
    """
    
    def __init__(self, projmap: ProjMap, workspace_dir: Optional[str] = None):
        self.projmap = projmap
        self.workspace_dir = workspace_dir or os.path.join(
            os.path.dirname(projmap.metadata.file_path) if projmap.metadata.file_path else ".",
            ".projmap",
            "workspace"
        )
        self._ensure_workspace_dir()
        
        self.current_session: Optional[WorkSession] = None
        self._sessions: list[WorkSession] = []
        self._checkpoints: list[ProgressCheckpoint] = []
        
        self._load_sessions()
    
    def _ensure_workspace_dir(self):
        """确保工作区目录存在"""
        if not os.path.exists(self.workspace_dir):
            os.makedirs(self.workspace_dir, exist_ok=True)
    
    def _get_sessions_file(self) -> str:
        """获取会话文件路径"""
        return os.path.join(self.workspace_dir, "sessions.json")
    
    def _load_sessions(self):
        """加载会话历史"""
        sessions_file = self._get_sessions_file()
        if os.path.exists(sessions_file):
            try:
                with open(sessions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._sessions = [WorkSession.from_dict(s) for s in data.get("sessions", [])]
            except Exception:
                self._sessions = []
    
    def _save_sessions(self):
        """保存会话历史"""
        sessions_file = self._get_sessions_file()
        data = {
            "sessions": [s.to_dict() for s in self._sessions],
            "current_session": self.current_session.to_dict() if self.current_session else None,
        }
        with open(sessions_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def start_session(self, context_notes: str = "") -> WorkSession:
        """开始新会话"""
        import uuid
        
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now()
        
        # 获取当前活跃的节点
        active_nodes = [
            n.id for n in self.projmap.nodes
            if n.status in (NodeStatus.ACTIVE_MAIN, NodeStatus.ACTIVE_BRANCH)
        ]
        
        session = WorkSession(
            session_id=session_id,
            started_at=now,
            last_active_at=now,
            active_nodes=active_nodes,
            context_notes=context_notes,
        )
        
        self.current_session = session
        self._sessions.append(session)
        self._save_sessions()
        
        return session
    
    def resume_session(self, session_id: str) -> Optional[WorkSession]:
        """恢复历史会话"""
        for session in self._sessions:
            if session.session_id == session_id:
                session.last_active_at = datetime.now()
                self.current_session = session
                self._save_sessions()
                return session
        return None
    
    def end_session(self, notes: str = ""):
        """结束当前会话"""
        if self.current_session:
            self.current_session.context_notes += f"\n[结束备注] {notes}"
            self.current_session.last_active_at = datetime.now()
            self._save_sessions()
            self.current_session = None
    
    def update_progress(self, notes: str = ""):
        """更新当前进度"""
        if not self.current_session:
            return
        
        # 更新活跃节点
        self.current_session.active_nodes = [
            n.id for n in self.projmap.nodes
            if n.status in (NodeStatus.ACTIVE_MAIN, NodeStatus.ACTIVE_BRANCH)
        ]
        
        self.current_session.last_active_at = datetime.now()
        
        if notes:
            self.current_session.context_notes += f"\n[{datetime.now().strftime('%H:%M')}] {notes}"
        
        self._save_sessions()
    
    def add_task(self, description: str, priority: str = "medium", node_id: Optional[str] = None):
        """添加任务"""
        if not self.current_session:
            return
        
        import uuid
        task = {
            "id": str(uuid.uuid4())[:8],
            "description": description,
            "priority": priority,
            "node_id": node_id,
            "created_at": datetime.now().isoformat(),
            "completed": False,
        }
        
        self.current_session.tasks.append(task)
        self._save_sessions()
    
    def complete_task(self, task_id: str):
        """完成任务"""
        if not self.current_session:
            return
        
        for task in self.current_session.tasks:
            if task["id"] == task_id:
                task["completed"] = True
                task["completed_at"] = datetime.now().isoformat()
                break
        
        self._save_sessions()
    
    def add_bookmark(self, node_id: str, note: str = ""):
        """添加书签"""
        if not self.current_session:
            return
        
        if node_id not in self.current_session.bookmarks:
            self.current_session.bookmarks.append(node_id)
            self._save_sessions()
    
    def remove_bookmark(self, node_id: str):
        """移除书签"""
        if not self.current_session:
            return
        
        if node_id in self.current_session.bookmarks:
            self.current_session.bookmarks.remove(node_id)
            self._save_sessions()
    
    def create_checkpoint(self, description: str) -> ProgressCheckpoint:
        """创建进度检查点"""
        import uuid
        
        checkpoint_id = str(uuid.uuid4())[:8]
        
        # 获取当前状态
        active_main = None
        active_branches = []
        
        for node in self.projmap.nodes:
            if node.status == NodeStatus.ACTIVE_MAIN:
                active_main = node.id
            elif node.status == NodeStatus.ACTIVE_BRANCH:
                active_branches.append(node.id)
        
        # 获取最近修改的文件
        modified_files = []
        for node in self.projmap.nodes:
            if node.last_modified:
                if datetime.now() - node.last_modified < timedelta(hours=1):
                    modified_files.append(node.file_path)
        
        checkpoint = ProgressCheckpoint(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(),
            description=description,
            active_main=active_main,
            active_branches=active_branches,
            modified_files=modified_files,
        )
        
        self._checkpoints.append(checkpoint)
        
        # 保存检查点
        checkpoint_file = os.path.join(self.workspace_dir, f"checkpoint_{checkpoint_id}.json")
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump({
                "checkpoint_id": checkpoint.checkpoint_id,
                "timestamp": checkpoint.timestamp.isoformat(),
                "description": checkpoint.description,
                "active_main": checkpoint.active_main,
                "active_branches": checkpoint.active_branches,
                "modified_files": checkpoint.modified_files,
                "notes": checkpoint.notes,
            }, f, ensure_ascii=False, indent=2)
        
        return checkpoint
    
    def get_resume_context(self) -> dict:
        """获取恢复上下文"""
        if not self.current_session:
            # 尝试恢复最近的会话
            if self._sessions:
                recent = max(self._sessions, key=lambda s: s.last_active_at)
                return self._format_resume_context(recent)
            return {"error": "没有可恢复的会话"}
        
        return self._format_resume_context(self.current_session)
    
    def _format_resume_context(self, session: WorkSession) -> dict:
        """格式化恢复上下文"""
        # 获取节点详情
        node_map = {n.id: n for n in self.projmap.nodes}
        
        active_nodes_info = []
        for node_id in session.active_nodes:
            if node_id in node_map:
                node = node_map[node_id]
                active_nodes_info.append({
                    "id": node.id,
                    "name": node.name,
                    "file_path": node.file_path,
                    "status": node.status.value,
                })
        
        # 计算会话持续时间
        duration = datetime.now() - session.started_at
        hours = duration.total_seconds() / 3600
        
        # 获取未完成任务
        pending_tasks = [t for t in session.tasks if not t.get("completed", False)]
        
        # 获取书签节点
        bookmarks_info = []
        for node_id in session.bookmarks:
            if node_id in node_map:
                node = node_map[node_id]
                bookmarks_info.append({
                    "id": node.id,
                    "name": node.name,
                    "file_path": node.file_path,
                })
        
        return {
            "session_id": session.session_id,
            "started_at": session.started_at.isoformat(),
            "last_active_at": session.last_active_at.isoformat(),
            "duration_hours": round(hours, 2),
            "active_nodes": active_nodes_info,
            "context_notes": session.context_notes,
            "pending_tasks": pending_tasks,
            "pending_tasks_count": len(pending_tasks),
            "bookmarks": bookmarks_info,
            "can_resume": (datetime.now() - session.last_active_at) < timedelta(days=7),
        }
    
    def get_session_history(self, limit: int = 10) -> list[dict]:
        """获取会话历史"""
        sorted_sessions = sorted(
            self._sessions,
            key=lambda s: s.last_active_at,
            reverse=True,
        )[:limit]
        
        return [
            {
                "session_id": s.session_id,
                "started_at": s.started_at.isoformat(),
                "last_active_at": s.last_active_at.isoformat(),
                "context_preview": s.context_notes[:100] + "..." if len(s.context_notes) > 100 else s.context_notes,
                "tasks_count": len(s.tasks),
                "completed_tasks": len([t for t in s.tasks if t.get("completed")]),
            }
            for s in sorted_sessions
        ]
    
    def generate_daily_summary(self) -> dict:
        """生成每日工作摘要"""
        today = datetime.now().date()
        
        # 今日会话
        today_sessions = [
            s for s in self._sessions
            if s.started_at.date() == today or s.last_active_at.date() == today
        ]
        
        # 今日完成的任务
        completed_today = []
        for session in today_sessions:
            for task in session.tasks:
                if task.get("completed") and task.get("completed_at"):
                    completed_time = datetime.fromisoformat(task["completed_at"])
                    if completed_time.date() == today:
                        completed_today.append(task)
        
        # 今日创建的决策
        today_decisions = [
            d for d in self.projmap.decisions
            if d.timestamp.date() == today
        ]
        
        return {
            "date": today.isoformat(),
            "sessions_count": len(today_sessions),
            "total_work_time": sum(
                (s.last_active_at - s.started_at).total_seconds() / 3600
                for s in today_sessions
            ),
            "tasks_completed": len(completed_today),
            "decisions_made": len(today_decisions),
            "active_main": [
                {"id": n.id, "name": n.name}
                for n in self.projmap.nodes
                if n.status == NodeStatus.ACTIVE_MAIN
            ],
        }


def quick_save_progress(projmap: ProjMap, notes: str = ""):
    """便捷函数：快速保存进度"""
    manager = WorkspaceManager(projmap)
    
    if not manager.current_session:
        manager.start_session(notes)
    else:
        manager.update_progress(notes)
    
    return manager.create_checkpoint(notes or "快速保存")


def get_where_was_i(projmap: ProjMap) -> dict:
    """便捷函数：我在哪里？"""
    manager = WorkspaceManager(projmap)
    return manager.get_resume_context()
