"""技术标签系统

核心功能：
1. 预设词库：覆盖金融科技、科研、软件开发三大领域
2. 自动识别：扫描代码、注释、文档时命中关键词自动打标
3. 决策关联：每个技术标签可关联决策记录
4. 废线记录：废弃路径强制记录决策信息

设计原则：
- 标签是索引，决策是血肉
- 一个节点可以有多个技术标签
- 每个技术标签可以关联一条或多条关键决策记录
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from collections import defaultdict

from projmap.models import (
    ProjMap, Node, Decision, DecisionType, DecisionSource,
    TechTag, AbandonInfo, Alternative, FollowUp, NodeStatus,
    generate_decision_id, generate_todo_id,
)


TECH_TAG_VOCABULARY = {
    "fintech": {
        "factor_construction": {
            "keywords": [
                "动量因子", "momentum_factor", "momentum factor",
                "反转因子", "reversal_factor", "reversal factor",
                "波动率因子", "volatility_factor", "volatility factor",
                "价值因子", "value_factor", "value factor",
                "成长因子", "growth_factor", "growth factor",
                "质量因子", "quality_factor", "quality factor",
                "情绪因子", "sentiment_factor", "sentiment factor",
                "Alpha因子", "alpha_factor", "alpha factor",
                "Beta中性", "beta_neutral", "beta neutral",
                "IC", "Information Coefficient", "信息系数",
                "IR", "Information Ratio", "信息比率",
                "换手率", "turnover", "turnover_rate",
            ],
            "description": "因子构建相关技术",
        },
        "weight_allocation": {
            "keywords": [
                "等权重", "equal_weight", "equal weight",
                "市值加权", "market_cap_weight", "market cap weight",
                "波动率倒数", "volatility_inverse", "inverse volatility",
                "风险平价", "risk_parity",
                "均值方差", "mean_variance", "mean-variance",
                "Black-Litterman", "black litterman",
                "最大夏普", "max_sharpe", "maximum sharpe",
                "最小方差", "min_variance", "minimum variance",
                "目标波动率", "target_volatility",
                "风险预算", "risk_budget", "risk budgeting",
            ],
            "description": "权重分配方法",
        },
        "portfolio_optimization": {
            "keywords": [
                "马科维茨", "markowitz",
                "有效前沿", "efficient_frontier", "efficient frontier",
                "二次规划", "quadratic_programming", "QP",
                "CVaR", "Conditional VaR", "条件风险价值",
                "VaR", "Value at Risk", "风险价值",
                "预期亏损", "expected_shortfall",
                "蒙特卡洛", "monte_carlo", "monte carlo",
            ],
            "description": "组合优化技术",
        },
        "backtest_evaluation": {
            "keywords": [
                "回测", "backtest", "back_test", "back-test",
                "夏普比率", "sharpe_ratio", "sharpe ratio",
                "最大回撤", "max_drawdown", "maximum drawdown",
                "Calmar比率", "calmar_ratio", "calmar ratio",
                "索提诺比率", "sortino_ratio", "sortino ratio",
                "胜率", "win_rate", "win rate",
                "盈亏比", "profit_loss_ratio",
                "滑点", "slippage",
                "冲击成本", "impact_cost", "market impact",
            ],
            "description": "回测评估指标",
        },
        "risk_management": {
            "keywords": [
                "Barra", "barra",
                "多因子模型", "multi_factor", "multi-factor model",
                "协方差矩阵", "covariance_matrix", "covariance matrix",
                "风险归因", "risk_attribution", "risk attribution",
                "压力测试", "stress_test", "stress testing",
                "情景分析", "scenario_analysis", "scenario analysis",
            ],
            "description": "风险管理模型",
        },
        "trading_execution": {
            "keywords": [
                "TWAP", "twap", "Time Weighted Average Price",
                "VWAP", "vwap", "Volume Weighted Average Price",
                "冰山订单", "iceberg_order", "iceberg order",
                "算法交易", "algorithmic_trading", "algorithmic trading",
                "高频交易", "hft", "high_frequency_trading", "high frequency trading",
            ],
            "description": "交易执行算法",
        },
    },
    "research": {
        "preprocessing": {
            "keywords": [
                "缺失值填充", "missing_value", "missing value imputation",
                "异常值检测", "outlier_detection", "outlier detection",
                "标准化", "standardization", "normalize", "normalization",
                "归一化", "min_max", "min-max scaling",
                "独热编码", "one_hot", "one-hot encoding",
                "标签编码", "label_encoding", "label encoding",
                "分箱", "binning", "discretization",
                "SMOTE", "smote",
                "数据增强", "data_augmentation", "data augmentation",
            ],
            "description": "数据预处理技术",
        },
        "feature_engineering": {
            "keywords": [
                "PCA", "pca", "Principal Component Analysis",
                "t-SNE", "tsne", "t-SNE",
                "UMAP", "umap",
                "LDA", "lda", "Linear Discriminant Analysis",
                "因子分析", "factor_analysis", "factor analysis",
                "特征选择", "feature_selection", "feature selection",
                "特征交叉", "feature_cross", "feature crossing",
                "多项式特征", "polynomial_feature", "polynomial features",
                "分箱特征", "binning_feature",
            ],
            "description": "特征工程技术",
        },
        "statistical_test": {
            "keywords": [
                "t检验", "t_test", "t-test", "ttest",
                "卡方检验", "chi_square", "chi-square test",
                "方差分析", "anova", "ANOVA",
                "Mann-Whitney", "mann_whitney",
                "KS检验", "ks_test", "Kolmogorov-Smirnov",
                "正态性检验", "normality_test", "normality test",
                "相关性分析", "correlation", "correlation analysis",
                "因果推断", "causal_inference", "causal inference",
            ],
            "description": "统计检验方法",
        },
        "models": {
            "keywords": [
                "线性回归", "linear_regression", "linear regression",
                "逻辑回归", "logistic_regression", "logistic regression",
                "决策树", "decision_tree", "decision tree",
                "随机森林", "random_forest", "random forest",
                "XGBoost", "xgboost", "xgb",
                "LightGBM", "lightgbm", "lgbm",
                "CatBoost", "catboost",
                "SVM", "svm", "Support Vector Machine",
                "KNN", "knn", "K-Nearest Neighbors",
                "朴素贝叶斯", "naive_bayes", "naive bayes",
                "神经网络", "neural_network", "neural network",
                "LSTM", "lstm", "Long Short-Term Memory",
                "GRU", "gru", "Gated Recurrent Unit",
                "Transformer", "transformer",
                "BERT", "bert",
                "GPT", "gpt",
            ],
            "description": "机器学习/深度学习模型",
        },
        "model_evaluation": {
            "keywords": [
                "交叉验证", "cross_validation", "cross validation",
                "网格搜索", "grid_search", "grid search",
                "随机搜索", "random_search", "random search",
                "贝叶斯优化", "bayesian_optimization", "bayesian optimization",
                "AUC", "auc", "Area Under Curve",
                "F1", "f1", "f1_score", "f1 score",
                "准确率", "accuracy",
                "召回率", "recall",
                "精确率", "precision",
                "混淆矩阵", "confusion_matrix", "confusion matrix",
                "ROC", "roc", "ROC curve",
                "PR曲线", "pr_curve", "PR curve",
            ],
            "description": "模型评估方法",
        },
        "interpretability": {
            "keywords": [
                "SHAP", "shap", "SHapley Additive exPlanations",
                "LIME", "lime", "Local Interpretable Model",
                "特征重要性", "feature_importance", "feature importance",
                "部分依赖图", "pdp", "partial dependence plot",
                "ICE图", "ice_plot", "Individual Conditional Expectation",
            ],
            "description": "模型可解释性方法",
        },
    },
    "software": {
        "architecture": {
            "keywords": [
                "MVC", "mvc", "Model-View-Controller",
                "MVP", "mvp", "Model-View-Presenter",
                "MVVM", "mvvm", "Model-View-ViewModel",
                "微服务", "microservice", "micro-service", "micro service",
                "单体架构", "monolith", "monolithic",
                "Serverless", "serverless",
                "事件驱动", "event_driven", "event-driven",
                "CQRS", "cqrs", "Command Query Responsibility Segregation",
                "DDD", "ddd", "Domain-Driven Design",
                "分层架构", "layered_architecture", "layered architecture",
            ],
            "description": "架构模式",
        },
        "design_patterns": {
            "keywords": [
                "单例", "singleton",
                "工厂", "factory", "factory_method", "factory method",
                "抽象工厂", "abstract_factory", "abstract factory",
                "建造者", "builder",
                "原型", "prototype",
                "适配器", "adapter",
                "装饰器", "decorator",
                "代理", "proxy",
                "观察者", "observer",
                "策略", "strategy",
                "模板方法", "template_method", "template method",
                "责任链", "chain_of_responsibility", "chain of responsibility",
            ],
            "description": "设计模式",
        },
        "database": {
            "keywords": [
                "MySQL", "mysql",
                "PostgreSQL", "postgresql", "postgres",
                "MongoDB", "mongodb", "mongo",
                "Redis", "redis",
                "Elasticsearch", "elasticsearch", "es",
                "ClickHouse", "clickhouse",
                "分库分表", "sharding",
                "读写分离", "read_write_splitting",
                "索引优化", "index_optimization", "index optimization",
            ],
            "description": "数据库技术",
        },
        "middleware": {
            "keywords": [
                "Spring Boot", "springboot", "spring boot",
                "Django", "django",
                "Flask", "flask",
                "FastAPI", "fastapi",
                "React", "react",
                "Vue", "vue",
                "Nginx", "nginx",
                "Kafka", "kafka",
                "RabbitMQ", "rabbitmq",
                "Docker", "docker",
                "K8s", "k8s", "Kubernetes", "kubernetes",
            ],
            "description": "中间件和框架",
        },
        "code_quality": {
            "keywords": [
                "单元测试", "unit_test", "unit testing",
                "集成测试", "integration_test", "integration testing",
                "TDD", "tdd", "Test-Driven Development",
                "重构", "refactor", "refactoring",
                "代码审查", "code_review", "code review",
                "CI/CD", "cicd", "CI/CD pipeline",
                "Git Flow", "gitflow", "git flow",
            ],
            "description": "代码质量实践",
        },
        "performance": {
            "keywords": [
                "缓存", "cache", "caching",
                "异步", "async", "asynchronous",
                "并发", "concurrent", "concurrency",
                "多线程", "multithreading", "multi-threading",
                "协程", "coroutine",
                "连接池", "connection_pool", "connection pooling",
                "懒加载", "lazy_loading", "lazy loading",
                "CDN", "cdn", "Content Delivery Network",
            ],
            "description": "性能优化技术",
        },
    },
}


@dataclass
class TagMatch:
    """标签匹配结果"""
    tag_name: str
    category: str
    domain: str
    matched_keyword: str
    line_number: int
    confidence: float = 1.0
    context: str = ""


class TechTagRecognizer:
    """技术标签识别器
    
    自动扫描代码、注释、文档，识别技术标签并打标。
    """
    
    def __init__(self, custom_vocabulary: Optional[dict] = None):
        self.vocabulary = TECH_TAG_VOCABULARY.copy()
        if custom_vocabulary:
            self._merge_vocabulary(custom_vocabulary)
        
        self._build_index()
    
    def _build_index(self):
        """构建关键词索引"""
        self._keyword_index = {}
        self._keyword_pattern = {}
        
        for domain, categories in self.vocabulary.items():
            for category, info in categories.items():
                for keyword in info["keywords"]:
                    keyword_lower = keyword.lower()
                    if keyword_lower not in self._keyword_index:
                        self._keyword_index[keyword_lower] = []
                    self._keyword_index[keyword_lower].append({
                        "domain": domain,
                        "category": category,
                        "description": info["description"],
                    })
        
        all_keywords = list(self._keyword_index.keys())
        all_keywords.sort(key=len, reverse=True)
        
        pattern = r'(?i)\b(' + '|'.join(re.escape(k) for k in all_keywords) + r')\b'
        self._keyword_pattern = re.compile(pattern)
    
    def _merge_vocabulary(self, custom_vocabulary: dict):
        """合并自定义词库"""
        for domain, categories in custom_vocabulary.items():
            if domain not in self.vocabulary:
                self.vocabulary[domain] = {}
            for category, info in categories.items():
                if category not in self.vocabulary[domain]:
                    self.vocabulary[domain][category] = {"keywords": [], "description": ""}
                self.vocabulary[domain][category]["keywords"].extend(info.get("keywords", []))
                if info.get("description"):
                    self.vocabulary[domain][category]["description"] = info["description"]
    
    def scan_content(self, content: str, file_path: str = "") -> list[TagMatch]:
        """扫描内容，识别技术标签
        
        Args:
            content: 代码/注释/文档内容
            file_path: 文件路径（用于上下文）
        
        Returns:
            匹配的标签列表
        """
        matches = []
        lines = content.split('\n')
        
        seen = set()
        
        for line_num, line in enumerate(lines, 1):
            found_in_line = self._keyword_pattern.finditer(line)
            
            for match in found_in_line:
                keyword = match.group(1).lower()
                
                if keyword not in self._keyword_index:
                    continue
                
                for info in self._keyword_index[keyword]:
                    match_key = (info["domain"], info["category"], keyword)
                    if match_key in seen:
                        continue
                    seen.add(match_key)
                    
                    tag_match = TagMatch(
                        tag_name=self._generate_tag_name(info["category"], keyword),
                        category=info["category"],
                        domain=info["domain"],
                        matched_keyword=keyword,
                        line_number=line_num,
                        confidence=self._calculate_confidence(line, keyword),
                        context=line.strip()[:100],
                    )
                    matches.append(tag_match)
        
        return matches
    
    def _generate_tag_name(self, category: str, keyword: str) -> str:
        """生成标签名称"""
        return f"{category}:{keyword}"
    
    def _calculate_confidence(self, line: str, keyword: str) -> float:
        """计算匹配置信度"""
        confidence = 1.0
        
        if line.strip().startswith('#') or line.strip().startswith('//'):
            confidence *= 0.9
        
        if 'import' in line.lower() or 'from' in line.lower():
            confidence *= 1.1
        
        if keyword.lower() in ['pca', 'svm', 'knn', 'lstm', 'gru', 'bert']:
            confidence *= 1.0
        elif len(keyword) < 3:
            confidence *= 0.7
        
        return min(confidence, 1.0)
    
    def scan_file(self, file_path: str) -> list[TagMatch]:
        """扫描文件，识别技术标签"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.scan_content(content, file_path)
        except Exception:
            return []
    
    def get_tag_suggestions(self, partial: str) -> list[dict]:
        """获取标签建议（用于自动补全）"""
        suggestions = []
        partial_lower = partial.lower()
        
        for keyword, infos in self._keyword_index.items():
            if partial_lower in keyword:
                for info in infos:
                    suggestions.append({
                        "name": self._generate_tag_name(info["category"], keyword),
                        "keyword": keyword,
                        "category": info["category"],
                        "domain": info["domain"],
                        "description": info["description"],
                    })
        
        return suggestions[:10]


