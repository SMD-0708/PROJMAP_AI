"""协作功能模块

支持多用户决策评审、评论和知识共享。
核心特性：
- 多用户支持：区分不同用户的操作
- 决策评审：决策需要多人审核批准
- 评论系统：对节点和决策进行讨论
- 变更追踪：记录谁做了什么修改
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional
from uuid import uuid4

from projmap.models import ProjMap, Decision, DecisionType

logger = logging.getLogger(__name__)


class ReviewStatus(Enum):
    """评审状态"""
    PENDING = auto()      # 待评审
    APPROVED = auto()     # 已批准
    REJECTED = auto()     # 已拒绝
    REQUESTED_CHANGES = auto()  # 需要修改


class CommentTargetType(Enum):
    """评论目标类型"""
    NODE = "node"
    DECISION = "decision"
    EDGE = "edge"
    PROJECT = "project"


@dataclass
class User:
    """用户信息"""
    user_id: str
    name: str
    email: str
    role: str = "member"  # admin, member, viewer
    avatar_url: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Comment:
    """评论"""
    comment_id: str
    target_type: CommentTargetType
    target_id: str
    author: User
    content: str
    parent_id: Optional[str] = None  # 回复的评论ID
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    reactions: dict = field(default_factory=dict)  # emoji -> count
    resolved: bool = False


@dataclass
class DecisionReview:
    """决策评审"""
    review_id: str
    decision_id: str
    reviewer: User
    status: ReviewStatus
    comment: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None


@dataclass
class ChangeRecord:
    """变更记录"""
    change_id: str
    user: User
    action: str  # create, update, delete
    target_type: str  # node, decision, edge, etc.
    target_id: str
    old_value: Optional[dict] = None
    new_value: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.now)
    reason: str = ""


class CollaborationManager:
    """协作管理器"""
    
    def __init__(
        self,
        projmap: ProjMap,
        data_dir: str = ".projmap/collaboration",
    ):
        self.projmap = projmap
        self.data_dir = data_dir
        
        # 内存数据
        self._users: dict[str, User] = {}
        self._comments: list[Comment] = []
        self._reviews: list[DecisionReview] = []
        self._changes: list[ChangeRecord] = []
        
        # 当前用户
        self._current_user: Optional[User] = None
        
        # 加载数据
        self._load_data()
        
        self._logger = logging.getLogger("projmap.collaboration")
    
    def _load_data(self):
        """加载协作数据"""
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 加载用户
        users_file = os.path.join(self.data_dir, "users.json")
        if os.path.exists(users_file):
            try:
                with open(users_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._users = {
                    u["user_id"]: User(
                        user_id=u["user_id"],
                        name=u["name"],
                        email=u["email"],
                        role=u.get("role", "member"),
                        avatar_url=u.get("avatar_url", ""),
                        created_at=datetime.fromisoformat(u["created_at"]),
                    )
                    for u in data.get("users", [])
                }
            except Exception as e:
                self._logger.warning(f"加载用户数据失败: {e}")
        
        # 加载评论
        comments_file = os.path.join(self.data_dir, "comments.json")
        if os.path.exists(comments_file):
            try:
                with open(comments_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._comments = [
                    Comment(
                        comment_id=c["comment_id"],
                        target_type=CommentTargetType(c["target_type"]),
                        target_id=c["target_id"],
                        author=self._users.get(c["author_id"], User("unknown", "Unknown", "")),
                        content=c["content"],
                        parent_id=c.get("parent_id"),
                        created_at=datetime.fromisoformat(c["created_at"]),
                        updated_at=datetime.fromisoformat(c["updated_at"]) if c.get("updated_at") else None,
                        reactions=c.get("reactions", {}),
                        resolved=c.get("resolved", False),
                    )
                    for c in data.get("comments", [])
                ]
            except Exception as e:
                self._logger.warning(f"加载评论失败: {e}")
        
        # 加载评审
        reviews_file = os.path.join(self.data_dir, "reviews.json")
        if os.path.exists(reviews_file):
            try:
                with open(reviews_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._reviews = [
                    DecisionReview(
                        review_id=r["review_id"],
                        decision_id=r["decision_id"],
                        reviewer=self._users.get(r["reviewer_id"], User("unknown", "Unknown", "")),
                        status=ReviewStatus[r["status"]],
                        comment=r.get("comment", ""),
                        created_at=datetime.fromisoformat(r["created_at"]),
                        updated_at=datetime.fromisoformat(r["updated_at"]) if r.get("updated_at") else None,
                    )
                    for r in data.get("reviews", [])
                ]
            except Exception as e:
                self._logger.warning(f"加载评审失败: {e}")
    
    def _save_data(self):
        """保存协作数据"""
        try:
            # 保存用户
            users_file = os.path.join(self.data_dir, "users.json")
            with open(users_file, "w", encoding="utf-8") as f:
                json.dump({
                    "users": [
                        {
                            "user_id": u.user_id,
                            "name": u.name,
                            "email": u.email,
                            "role": u.role,
                            "avatar_url": u.avatar_url,
                            "created_at": u.created_at.isoformat(),
                        }
                        for u in self._users.values()
                    ],
                }, f, ensure_ascii=False, indent=2)
            
            # 保存评论
            comments_file = os.path.join(self.data_dir, "comments.json")
            with open(comments_file, "w", encoding="utf-8") as f:
                json.dump({
                    "comments": [
                        {
                            "comment_id": c.comment_id,
                            "target_type": c.target_type.value,
                            "target_id": c.target_id,
                            "author_id": c.author.user_id,
                            "content": c.content,
                            "parent_id": c.parent_id,
                            "created_at": c.created_at.isoformat(),
                            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                            "reactions": c.reactions,
                            "resolved": c.resolved,
                        }
                        for c in self._comments
                    ],
                }, f, ensure_ascii=False, indent=2)
            
            # 保存评审
            reviews_file = os.path.join(self.data_dir, "reviews.json")
            with open(reviews_file, "w", encoding="utf-8") as f:
                json.dump({
                    "reviews": [
                        {
                            "review_id": r.review_id,
                            "decision_id": r.decision_id,
                            "reviewer_id": r.reviewer.user_id,
                            "status": r.status.name,
                            "comment": r.comment,
                            "created_at": r.created_at.isoformat(),
                            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                        }
                        for r in self._reviews
                    ],
                }, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            self._logger.error(f"保存协作数据失败: {e}")
    
    # ========== 用户管理 ==========
    
    def set_current_user(self, user: User):
        """设置当前用户"""
        self._current_user = user
        self._users[user.user_id] = user
        self._save_data()
    
    def get_current_user(self) -> Optional[User]:
        """获取当前用户"""
        return self._current_user
    
    def add_user(self, name: str, email: str, role: str = "member") -> User:
        """添加用户"""
        user = User(
            user_id=str(uuid4())[:8],
            name=name,
            email=email,
            role=role,
        )
        self._users[user.user_id] = user
        self._save_data()
        return user
    
    def get_users(self) -> list[User]:
        """获取所有用户"""
        return list(self._users.values())
    
    # ========== 评论功能 ==========
    
    def add_comment(
        self,
        target_type: CommentTargetType,
        target_id: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> Comment:
        """添加评论"""
        if not self._current_user:
            raise ValueError("未设置当前用户")
        
        comment = Comment(
            comment_id=str(uuid4())[:12],
            target_type=target_type,
            target_id=target_id,
            author=self._current_user,
            content=content,
            parent_id=parent_id,
        )
        
        self._comments.append(comment)
        self._save_data()
        
        self._logger.info(f"添加评论: {comment.comment_id}")
        return comment
    
    def get_comments(
        self,
        target_type: Optional[CommentTargetType] = None,
        target_id: Optional[str] = None,
        include_resolved: bool = True,
    ) -> list[Comment]:
        """获取评论"""
        comments = self._comments
        
        if target_type:
            comments = [c for c in comments if c.target_type == target_type]
        
        if target_id:
            comments = [c for c in comments if c.target_id == target_id]
        
        if not include_resolved:
            comments = [c for c in comments if not c.resolved]
        
        return sorted(comments, key=lambda c: c.created_at)
    
    def resolve_comment(self, comment_id: str) -> bool:
        """解决评论"""
        for comment in self._comments:
            if comment.comment_id == comment_id:
                comment.resolved = True
                self._save_data()
                return True
        return False
    
    # ========== 决策评审 ==========
    
    def request_review(self, decision_id: str, reviewers: list[str]) -> list[DecisionReview]:
        """请求决策评审
        
        Args:
            decision_id: 决策ID
            reviewers: 评审人用户ID列表
        
        Returns:
            创建的评审列表
        """
        reviews = []
        
        for reviewer_id in reviewers:
            if reviewer_id not in self._users:
                continue
            
            review = DecisionReview(
                review_id=str(uuid4())[:12],
                decision_id=decision_id,
                reviewer=self._users[reviewer_id],
                status=ReviewStatus.PENDING,
            )
            
            self._reviews.append(review)
            reviews.append(review)
        
        self._save_data()
        self._logger.info(f"为决策 {decision_id} 创建 {len(reviews)} 个评审请求")
        
        return reviews
    
    def submit_review(
        self,
        review_id: str,
        status: ReviewStatus,
        comment: str = "",
    ) -> bool:
        """提交评审"""
        if not self._current_user:
            raise ValueError("未设置当前用户")
        
        for review in self._reviews:
            if review.review_id == review_id:
                # 检查是否是评审人
                if review.reviewer.user_id != self._current_user.user_id:
                    raise PermissionError("只有评审人可以提交评审")
                
                review.status = status
                review.comment = comment
                review.updated_at = datetime.now()
                
                self._save_data()
                self._logger.info(f"提交评审: {review_id} -> {status.name}")
                return True
        
        return False
    
    def get_decision_status(self, decision_id: str) -> dict:
        """获取决策评审状态"""
        reviews = [r for r in self._reviews if r.decision_id == decision_id]
        
        if not reviews:
            return {"status": "no_review", "approved_count": 0, "total": 0}
        
        approved = sum(1 for r in reviews if r.status == ReviewStatus.APPROVED)
        rejected = sum(1 for r in reviews if r.status == ReviewStatus.REJECTED)
        pending = sum(1 for r in reviews if r.status == ReviewStatus.PENDING)
        
        # 判断是否通过（简单多数）
        if approved > len(reviews) / 2:
            status = "approved"
        elif rejected > len(reviews) / 2:
            status = "rejected"
        else:
            status = "pending"
        
        return {
            "status": status,
            "approved_count": approved,
            "rejected_count": rejected,
            "pending_count": pending,
            "total": len(reviews),
            "reviews": [
                {
                    "reviewer": r.reviewer.name,
                    "status": r.status.name,
                    "comment": r.comment,
                }
                for r in reviews
            ],
        }
    
    # ========== 变更追踪 ==========
    
    def record_change(
        self,
        action: str,
        target_type: str,
        target_id: str,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        reason: str = "",
    ) -> ChangeRecord:
        """记录变更"""
        if not self._current_user:
            raise ValueError("未设置当前用户")
        
        record = ChangeRecord(
            change_id=str(uuid4())[:12],
            user=self._current_user,
            action=action,
            target_type=target_type,
            target_id=target_id,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
        
        self._changes.append(record)
        
        # 只保留最近1000条变更记录
        if len(self._changes) > 1000:
            self._changes = self._changes[-1000:]
        
        self._logger.info(f"记录变更: {action} {target_type} {target_id}")
        return record
    
    def get_changes(
        self,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[ChangeRecord]:
        """获取变更记录"""
        changes = self._changes
        
        if target_type:
            changes = [c for c in changes if c.target_type == target_type]
        
        if target_id:
            changes = [c for c in changes if c.target_id == target_id]
        
        if user_id:
            changes = [c for c in changes if c.user.user_id == user_id]
        
        return sorted(changes, key=lambda c: c.timestamp, reverse=True)[:limit]
    
    # ========== 统计信息 ==========
    
    def get_statistics(self) -> dict:
        """获取协作统计"""
        return {
            "users": len(self._users),
            "comments": len(self._comments),
            "pending_reviews": len([r for r in self._reviews if r.status == ReviewStatus.PENDING]),
            "total_changes": len(self._changes),
            "unresolved_comments": len([c for c in self._comments if not c.resolved]),
        }
