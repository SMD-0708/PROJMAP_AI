"""项目导航器模块

解决"知识断层"痛点：项目交接不知从何读起
提供智能项目脉络导航和阅读路径推荐。
"""

import asyncio
import functools
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from collections import defaultdict

from projmap.models import ProjMap, Node, NodeStatus, Edge, NodeType
from projmap.cache import MemoryCache
from projmap.async_utils import AsyncExecutor, parallel_map

logger = logging.getLogger(__name__)


@dataclass
class ReadingNode:
    """阅读节点"""
    node: Node
    importance_score: float = 0.0
    reading_order: int = 0
    prerequisites: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ReadingPath:
    """推荐阅读路径"""
    name: str
    description: str
    nodes: list[ReadingNode]
    estimated_time: int = 0  # 分钟
    target_audience: str = ""


class ProjectNavigator:
    """项目导航器
    
    提供多种阅读路径推荐，解决项目交接时的知识断层问题。
    """
    
    def __init__(self, projmap: ProjMap, use_cache: bool = True):
        self.projmap = projmap
        self._node_map = {n.id: n for n in projmap.nodes}
        self._edge_map = self._build_edge_map()
        
        # 初始化缓存
        self._use_cache = use_cache
        if use_cache:
            self._cache = MemoryCache(max_size=256, ttl=300)  # 5分钟过期
            self._importance_cache = MemoryCache(max_size=512, ttl=600)  # 10分钟过期
        else:
            self._cache = None
            self._importance_cache = None
        
        logger.debug(f"项目导航器初始化完成，缓存: {use_cache}")
    
    def _build_edge_map(self) -> dict[str, list[str]]:
        """构建依赖关系图"""
        logger.debug("构建依赖关系图")
        edge_map = defaultdict(list)
        for edge in self.projmap.edges:
            edge_map[edge.target].append(edge.source)
        logger.debug(f"依赖关系图构建完成，共 {len(edge_map)} 个节点有入边")
        return edge_map
    
    def _calculate_node_importance(self, node: Node) -> float:
        """计算节点重要性分数（带缓存）"""
        # 尝试从缓存获取
        if self._use_cache and self._importance_cache:
            cached_score = self._importance_cache.get(node.id)
            if cached_score is not None:
                logger.debug(f"节点 {node.name} 重要性评分（缓存）: {cached_score:.2f}")
                return cached_score
        
        try:
            score = 0.0
            
            # 1. 状态权重
            status_weights = {
                NodeStatus.ACTIVE_MAIN: 1.0,
                NodeStatus.ACTIVE_BRANCH: 0.7,
                NodeStatus.DORMANT: 0.3,
                NodeStatus.ARCHIVED: 0.1,
            }
            score += status_weights.get(node.status, 0.5) * 30
            
            # 2. 被依赖次数（入度）
            incoming = len(self._edge_map.get(node.id, []))
            score += min(incoming * 5, 20)
            
            # 3. 导出依赖数（出度）
            outgoing = len([e for e in self.projmap.edges if e.source == node.id])
            score += min(outgoing * 3, 15)
            
            # 4. 节点类型权重
            type_weights = {
                NodeType.PACKAGE: 10,
                NodeType.MODULE: 8,
                NodeType.DIRECTORY: 5,
                NodeType.FILE: 3,
            }
            score += type_weights.get(node.type, 0)
            
            # 5. 是否有描述
            if node.description:
                score += 5
            
            # 6. 是否有决策记录
            node_decisions = [d for d in self.projmap.decisions if d.node_id == node.id]
            score += min(len(node_decisions) * 2, 10)
            
            # 存入缓存
            if self._use_cache and self._importance_cache:
                self._importance_cache.set(node.id, score)
            
            logger.debug(f"节点 {node.name} 重要性评分: {score:.2f}")
            return score
            
        except Exception as e:
            logger.warning(f"计算节点 {node.name} 重要性时出错: {e}")
            return 0.0
    
    def clear_cache(self):
        """清除缓存"""
        if self._cache:
            self._cache.clear()
        if self._importance_cache:
            self._importance_cache.clear()
        logger.debug("缓存已清除")
    
    def get_quick_start_path(self) -> ReadingPath:
        """获取快速入门路径
        
        针对新加入项目的开发者，提供最核心的文件阅读顺序。
        """
        # 筛选主线和分支状态的节点
        active_nodes = [
            n for n in self.projmap.nodes
            if n.status in (NodeStatus.ACTIVE_MAIN, NodeStatus.ACTIVE_BRANCH)
        ]
        
        # 计算重要性
        reading_nodes = []
        for node in active_nodes:
            score = self._calculate_node_importance(node)
            prerequisites = self._edge_map.get(node.id, [])
            
            reading_nodes.append(ReadingNode(
                node=node,
                importance_score=score,
                prerequisites=prerequisites,
            ))
        
        # 按重要性排序
        reading_nodes.sort(key=lambda x: x.importance_score, reverse=True)
        
        # 拓扑排序确定阅读顺序
        ordered_nodes = self._topological_sort(reading_nodes)
        
        # 只保留前15个最重要的节点
        top_nodes = ordered_nodes[:15]
        
        # 更新阅读顺序
        for i, rn in enumerate(top_nodes):
            rn.reading_order = i + 1
        
        return ReadingPath(
            name="快速入门路径",
            description="项目核心文件阅读顺序，适合新成员快速了解项目架构",
            nodes=top_nodes,
            estimated_time=len(top_nodes) * 5,
            target_audience="新加入的开发者",
        )
    
    def get_architecture_overview(self) -> ReadingPath:
        """获取架构概览路径
        
        重点展示模块和包级别的节点，理解整体架构。
        """
        # 筛选模块和包级别的节点
        arch_nodes = [
            n for n in self.projmap.nodes
            if n.type in (NodeType.MODULE, NodeType.PACKAGE, NodeType.DIRECTORY)
            and n.status != NodeStatus.ARCHIVED
        ]
        
        reading_nodes = []
        for node in arch_nodes:
            score = self._calculate_node_importance(node)
            prerequisites = self._edge_map.get(node.id, [])
            
            reading_nodes.append(ReadingNode(
                node=node,
                importance_score=score,
                prerequisites=prerequisites,
            ))
        
        reading_nodes.sort(key=lambda x: x.importance_score, reverse=True)
        ordered_nodes = self._topological_sort(reading_nodes)
        
        return ReadingPath(
            name="架构概览路径",
            description="模块和包级别的阅读路径，帮助理解项目整体架构设计",
            nodes=ordered_nodes[:10],
            estimated_time=len(ordered_nodes[:10]) * 8,
            target_audience="架构师、技术负责人",
        )
    
    def get_feature_path(self, feature_tag: str) -> Optional[ReadingPath]:
        """获取特定功能的阅读路径
        
        根据功能标签筛选相关节点。
        """
        # 筛选包含特定标签的节点
        feature_nodes = [
            n for n in self.projmap.nodes
            if n.function_tags and feature_tag in n.function_tags
            and n.status != NodeStatus.ARCHIVED
        ]
        
        if not feature_nodes:
            return None
        
        # 包含直接依赖的节点
        related_node_ids = {n.id for n in feature_nodes}
        for node in feature_nodes:
            for prereq in self._edge_map.get(node.id, []):
                if prereq in self._node_map:
                    related_node_ids.add(prereq)
        
        all_nodes = [self._node_map[nid] for nid in related_node_ids if nid in self._node_map]
        
        reading_nodes = []
        for node in all_nodes:
            score = self._calculate_node_importance(node)
            if node in feature_nodes:
                score += 20  # 功能节点加分
            
            reading_nodes.append(ReadingNode(
                node=node,
                importance_score=score,
                prerequisites=[p for p in self._edge_map.get(node.id, []) if p in related_node_ids],
            ))
        
        reading_nodes.sort(key=lambda x: x.importance_score, reverse=True)
        ordered_nodes = self._topological_sort(reading_nodes)
        
        return ReadingPath(
            name=f"功能路径: {feature_tag}",
            description=f"与'{feature_tag}'功能相关的文件阅读路径",
            nodes=ordered_nodes,
            estimated_time=len(ordered_nodes) * 5,
            target_audience=f"负责{feature_tag}功能的开发者",
        )
    
    def get_active_development_path(self) -> ReadingPath:
        """获取活跃开发路径
        
        只包含主线状态的节点，适合了解当前活跃的开发内容。
        """
        main_nodes = [
            n for n in self.projmap.nodes
            if n.status == NodeStatus.ACTIVE_MAIN
        ]
        
        reading_nodes = []
        for node in main_nodes:
            score = self._calculate_node_importance(node)
            prerequisites = self._edge_map.get(node.id, [])
            
            reading_nodes.append(ReadingNode(
                node=node,
                importance_score=score,
                prerequisites=prerequisites,
            ))
        
        reading_nodes.sort(key=lambda x: x.importance_score, reverse=True)
        ordered_nodes = self._topological_sort(reading_nodes)
        
        return ReadingPath(
            name="活跃开发路径",
            description="当前主线开发内容的阅读路径，排除休眠和归档文件",
            nodes=ordered_nodes[:12],
            estimated_time=len(ordered_nodes[:12]) * 5,
            target_audience="当前项目开发者",
        )
    
    def _topological_sort(self, reading_nodes: list[ReadingNode]) -> list[ReadingNode]:
        """拓扑排序，确保依赖项在前"""
        node_map = {rn.node.id: rn for rn in reading_nodes}
        result = []
        visited = set()
        temp_mark = set()
        
        def visit(rn: ReadingNode):
            if rn.node.id in temp_mark:
                return  # 有环，跳过
            if rn.node.id in visited:
                return
            
            temp_mark.add(rn.node.id)
            
            # 先访问依赖项
            for prereq_id in rn.prerequisites:
                if prereq_id in node_map:
                    visit(node_map[prereq_id])
            
            temp_mark.remove(rn.node.id)
            visited.add(rn.node.id)
            result.append(rn)
        
        # 按重要性顺序访问
        for rn in sorted(reading_nodes, key=lambda x: x.importance_score, reverse=True):
            if rn.node.id not in visited:
                visit(rn)
        
        return result
    
    async def calculate_importance_async(
        self,
        nodes: list[Node],
        max_workers: int = 4,
    ) -> dict[str, float]:
        """异步计算节点重要性
        
        Args:
            nodes: 节点列表
            max_workers: 最大并发数
        
        Returns:
            节点ID到重要性分数的映射
        """
        logger.info(f"开始异步计算 {len(nodes)} 个节点的重要性")
        
        def calc_single(node: Node) -> tuple[str, float]:
            score = self._calculate_node_importance(node)
            return (node.id, score)
        
        # 使用线程池并行计算
        results = await parallel_map(calc_single, nodes, max_workers=max_workers)
        
        logger.info("异步计算完成")
        return {node_id: score for node_id, score in results}
    
    async def generate_navigation_report_async(
        self,
        max_workers: int = 4,
    ) -> dict:
        """异步生成导航报告
        
        Args:
            max_workers: 最大并发数
        
        Returns:
            导航报告
        """
        logger.info("开始异步生成导航报告")
        
        # 并行计算所有节点的重要性
        importance_scores = await self.calculate_importance_async(
            self.projmap.nodes,
            max_workers=max_workers,
        )
        
        # 生成报告（其余逻辑同步执行）
        paths = [
            self.get_quick_start_path(),
            self.get_architecture_overview(),
            self.get_active_development_path(),
        ]
        
        # 获取所有功能标签
        all_tags = set()
        for node in self.projmap.nodes:
            if node.function_tags:
                all_tags.update(node.function_tags)
        
        # 为每个功能标签生成路径
        feature_paths = []
        for tag in sorted(all_tags)[:5]:
            path = self.get_feature_path(tag)
            if path:
                feature_paths.append(path)
        
        paths.extend(feature_paths)
        
        report = {
            "project_name": self.projmap.metadata.project_name,
            "generated_at": datetime.now().isoformat(),
            "total_nodes": len(self.projmap.nodes),
            "active_main_nodes": len([n for n in self.projmap.nodes if n.status == NodeStatus.ACTIVE_MAIN]),
            "reading_paths": [
                {
                    "name": p.name,
                    "description": p.description,
                    "target_audience": p.target_audience,
                    "estimated_time": p.estimated_time,
                    "node_count": len(p.nodes),
                    "nodes": [
                        {
                            "order": rn.reading_order,
                            "name": rn.node.name,
                            "file_path": rn.node.file_path,
                            "status": rn.node.status.value,
                            "type": rn.node.type.value,
                            "importance_score": round(rn.importance_score, 2),
                            "description": rn.node.description,
                        }
                        for rn in p.nodes
                    ],
                }
                for p in paths
            ],
        }
        
        logger.info("异步导航报告生成完成")
        return report
    
    def generate_navigation_report(self) -> dict:
        """生成导航报告"""
        paths = [
            self.get_quick_start_path(),
            self.get_architecture_overview(),
            self.get_active_development_path(),
        ]
        
        # 获取所有功能标签
        all_tags = set()
        for node in self.projmap.nodes:
            if node.function_tags:
                all_tags.update(node.function_tags)
        
        # 为每个功能标签生成路径
        feature_paths = []
        for tag in sorted(all_tags)[:5]:  # 最多5个功能路径
            path = self.get_feature_path(tag)
            if path:
                feature_paths.append(path)
        
        paths.extend(feature_paths)
        
        return {
            "project_name": self.projmap.metadata.project_name,
            "generated_at": datetime.now().isoformat(),
            "total_nodes": len(self.projmap.nodes),
            "active_main_nodes": len([n for n in self.projmap.nodes if n.status == NodeStatus.ACTIVE_MAIN]),
            "reading_paths": [
                {
                    "name": p.name,
                    "description": p.description,
                    "target_audience": p.target_audience,
                    "estimated_time": p.estimated_time,
                    "node_count": len(p.nodes),
                    "nodes": [
                        {
                            "order": rn.reading_order,
                            "name": rn.node.name,
                            "file_path": rn.node.file_path,
                            "status": rn.node.status.value,
                            "type": rn.node.type.value,
                            "importance_score": round(rn.importance_score, 2),
                            "description": rn.node.description,
                        }
                        for rn in p.nodes
                    ],
                }
                for p in paths
            ],
        }