class TechTagManager:
    """技术标签管理器
    
    管理节点的技术标签，处理标签与决策的关联。
    """
    
    def __init__(self, projmap: ProjMap):
        self.projmap = projmap
        self.recognizer = TechTagRecognizer()
        self._node_map = {n.id: n for n in projmap.nodes}
    
    def auto_tag_node(self, node_id: str, content: Optional[str] = None) -> list[TechTag]:
        """自动为节点打标签
        
        Args:
            node_id: 节点ID
            content: 可选的内容，如果不提供则从文件读取
        
        Returns:
            新增的标签列表
        """
        node = self._node_map.get(node_id)
        if not node:
            return []
        
        if content is None:
            matches = self.recognizer.scan_file(node.file_path)
        else:
            matches = self.recognizer.scan_content(content, node.file_path)
        
        new_tags = []
        existing_names = {t.name for t in node.tech_tags}
        
        for match in matches:
            if match.tag_name in existing_names:
                continue
            
            tag = TechTag(
                name=match.tag_name,
                category=match.category,
                domain=match.domain,
                confidence=match.confidence,
                source="auto",
                line_number=match.line_number,
            )
            node.tech_tags.append(tag)
            new_tags.append(tag)
        
        return new_tags
    
    def add_manual_tag(
        self,
        node_id: str,
        tag_name: str,
        category: str = "custom",
        domain: str = "custom",
    ) -> TechTag:
        """手动添加标签"""
        node = self._node_map.get(node_id)
        if not node:
            raise ValueError(f"节点不存在: {node_id}")
        
        existing_names = {t.name for t in node.tech_tags}
        if tag_name in existing_names:
            raise ValueError(f"标签已存在: {tag_name}")
        
        tag = TechTag(
            name=tag_name,
            category=category,
            domain=domain,
            confidence=1.0,
            source="manual",
        )
        node.tech_tags.append(tag)
        
        return tag
    
    def link_tag_to_decision(
        self,
        node_id: str,
        tag_name: str,
        decision: Decision,
    ) -> bool:
        """关联标签与决策
        
        Args:
            node_id: 节点ID
            tag_name: 标签名称
            decision: 决策记录
        
        Returns:
            是否成功关联
        """
        node = self._node_map.get(node_id)
        if not node:
            return False
        
        for tag in node.tech_tags:
            if tag.name == tag_name:
                tag.decision_id = decision.id
                decision.tech_tag = tag_name
                return True
        
        return False
    
    def create_decision_for_tag(
        self,
        node_id: str,
        tag_name: str,
        content: str,
        reason: str = "",
        alternatives: Optional[list[str]] = None,
        decision_basis: str = "",
        source: DecisionSource = DecisionSource.MANUAL,
    ) -> Decision:
        """为标签创建决策记录
        
        Args:
            node_id: 节点ID
            tag_name: 标签名称
            content: 决策内容
            reason: 决策理由
            alternatives: 备选方案列表
            decision_basis: 决策依据
            source: 决策来源
        
        Returns:
            创建的决策记录
        """
        node = self._node_map.get(node_id)
        if not node:
            raise ValueError(f"节点不存在: {node_id}")
        
        decision = Decision(
            id=generate_decision_id(node_id, DecisionType.METHOD_SELECTION),
            node_id=node_id,
            type=DecisionType.METHOD_SELECTION,
            content=content,
            timestamp=datetime.now(),
            reason=reason,
            alternatives=[Alternative(name=a) for a in (alternatives or [])],
            source=source,
            file_path=node.file_path,
            decision_basis=decision_basis,
            tech_tag=tag_name,
        )
        
        self.projmap.decisions.append(decision)
        
        self.link_tag_to_decision(node_id, tag_name, decision)
        
        return decision
    
    def get_tags_without_decisions(self, node_id: str) -> list[TechTag]:
        """获取没有关联决策的标签"""
        node = self._node_map.get(node_id)
        if not node:
            return []
        
        return [t for t in node.tech_tags if not t.decision_id]
    
    def get_decision_for_tag(self, node_id: str, tag_name: str) -> Optional[Decision]:
        """获取标签关联的决策"""
        node = self._node_map.get(node_id)
        if not node:
            return None
        
        for tag in node.tech_tags:
            if tag.name == tag_name and tag.decision_id:
                for decision in self.projmap.decisions:
                    if decision.id == tag.decision_id:
                        return decision
        
        return None


