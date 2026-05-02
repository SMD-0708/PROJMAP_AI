"""机器学习增强的导航器

使用历史数据训练模型，提供更准确的阅读路径推荐。
核心特性：
- 特征工程：从代码和项目结构中提取有意义的特征
- 模型训练：基于用户行为训练重要性预测模型
- 在线学习：持续收集反馈，模型自我改进
- 可解释性：提供推荐原因说明
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np

from projmap.models import ProjMap, Node, NodeStatus, NodeType
from projmap.project_navigator import ProjectNavigator, ReadingNode, ReadingPath

logger = logging.getLogger(__name__)


@dataclass
class NodeFeatures:
    """节点特征向量"""
    # 结构特征
    incoming_deps: int = 0  # 入度
    outgoing_deps: int = 0  # 出度
    depth_from_root: int = 0  # 距离根目录深度
    
    # 代码特征
    lines_of_code: int = 0
    comment_ratio: float = 0.0  # 注释比例
    function_count: int = 0
    class_count: int = 0
    
    # 历史特征
    modification_frequency: float = 0.0  # 修改频率
    days_since_last_modified: int = 0
    author_count: int = 0  # 贡献者数量
    
    # 语义特征
    has_description: bool = False
    keyword_matches: int = 0  # 匹配关键词数量
    function_tag_count: int = 0
    
    # 状态特征
    is_active_main: bool = False
    is_active_branch: bool = False
    is_dormant: bool = False
    
    def to_vector(self) -> np.ndarray:
        """转换为数值向量"""
        return np.array([
            self.incoming_deps,
            self.outgoing_deps,
            self.depth_from_root,
            self.lines_of_code,
            self.comment_ratio,
            self.function_count,
            self.class_count,
            self.modification_frequency,
            self.days_since_last_modified,
            self.author_count,
            int(self.has_description),
            self.keyword_matches,
            self.function_tag_count,
            int(self.is_active_main),
            int(self.is_active_branch),
            int(self.is_dormant),
        ], dtype=np.float32)
    
    @classmethod
    def from_node(cls, node: Node, projmap: ProjMap) -> "NodeFeatures":
        """从节点提取特征"""
        features = cls()
        
        # 计算依赖
        features.incoming_deps = len([
            e for e in projmap.edges if e.target == node.id
        ])
        features.outgoing_deps = len([
            e for e in projmap.edges if e.source == node.id
        ])
        
        # 计算深度
        if node.file_path:
            features.depth_from_root = len(node.file_path.split(os.sep)) - 1
        
        # 代码特征
        features.lines_of_code = node.lines_of_code or 0
        
        # 状态特征
        features.is_active_main = node.status == NodeStatus.ACTIVE_MAIN
        features.is_active_branch = node.status == NodeStatus.ACTIVE_BRANCH
        features.is_dormant = node.status == NodeStatus.DORMANT
        
        # 语义特征
        features.has_description = bool(node.description)
        features.function_tag_count = len(node.function_tags) if node.function_tags else 0
        
        # 历史特征
        if node.last_modified:
            features.days_since_last_modified = (
                datetime.now() - node.last_modified
            ).days
        
        return features


@dataclass
class UserFeedback:
    """用户反馈"""
    node_id: str
    was_helpful: bool  # 是否对理解项目有帮助
    time_spent: int  # 阅读时间（秒）
    timestamp: datetime = field(default_factory=datetime.now)
    context: str = ""  # 阅读上下文


class SimpleLinearModel:
    """简单的线性回归模型
    
    用于预测节点重要性分数。
    """
    
    def __init__(self, n_features: int = 16):
        self.weights = np.random.randn(n_features) * 0.01
        self.bias = 0.0
        self.learning_rate = 0.01
        self.training_history: list[dict] = []
    
    def predict(self, features: np.ndarray) -> float:
        """预测重要性分数"""
        return float(np.dot(features, self.weights) + self.bias)
    
    def train_step(self, features: np.ndarray, target: float):
        """单步训练"""
        prediction = self.predict(features)
        error = target - prediction
        
        # 梯度下降更新
        self.weights += self.learning_rate * error * features
        self.bias += self.learning_rate * error
        
        # 记录历史
        self.training_history.append({
            "error": abs(error),
            "prediction": prediction,
            "target": target,
        })
    
    def save(self, path: str):
        """保存模型"""
        np.savez(
            path,
            weights=self.weights,
            bias=self.bias,
            history=json.dumps(self.training_history[-100:]),  # 只保存最近100条
        )
    
    def load(self, path: str):
        """加载模型"""
        if os.path.exists(path):
            data = np.load(path)
            self.weights = data["weights"]
            self.bias = float(data["bias"])
            if "history" in data:
                self.training_history = json.loads(str(data["history"]))


class MLEnhancedNavigator(ProjectNavigator):
    """机器学习增强的项目导航器"""
    
    def __init__(
        self,
        projmap: ProjMap,
        use_cache: bool = True,
        model_path: str = ".projmap/ml_model.npz",
        feedback_path: str = ".projmap/feedback.json",
    ):
        super().__init__(projmap, use_cache)
        
        self.model_path = model_path
        self.feedback_path = feedback_path
        self.model = SimpleLinearModel()
        self.feedback_history: list[UserFeedback] = []
        
        # 加载模型和反馈
        self._load_model()
        self._load_feedback()
        
        self._logger = logging.getLogger("projmap.ml_navigator")
    
    def _load_model(self):
        """加载训练好的模型"""
        try:
            self.model.load(self.model_path)
            logger.info("ML 模型加载成功")
        except Exception as e:
            logger.warning(f"加载 ML 模型失败: {e}，使用默认权重")
    
    def _save_model(self):
        """保存模型"""
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            self.model.save(self.model_path)
            logger.info("ML 模型保存成功")
        except Exception as e:
            logger.error(f"保存 ML 模型失败: {e}")
    
    def _load_feedback(self):
        """加载用户反馈"""
        if not os.path.exists(self.feedback_path):
            return
        
        try:
            with open(self.feedback_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.feedback_history = [
                UserFeedback(
                    node_id=f["node_id"],
                    was_helpful=f["was_helpful"],
                    time_spent=f["time_spent"],
                    timestamp=datetime.fromisoformat(f["timestamp"]),
                    context=f.get("context", ""),
                )
                for f in data.get("feedbacks", [])
            ]
            
            logger.info(f"加载 {len(self.feedback_history)} 条用户反馈")
        except Exception as e:
            logger.warning(f"加载反馈失败: {e}")
    
    def _save_feedback(self):
        """保存用户反馈"""
        try:
            os.makedirs(os.path.dirname(self.feedback_path), exist_ok=True)
            data = {
                "feedbacks": [
                    {
                        "node_id": f.node_id,
                        "was_helpful": f.was_helpful,
                        "time_spent": f.time_spent,
                        "timestamp": f.timestamp.isoformat(),
                        "context": f.context,
                    }
                    for f in self.feedback_history
                ],
            }
            with open(self.feedback_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存反馈失败: {e}")
    
    def _calculate_node_importance_ml(self, node: Node) -> tuple[float, dict]:
        """使用 ML 模型计算重要性
        
        Returns:
            (重要性分数, 特征解释)
        """
        # 提取特征
        features = NodeFeatures.from_node(node, self.projmap)
        feature_vector = features.to_vector()
        
        # 模型预测
        ml_score = self.model.predict(feature_vector)
        
        # 结合规则评分（加权平均）
        rule_score = self._calculate_node_importance(node)
        
        # 如果模型训练数据少，更依赖规则
        if len(self.feedback_history) < 10:
            final_score = rule_score * 0.8 + ml_score * 0.2
        elif len(self.feedback_history) < 50:
            final_score = rule_score * 0.5 + ml_score * 0.5
        else:
            final_score = rule_score * 0.3 + ml_score * 0.7
        
        # 生成解释
        explanation = self._generate_explanation(features, ml_score, rule_score)
        
        return final_score, explanation
    
    def _generate_explanation(
        self, features: NodeFeatures, ml_score: float, rule_score: float
    ) -> dict:
        """生成推荐解释"""
        reasons = []
        
        if features.incoming_deps > 5:
            reasons.append(f"被 {features.incoming_deps} 个文件依赖")
        
        if features.is_active_main:
            reasons.append("主线活跃文件")
        
        if features.has_description:
            reasons.append("有详细文档")
        
        if features.function_tag_count > 0:
            reasons.append(f"标记为 {features.function_tag_count} 个功能模块")
        
        return {
            "ml_score": round(ml_score, 2),
            "rule_score": round(rule_score, 2),
            "reasons": reasons,
            "top_features": {
                "incoming_deps": features.incoming_deps,
                "lines_of_code": features.lines_of_code,
                "has_description": features.has_description,
            },
        }
    
    def get_quick_start_path_ml(self) -> ReadingPath:
        """获取 ML 增强的快速入门路径"""
        active_nodes = [
            n for n in self.projmap.nodes
            if n.status in (NodeStatus.ACTIVE_MAIN, NodeStatus.ACTIVE_BRANCH)
        ]
        
        reading_nodes = []
        for node in active_nodes:
            score, explanation = self._calculate_node_importance_ml(node)
            prerequisites = self._edge_map.get(node.id, [])
            
            rn = ReadingNode(
                node=node,
                importance_score=score,
                prerequisites=prerequisites,
            )
            # 添加解释到 notes
            rn.notes = json.dumps(explanation, ensure_ascii=False)
            reading_nodes.append(rn)
        
        reading_nodes.sort(key=lambda x: x.importance_score, reverse=True)
        ordered_nodes = self._topological_sort(reading_nodes)
        top_nodes = ordered_nodes[:15]
        
        for i, rn in enumerate(top_nodes):
            rn.reading_order = i + 1
        
        return ReadingPath(
            name="智能推荐路径 (ML增强)",
            description="基于机器学习的智能阅读路径，结合项目结构和历史反馈",
            nodes=top_nodes,
            estimated_time=len(top_nodes) * 5,
            target_audience="新加入的开发者",
        )
    
    def record_feedback(
        self,
        node_id: str,
        was_helpful: bool,
        time_spent: int = 0,
        context: str = "",
    ):
        """记录用户反馈
        
        Args:
            node_id: 节点ID
            was_helpful: 是否有帮助
            time_spent: 阅读时间（秒）
            context: 阅读上下文
        """
        feedback = UserFeedback(
            node_id=node_id,
            was_helpful=was_helpful,
            time_spent=time_spent,
            context=context,
        )
        
        self.feedback_history.append(feedback)
        self._save_feedback()
        
        # 触发模型训练
        self._train_on_feedback(feedback)
        
        logger.info(f"记录反馈: {node_id} helpful={was_helpful}")
    
    def _train_on_feedback(self, feedback: UserFeedback):
        """基于反馈训练模型"""
        # 找到对应的节点
        node = None
        for n in self.projmap.nodes:
            if n.id == feedback.node_id:
                node = n
                break
        
        if not node:
            return
        
        # 提取特征
        features = NodeFeatures.from_node(node, self.projmap)
        feature_vector = features.to_vector()
        
        # 构建目标值
        # 有帮助 -> 高重要性，无帮助 -> 低重要性
        target = 80.0 if feedback.was_helpful else 20.0
        
        # 根据阅读时间调整
        if feedback.time_spent > 300:  # 超过5分钟
            target += 10
        elif feedback.time_spent < 30:  # 少于30秒
            target -= 10
        
        target = max(0, min(100, target))  # 限制在 0-100
        
        # 训练一步
        self.model.train_step(feature_vector, target)
        
        # 保存模型
        self._save_model()
        
        logger.debug(f"模型训练: target={target:.2f}")
    
    def get_model_statistics(self) -> dict:
        """获取模型统计信息"""
        return {
            "feedback_count": len(self.feedback_history),
            "training_steps": len(self.model.training_history),
            "recent_error": (
                self.model.training_history[-1]["error"]
                if self.model.training_history else None
            ),
            "model_path": self.model_path,
            "top_weights": {
                "incoming_deps": round(self.model.weights[0], 4),
                "lines_of_code": round(self.model.weights[3], 4),
                "is_active_main": round(self.model.weights[13], 4),
            },
        }
    
    def reset_model(self):
        """重置模型"""
        self.model = SimpleLinearModel()
        self.feedback_history.clear()
        
        if os.path.exists(self.model_path):
            os.remove(self.model_path)
        if os.path.exists(self.feedback_path):
            os.remove(self.feedback_path)
        
        logger.info("模型已重置")