def generate_navigation_guide(projmap: ProjMap, output_path: Optional[str] = None) -> str:
    """生成导航指南 Markdown 文件"""
    navigator = ProjectNavigator(projmap)
    report = navigator.generate_navigation_report()
    
    lines = [
        f"# {report['project_name']} - 项目导航指南",
        "",
        f"生成时间: {report['generated_at']}",
        f"项目节点总数: {report['total_nodes']} (主线: {report['active_main_nodes']})",
        "",
        "---",
        "",
    ]
    
    for path in report["reading_paths"]:
        lines.extend([
            f"## {path['name']}",
            "",
            f"**目标读者**: {path['target_audience']}",
            f"**预计阅读时间**: {path['estimated_time']} 分钟",
            f"**包含文件**: {path['node_count']} 个",
            "",
            f"{path['description']}",
            "",
            "### 阅读顺序",
            "",
        ])
        
        for node in path["nodes"]:
            status_emoji = {
                "active_main": "🟢",
                "active_branch": "🔵",
                "dormant": "🟡",
                "archived": "⚪",
            }.get(node["status"], "⚪")
            
            lines.extend([
                f"{node['order']}. {status_emoji} **{node['name']}**",
                f"   - 路径: `{node['file_path']}`",
                f"   - 类型: {node['type']} | 重要度: {node['importance_score']}",
            ])
            if node["description"]:
                lines.append(f"   - 描述: {node['description']}")
            lines.append("")
        
        lines.append("---\n")
    
    content = "\n".join(lines)
    
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
    
    return content