class AbandonmentManager:
    """废弃路径管理器
    
    处理废线/休眠路径的强制决策记录。
    """
    
    def __init__(self, projmap: ProjMap):
        self.projmap = projmap
        self._node_map = {n.id: n for n in projmap.nodes}
    
    def abandon_node(
        self,
        node_id: str,
        abandoned_method: str,
        abandon_reason: str,
        attempted_solutions: Optional[list[str]] = None,
        can_revive: bool = True,
        revive_condition: str = "",
        abandoned_by: str = "",
    ) -> tuple[Node, Decision]:
        """废弃节点（强制记录决策）
        
        Args:
            node_id: 节点ID
            abandoned_method: 废弃的方法名称
            abandon_reason: 废弃原因
            attempted_solutions: 尝试过的解决方案
            can_revive: 是否可以唤醒
            revive_condition: 唤醒条件
            abandoned_by: 废弃操作人
        
        Returns:
            (更新后的节点, 废弃决策记录)
        """
        node = self._node_map.get(node_id)
        if not node:
            raise ValueError(f"节点不存在: {node_id}")
        
        node.abandon_info = AbandonInfo(
            abandoned_method=abandoned_method,
            abandon_reason=abandon_reason,
            attempted_solutions=attempted_solutions or [],
            can_revive=can_revive,
            revive_condition=revive_condition,
            abandoned_by=abandoned_by,
        )
        
        node.status = NodeStatus.DORMANT
        node.status_changed_at = datetime.now()
        node.status_changed_reason = abandon_reason
        
        decision = Decision(
            id=generate_decision_id(node_id, DecisionType.PATH_ABANDONMENT),
            node_id=node_id,
            type=DecisionType.PATH_ABANDONMENT,
            content=f"废弃方法: {abandoned_method}",
            timestamp=datetime.now(),
            reason=abandon_reason,
            source=DecisionSource.MANUAL,
            file_path=node.file_path,
            decision_basis="\n".join(attempted_solutions) if attempted_solutions else "",
        )
        
        self.projmap.decisions.append(decision)
        
        return node, decision
    
    def revive_node(
        self,
        node_id: str,
        revive_reason: str,
        revived_by: str = "",
    ) -> tuple[Node, Decision]:
        """唤醒废弃节点
        
        Args:
            node_id: 节点ID
            revive_reason: 唤醒原因
            revived_by: 唤醒操作人
        
        Returns:
            (更新后的节点, 唤醒决策记录)
        """
        node = self._node_map.get(node_id)
        if not node:
            raise ValueError(f"节点不存在: {node_id}")
        
        if not node.abandon_info or not node.abandon_info.can_revive:
            raise ValueError(f"节点不可唤醒: {node_id}")
        
        old_abandon_info = node.abandon_info
        node.abandon_info = None
        node.status = NodeStatus.ACTIVE_BRANCH
        node.status_changed_at = datetime.now()
        node.status_changed_reason = f"唤醒: {revive_reason}"
        
        decision = Decision(
            id=generate_decision_id(node_id, DecisionType.MILESTONE),
            node_id=node_id,
            type=DecisionType.MILESTONE,
            content=f"唤醒废弃方法: {old_abandon_info.abandoned_method}",
            timestamp=datetime.now(),
            reason=revive_reason,
            source=DecisionSource.MANUAL,
            file_path=node.file_path,
            decision_basis=f"原废弃原因: {old_abandon_info.abandon_reason}",
        )
        
        self.projmap.decisions.append(decision)
        
        return node, decision
    
    def get_abandonable_nodes(self) -> list[Node]:
        """获取可废弃的节点列表"""
        return [
            n for n in self.projmap.nodes
            if n.status in (NodeStatus.ACTIVE_MAIN, NodeStatus.ACTIVE_BRANCH)
            and not n.abandon_info
        ]
    
    def get_revivable_nodes(self) -> list[Node]:
        """获取可唤醒的节点列表"""
        return [
            n for n in self.projmap.nodes
            if n.status == NodeStatus.DORMANT
            and n.abandon_info
            and n.abandon_info.can_revive
        ]


