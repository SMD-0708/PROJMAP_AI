"""失败检索系统

解决"踩坑复现"痛点：解决过的问题找不到
提供失败记录、错误模式识别和解决方案检索。
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from collections import defaultdict
import hashlib

from projmap.models import ProjMap, Decision, DecisionType, Node, NodeStatus

logger = logging.getLogger(__name__)


@dataclass
class FailurePattern:
    """失败模式"""
    pattern_id: str
    error_type: str
    error_message: str
    context: str
    solution: str
    node_id: str
    timestamp: datetime
    tags: list[str] = field(default_factory=list)
    related_failures: list[str] = field(default_factory=list)


@dataclass
class Solution:
    """解决方案"""
    solution_id: str
    failure_pattern_id: str
    description: str
    code_fix: Optional[str] = None
    references: list[str] = field(default_factory=list)
    verified: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


class FailureRetrieval:
    """失败检索器
    
    提供失败记录的管理、检索和模式识别。
    核心功能：
    - 记录失败和解决方案
    - 按错误类型、标签检索
    - 相似错误匹配
    - 失败模式统计
    """
    
    # 常见错误类型模式
    ERROR_PATTERNS = {
        "syntax_error": r"SyntaxError|语法错误",
        "import_error": r"ImportError|ModuleNotFoundError|No module named",
        "type_error": r"TypeError|类型错误",
        "value_error": r"ValueError|值错误",
        "key_error": r"KeyError|键错误",
        "index_error": r"IndexError|索引错误",
        "attribute_error": r"AttributeError|属性错误",
        "runtime_error": r"RuntimeError|运行时错误",
        "timeout_error": r"TimeoutError|超时",
        "connection_error": r"ConnectionError|连接错误",
        "permission_error": r"PermissionError|权限错误",
        "file_not_found": r"FileNotFoundError|文件未找到",
        "memory_error": r"MemoryError|内存错误",
        "null_pointer": r"NullPointerException|NoneType",
        "division_by_zero": r"ZeroDivisionError|除零",
    }
    
    def __init__(self, projmap: ProjMap):
        self.projmap = projmap
        self._failure_cache: list[FailurePattern] = []
        self._solution_cache: list[Solution] = []
        self._build_cache()
    
    def _build_cache(self):
        """从决策记录构建失败缓存"""
        logger.debug(f"开始构建失败缓存，共 {len(self.projmap.decisions)} 个决策")
        
        for decision in self.projmap.decisions:
            if decision.type in (DecisionType.FAILURE, DecisionType.ABANDONED):
                try:
                    pattern = self._decision_to_failure_pattern(decision)
                    if pattern:
                        self._failure_cache.append(pattern)
                        logger.debug(f"添加失败模式: {pattern.pattern_id} ({pattern.error_type})")
                except Exception as e:
                    logger.warning(f"处理决策 {decision.id} 失败: {e}")
                    continue
        
        logger.info(f"失败缓存构建完成，共 {len(self._failure_cache)} 个模式")
    
    def _decision_to_failure_pattern(self, decision: Decision) -> Optional[FailurePattern]:
        """将决策转换为失败模式"""
        # 识别错误类型
        error_type = self._detect_error_type(decision.content)
        
        # 生成模式ID
        pattern_id = hashlib.md5(
            f"{decision.node_id}:{decision.timestamp.isoformat()}".encode()
        ).hexdigest()[:12]
        
        # 提取标签
        tags = self._extract_tags(decision.content)
        
        return FailurePattern(
            pattern_id=pattern_id,
            error_type=error_type or "unknown",
            error_message=decision.content,
            context=decision.reason or "",
            solution=self._extract_solution(decision),
            node_id=decision.node_id,
            timestamp=decision.timestamp,
            tags=tags,
        )
    
    def _detect_error_type(self, content: str) -> Optional[str]:
        """检测错误类型"""
        content_lower = content.lower()
        
        for error_type, pattern in self.ERROR_PATTERNS.items():
            if re.search(pattern, content, re.IGNORECASE):
                return error_type
        
        return None
    
    def _extract_tags(self, content: str) -> list[str]:
        """从内容中提取标签"""
        tags = []
        
        # 技术关键词
        tech_keywords = [
            "python", "javascript", "java", "go", "rust",
            "api", "database", "cache", "async", "thread",
            "memory", "performance", "security", "config",
            "dependency", "version", "build", "deploy",
        ]
        
        content_lower = content.lower()
        for keyword in tech_keywords:
            if keyword in content_lower:
                tags.append(keyword)
        
        return tags
    
    def _extract_solution(self, decision: Decision) -> str:
        """从决策中提取解决方案"""
        # 如果有参数，可能包含解决方案
        if decision.parameters:
            solution_parts = []
            for key, value in decision.parameters.items():
                if "fix" in key.lower() or "solution" in key.lower():
                    solution_parts.append(f"{key}: {value}")
            if solution_parts:
                return "; ".join(solution_parts)
        
        # 备选方案中可能有解决方案
        for alt in decision.alternatives:
            if alt.reason_rejected and "改用" in alt.reason_rejected:
                return alt.reason_rejected
        
        return "未记录具体解决方案"
    
    def record_failure(
        self,
        node_id: str,
        error_message: str,
        context: str = "",
        solution: str = "",
        tags: Optional[list[str]] = None,
    ) -> FailurePattern:
        """记录新的失败"""
        logger.info(f"记录失败: node={node_id}, error_type={self._detect_error_type(error_message)}")
        
        try:
            error_type = self._detect_error_type(error_message)
            
            pattern_id = hashlib.md5(
                f"{node_id}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:12]
            
            all_tags = self._extract_tags(error_message)
            if tags:
                all_tags.extend(tags)
            
            pattern = FailurePattern(
                pattern_id=pattern_id,
                error_type=error_type or "unknown",
                error_message=error_message,
                context=context,
                solution=solution,
                node_id=node_id,
                timestamp=datetime.now(),
                tags=list(set(all_tags)),
            )
            
            self._failure_cache.append(pattern)
            logger.debug(f"失败模式已添加到缓存: {pattern_id}")
            
            # 同时记录到决策中
            try:
                from projmap.decision_manager import DecisionManager
                
                manager = DecisionManager(self.projmap)
                manager.add_decision(
                    node_id=node_id,
                    decision_type="failure",
                    content=error_message,
                    reason=context,
                    parameters={"solution": solution, "error_type": error_type} if solution else {"error_type": error_type},
                )
                logger.debug(f"失败已记录到决策系统")
            except Exception as e:
                logger.warning(f"记录到决策系统失败: {e}")
            
            logger.info(f"失败记录完成: {pattern_id}")
            return pattern
            
        except Exception as e:
            logger.error(f"记录失败时发生错误: {e}")
            raise
    
    def search_failures(
        self,
        query: str,
        error_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        node_id: Optional[str] = None,
    ) -> list[FailurePattern]:
        """搜索失败记录"""
        query_lower = query.lower()
        results = []
        
        for pattern in self._failure_cache:
            score = 0
            
            # 节点过滤
            if node_id and pattern.node_id != node_id:
                continue
            
            # 错误类型过滤
            if error_type and pattern.error_type != error_type:
                continue
            
            # 标签过滤
            if tags:
                if not all(tag in pattern.tags for tag in tags):
                    continue
            
            # 相关性评分
            if query_lower in pattern.error_message.lower():
                score += 10
            if query_lower in pattern.context.lower():
                score += 5
            if query_lower in pattern.solution.lower():
                score += 3
            if any(query_lower in tag.lower() for tag in pattern.tags):
                score += 8
            if pattern.error_type and query_lower in pattern.error_type.lower():
                score += 7
            
            if score > 0:
                results.append((pattern, score))
        
        # 按评分排序
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results]
    
    def find_similar_failures(
        self,
        error_message: str,
        top_k: int = 5,
    ) -> list[tuple[FailurePattern, float]]:
        """查找相似的失败记录"""
        query_lower = error_message.lower()
        results = []
        
        for pattern in self._failure_cache:
            # 简单的相似度计算
            pattern_msg_lower = pattern.error_message.lower()
            
            # 计算共同词数
            query_words = set(query_lower.split())
            pattern_words = set(pattern_msg_lower.split())
            common_words = query_words & pattern_words
            
            if len(query_words) > 0:
                similarity = len(common_words) / len(query_words)
            else:
                similarity = 0
            
            # 错误类型匹配加分
            query_error_type = self._detect_error_type(error_message)
            if query_error_type and pattern.error_type == query_error_type:
                similarity += 0.3
            
            if similarity > 0.2:  # 阈值
                results.append((pattern, min(similarity, 1.0)))
        
        # 按相似度排序
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def get_failure_statistics(self) -> dict:
        """获取失败统计信息"""
        stats = {
            "total_failures": len(self._failure_cache),
            "by_error_type": defaultdict(int),
            "by_node": defaultdict(int),
            "by_time": defaultdict(int),
            "by_tag": defaultdict(int),
            "recent_failures": [],
        }
        
        for pattern in self._failure_cache:
            # 按错误类型统计
            stats["by_error_type"][pattern.error_type] += 1
            
            # 按节点统计
            stats["by_node"][pattern.node_id] += 1
            
            # 按月统计
            month_key = pattern.timestamp.strftime("%Y-%m")
            stats["by_time"][month_key] += 1
            
            # 按标签统计
            for tag in pattern.tags:
                stats["by_tag"][tag] += 1
        
        # 最近的失败
        sorted_patterns = sorted(
            self._failure_cache,
            key=lambda p: p.timestamp,
            reverse=True,
        )
        stats["recent_failures"] = [
            {
                "pattern_id": p.pattern_id,
                "error_type": p.error_type,
                "error_message": p.error_message[:100] + "..." if len(p.error_message) > 100 else p.error_message,
                "timestamp": p.timestamp.isoformat(),
                "node_id": p.node_id,
            }
            for p in sorted_patterns[:10]
        ]
        
        return dict(stats)
    
    def get_common_solutions(self, error_type: str) -> list[dict]:
        """获取某类错误的常见解决方案"""
        solutions = []
        
        for pattern in self._failure_cache:
            if pattern.error_type == error_type and pattern.solution:
                solutions.append({
                    "pattern_id": pattern.pattern_id,
                    "solution": pattern.solution,
                    "context": pattern.context,
                    "timestamp": pattern.timestamp.isoformat(),
                    "tags": pattern.tags,
                })
        
        # 按时间排序
        solutions.sort(key=lambda x: x["timestamp"], reverse=True)
        return solutions[:10]
    
    def suggest_prevention(self, node_id: str) -> list[dict]:
        """为节点建议预防措施"""
        suggestions = []
        
        # 获取该节点的历史失败
        node_failures = [p for p in self._failure_cache if p.node_id == node_id]
        
        if not node_failures:
            return suggestions
        
        # 统计该节点的常见错误类型
        error_types = defaultdict(int)
        for pattern in node_failures:
            error_types[pattern.error_type] += 1
        
        # 生成预防建议
        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:3]:
            suggestion = {
                "error_type": error_type,
                "occurrence_count": count,
                "prevention_tips": self._get_prevention_tips(error_type),
            }
            suggestions.append(suggestion)
        
        return suggestions
    
    def _get_prevention_tips(self, error_type: str) -> list[str]:
        """获取预防建议"""
        tips_map = {
            "syntax_error": [
                "使用 IDE 的语法检查功能",
                "提交前运行代码检查工具",
                "编写单元测试覆盖关键路径",
            ],
            "import_error": [
                "维护 requirements.txt 或 package.json",
                "使用虚拟环境隔离依赖",
                "在 CI/CD 中检查依赖安装",
            ],
            "type_error": [
                "添加类型注解",
                "使用 mypy 进行类型检查",
                "编写输入验证逻辑",
            ],
            "key_error": [
                "使用 .get() 方法访问字典",
                "添加键存在性检查",
                "使用 defaultdict",
            ],
            "index_error": [
                "检查列表长度后再访问",
                "使用 try-except 处理边界情况",
                "考虑使用切片操作",
            ],
            "attribute_error": [
                "使用 hasattr() 检查属性存在",
                "添加空值检查",
                "使用可选链操作符",
            ],
            "null_pointer": [
                "添加空值检查",
                "使用 Optional 类型",
                "初始化时设置默认值",
            ],
        }
        
        return tips_map.get(error_type, ["添加适当的错误处理", "编写单元测试", "进行代码审查"])
    
    def generate_failure_report(self) -> dict:
        """生成失败分析报告"""
        stats = self.get_failure_statistics()
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_failures": stats["total_failures"],
                "most_common_error": max(stats["by_error_type"].items(), key=lambda x: x[1])[0] if stats["by_error_type"] else None,
                "most_problematic_node": max(stats["by_node"].items(), key=lambda x: x[1])[0] if stats["by_node"] else None,
            },
            "error_type_distribution": dict(stats["by_error_type"]),
            "tag_distribution": dict(stats["by_tag"]),
            "recent_failures": stats["recent_failures"],
            "recommendations": [],
        }
        
        # 生成建议
        if stats["by_error_type"]:
            top_error = max(stats["by_error_type"].items(), key=lambda x: x[1])
            report["recommendations"].append(
                f"'{top_error[0]}' 是最常见的错误类型，建议团队重点关注此类错误的预防"
            )
        
        if stats["by_node"]:
            top_node = max(stats["by_node"].items(), key=lambda x: x[1])
            report["recommendations"].append(
                f"节点 '{top_node[0]}' 失败次数最多，建议进行代码重构或增加测试覆盖"
            )
        
        return report


def search_similar_errors(projmap: ProjMap, error_message: str) -> list[dict]:
    """便捷函数：搜索相似错误"""
    retriever = FailureRetrieval(projmap)
    similar = retriever.find_similar_failures(error_message)
    
    return [
        {
            "pattern_id": pattern.pattern_id,
            "similarity": round(score, 2),
            "error_type": pattern.error_type,
            "error_message": pattern.error_message,
            "solution": pattern.solution,
            "timestamp": pattern.timestamp.isoformat(),
        }
        for pattern, score in similar
    ]