class InferenceAnnotator:
    """推断标注器
    
    处理冷启动时的推断内容标注。
    """
    
    def __init__(self, projmap: ProjMap):
        self.projmap = projmap
        self._node_map = {n.id: n for n in projmap.nodes}
    
    def mark_inferred(
        self,
        node_id: str,
        inference_source: str,
        confidence: float = 0.5,
        needs_confirmation: bool = True,
    ):
        """标记节点为推断生成"""
        node = self._node_map.get(node_id)
        if not node:
            return
        
        from projmap.models import InferenceSource
        source_map = {
            "llm": InferenceSource.LLM,
            "rule": InferenceSource.RULE,
            "git": InferenceSource.GIT,
            "manual": InferenceSource.MANUAL,
        }
        
        node.inferred_by = source_map.get(inference_source, InferenceSource.UNKNOWN)
        node.confidence = confidence
        node.needs_confirmation = needs_confirmation
    
    def confirm_inference(self, node_id: str):
        """确认推断内容"""
        node = self._node_map.get(node_id)
        if not node:
            return
        
        node.needs_confirmation = False
        node.confidence = 1.0
    
    def get_unconfirmed_nodes(self) -> list[Node]:
        """获取未确认的推断节点"""
        return [n for n in self.projmap.nodes if n.needs_confirmation]
    
    def infer_task_name(self, file_path: str, content: Optional[str] = None) -> tuple[str, float]:
        """从文件推断任务名称
        
        Returns:
            (任务名称, 置信度)
        """
        import os
        file_name = os.path.basename(file_path)
        name_without_ext = os.path.splitext(file_name)[0]
        
        name_mappings = {
            "clean": "数据清洗",
            "preprocess": "数据预处理",
            "feature": "特征工程",
            "train": "模型训练",
            "model": "模型构建",
            "predict": "预测推理",
            "eval": "模型评估",
            "test": "测试验证",
            "utils": "工具函数",
            "config": "配置管理",
            "main": "主入口",
            "app": "应用入口",
            "api": "API接口",
            "data": "数据处理",
            "etl": "ETL流程",
            "backtest": "策略回测",
            "strategy": "交易策略",
            "factor": "因子计算",
            "signal": "信号生成",
        }
        
        name_lower = name_without_ext.lower()
        for key, value in name_mappings.items():
            if key in name_lower:
                return value, 0.7
        
        return name_without_ext, 0.3
    
    def infer_data_flow(self, content: str) -> tuple[list[str], list[str]]:
        """从代码推断数据流向
        
        Returns:
            (输入源列表, 输出目标列表)
        """
        input_patterns = [
            r'read_csv\s*\(\s*["\']([^"\']+)["\']',
            r'read_excel\s*\(\s*["\']([^"\']+)["\']',
            r'read_json\s*\(\s*["\']([^"\']+)["\']',
            r'open\s*\(\s*["\']([^"\']+)["\']',
            r'load\s*\(\s*["\']([^"\']+)["\']',
            r'pd\.read_\w+\s*\(\s*["\']([^"\']+)["\']',
        ]
        
        output_patterns = [
            r'to_csv\s*\(\s*["\']([^"\']+)["\']',
            r'to_excel\s*\(\s*["\']([^"\']+)["\']',
            r'to_json\s*\(\s*["\']([^"\']+)["\']',
            r'save\s*\(\s*["\']([^"\']+)["\']',
            r'write\s*\(\s*["\']([^"\']+)["\']',
        ]
        
        inputs = []
        outputs = []
        
        for pattern in input_patterns:
            matches = re.findall(pattern, content)
            inputs.extend(matches)
        
        for pattern in output_patterns:
            matches = re.findall(pattern, content)
            outputs.extend(matches)
        
        return list(set(inputs)), list(set(outputs))
