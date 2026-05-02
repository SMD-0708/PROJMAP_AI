"""节点聚合器

实现节点的自动归纳与聚合：
- 目录级聚合：同一目录下的文件聚合成一个节点
- 功能级聚合：LLM推断出多个脚本服务于同一功能
- 语义缩放联动：缩小时自动聚合，放大时自动展开
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AggregationLevel(Enum):
    FILE = "file"
    DIRECTORY = "directory"
    FUNCTION = "function"
    MODULE = "module"


@dataclass
class AggregatedNode:
    node_id: str
    node_type: str
    display_name: str
    children: list = field(default_factory=list)
    file_count: int = 0
    total_lines: int = 0
    main_language: str = ""
    importance_score: float = 0.0
    is_collapsed: bool = True
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "display_name": self.display_name,
            "children": self.children,
            "file_count": self.file_count,
            "total_lines": self.total_lines,
            "main_language": self.main_language,
            "importance_score": self.importance_score,
            "is_collapsed": self.is_collapsed,
            "metadata": self.metadata
        }


@dataclass
class AggregationRule:
    rule_id: str
    rule_name: str
    condition: str
    action: str
    priority: int = 0


class DirectoryAggregator:
    """目录级聚合器"""
    
    def __init__(self, min_files_to_aggregate: int = 3):
        self.min_files = min_files_to_aggregate
    
    def aggregate(self, files: list[dict]) -> list[AggregatedNode]:
        dir_groups = {}
        
        for file_info in files:
            file_path = file_info.get("path", "")
            dir_path = os.path.dirname(file_path) or "root"
            
            if dir_path not in dir_groups:
                dir_groups[dir_path] = {
                    "files": [],
                    "total_lines": 0,
                    "languages": {}
                }
            
            dir_groups[dir_path]["files"].append(file_info)
            dir_groups[dir_path]["total_lines"] += file_info.get("lines", 0)
            
            lang = file_info.get("language", "unknown")
            dir_groups[dir_path]["languages"][lang] = dir_groups[dir_path]["languages"].get(lang, 0) + 1
        
        aggregated_nodes = []
        
        for dir_path, group_data in dir_groups.items():
            file_count = len(group_data["files"])
            
            if file_count >= self.min_files:
                main_language = max(
                    group_data["languages"].items(),
                    key=lambda x: x[1]
                )[0] if group_data["languages"] else "unknown"
                
                node = AggregatedNode(
                    node_id=f"dir_{dir_path.replace('/', '_').replace('\\', '_')}",
                    node_type="directory",
                    display_name=self._generate_display_name(dir_path),
                    children=[f.get("path") for f in group_data["files"]],
                    file_count=file_count,
                    total_lines=group_data["total_lines"],
                    main_language=main_language,
                    is_collapsed=True,
                    metadata={
                        "directory": dir_path,
                        "aggregation_reason": "directory_grouping"
                    }
                )
                aggregated_nodes.append(node)
            else:
                for file_info in group_data["files"]:
                    node = AggregatedNode(
                        node_id=file_info.get("path", ""),
                        node_type="file",
                        display_name=os.path.basename(file_info.get("path", "")),
                        children=[],
                        file_count=1,
                        total_lines=file_info.get("lines", 0),
                        main_language=file_info.get("language", "unknown"),
                        is_collapsed=False,
                        metadata={"file_path": file_info.get("path", "")}
                    )
                    aggregated_nodes.append(node)
        
        return aggregated_nodes
    
    def _generate_display_name(self, dir_path: str) -> str:
        name_map = {
            "src": "源代码",
            "tests": "测试",
            "test": "测试",
            "docs": "文档",
            "data": "数据",
            "scripts": "脚本",
            "utils": "工具函数",
            "core": "核心模块",
            "models": "模型",
            "views": "视图",
            "controllers": "控制器",
            "api": "API接口",
            "config": "配置",
            "features": "特征工程",
            "notebooks": "笔记本",
            "lib": "库",
            "helpers": "辅助函数",
            "services": "服务",
            "handlers": "处理器",
        }
        
        dir_name = os.path.basename(dir_path)
        return name_map.get(dir_name.lower(), dir_name)


class FunctionalAggregator:
    """功能级聚合器 - 基于命名模式和依赖关系"""
    
    FUNCTIONAL_PATTERNS = {
        "data_ingestion": ["fetch", "download", "ingest", "collect", "crawl", "scrape"],
        "data_cleaning": ["clean", "preprocess", "transform", "etl", "sanitize"],
        "feature_engineering": ["feature", "feat", "engineer", "extract"],
        "model_training": ["train", "fit", "learn", "model"],
        "model_evaluation": ["eval", "test", "validate", "metric", "assess"],
        "visualization": ["plot", "visualize", "chart", "graph", "display"],
        "api": ["api", "endpoint", "route", "controller"],
        "database": ["db", "database", "sql", "query", "orm"],
        "authentication": ["auth", "login", "session", "token", "jwt"],
        "configuration": ["config", "setting", "env", "option"],
        "testing": ["test", "spec", "mock", "fixture"],
        "utils": ["util", "helper", "common", "shared", "tool"],
    }
    
    def __init__(self):
        self.pattern_map = {}
        for func_name, patterns in self.FUNCTIONAL_PATTERNS.items():
            for pattern in patterns:
                self.pattern_map[pattern] = func_name
    
    def aggregate(self, files: list[dict]) -> list[AggregatedNode]:
        functional_groups = {}
        
        for file_info in files:
            file_path = file_info.get("path", "")
            function_name = self._infer_function(file_path, file_info)
            
            if function_name:
                if function_name not in functional_groups:
                    functional_groups[function_name] = {
                        "files": [],
                        "total_lines": 0,
                        "languages": {}
                    }
                
                functional_groups[function_name]["files"].append(file_info)
                functional_groups[function_name]["total_lines"] += file_info.get("lines", 0)
                
                lang = file_info.get("language", "unknown")
                functional_groups[function_name]["languages"][lang] = \
                    functional_groups[function_name]["languages"].get(lang, 0) + 1
        
        aggregated_nodes = []
        
        for func_name, group_data in functional_groups.items():
            if len(group_data["files"]) >= 2:
                main_language = max(
                    group_data["languages"].items(),
                    key=lambda x: x[1]
                )[0] if group_data["languages"] else "unknown"
                
                node = AggregatedNode(
                    node_id=f"func_{func_name}",
                    node_type="functional_group",
                    display_name=self._get_function_display_name(func_name),
                    children=[f.get("path") for f in group_data["files"]],
                    file_count=len(group_data["files"]),
                    total_lines=group_data["total_lines"],
                    main_language=main_language,
                    importance_score=self._calculate_importance(func_name),
                    is_collapsed=True,
                    metadata={
                        "function": func_name,
                        "aggregation_reason": "functional_grouping"
                    }
                )
                aggregated_nodes.append(node)
        
        return aggregated_nodes
    
    def _infer_function(self, file_path: str, file_info: dict) -> Optional[str]:
        lower_path = file_path.lower()
        filename = os.path.basename(file_path).lower()
        
        for pattern, func_name in self.pattern_map.items():
            if pattern in lower_path or pattern in filename:
                return func_name
        
        imports = file_info.get("imports", [])
        for imp in imports:
            for pattern, func_name in self.pattern_map.items():
                if pattern in imp.lower():
                    return func_name
        
        return None
    
    def _get_function_display_name(self, func_name: str) -> str:
        name_map = {
            "data_ingestion": "数据采集",
            "data_cleaning": "数据清洗",
            "feature_engineering": "特征工程",
            "model_training": "模型训练",
            "model_evaluation": "模型评估",
            "visualization": "可视化",
            "api": "API接口",
            "database": "数据库",
            "authentication": "认证授权",
            "configuration": "配置管理",
            "testing": "测试",
            "utils": "工具函数",
        }
        return name_map.get(func_name, func_name)
    
    def _calculate_importance(self, func_name: str) -> float:
        importance_map = {
            "model_training": 1.0,
            "model_evaluation": 0.9,
            "feature_engineering": 0.85,
            "data_ingestion": 0.8,
            "data_cleaning": 0.75,
            "api": 0.7,
            "authentication": 0.65,
            "database": 0.6,
            "visualization": 0.5,
            "configuration": 0.4,
            "testing": 0.3,
            "utils": 0.2,
        }
        return importance_map.get(func_name, 0.5)


class SemanticZoomManager:
    """语义缩放管理器"""
    
    def __init__(self, zoom_thresholds: Optional[dict] = None):
        self.zoom_thresholds = zoom_thresholds or {
            "file_level": 1.0,
            "directory_level": 0.7,
            "functional_level": 0.5,
            "module_level": 0.3
        }
    
    def get_aggregation_level(self, zoom_level: float) -> AggregationLevel:
        if zoom_level >= self.zoom_thresholds["file_level"]:
            return AggregationLevel.FILE
        elif zoom_level >= self.zoom_thresholds["directory_level"]:
            return AggregationLevel.DIRECTORY
        elif zoom_level >= self.zoom_thresholds["functional_level"]:
            return AggregationLevel.FUNCTION
        else:
            return AggregationLevel.MODULE
    
    def apply_zoom(
        self,
        nodes: list[AggregatedNode],
        zoom_level: float,
        expanded_nodes: Optional[list] = None
    ) -> list[AggregatedNode]:
        expanded_nodes = expanded_nodes or []
        aggregation_level = self.get_aggregation_level(zoom_level)
        
        result = []
        for node in nodes:
            if node.node_id in expanded_nodes:
                node.is_collapsed = False
            else:
                node.is_collapsed = self._should_collapse(node, aggregation_level)
            
            result.append(node)
        
        return result
    
    def _should_collapse(self, node: AggregatedNode, level: AggregationLevel) -> bool:
        if level == AggregationLevel.FILE:
            return False
        elif level == AggregationLevel.DIRECTORY:
            return node.node_type in ["directory", "functional_group"]
        elif level == AggregationLevel.FUNCTION:
            return node.node_type == "functional_group"
        else:
            return True


class NodeAggregator:
    """节点聚合器主类"""
    
    def __init__(
        self,
        min_files_for_directory: int = 3,
        enable_functional: bool = True
    ):
        self.directory_aggregator = DirectoryAggregator(min_files_for_directory)
        self.functional_aggregator = FunctionalAggregator() if enable_functional else None
        self.zoom_manager = SemanticZoomManager()
    
    def aggregate(
        self,
        files: list[dict],
        zoom_level: float = 1.0,
        expanded_nodes: Optional[list] = None
    ) -> dict:
        dir_nodes = self.directory_aggregator.aggregate(files)
        
        func_nodes = []
        if self.functional_aggregator:
            func_nodes = self.functional_aggregator.aggregate(files)
        
        all_nodes = self._merge_nodes(dir_nodes, func_nodes)
        
        zoomed_nodes = self.zoom_manager.apply_zoom(
            all_nodes, zoom_level, expanded_nodes
        )
        
        return {
            "nodes": [node.to_dict() for node in zoomed_nodes],
            "statistics": self._calculate_statistics(zoomed_nodes),
            "zoom_level": zoom_level,
            "aggregation_level": self.zoom_manager.get_aggregation_level(zoom_level).value
        }
    
    def _merge_nodes(
        self,
        dir_nodes: list[AggregatedNode],
        func_nodes: list[AggregatedNode]
    ) -> list[AggregatedNode]:
        result = list(dir_nodes)
        
        for func_node in func_nodes:
            overlapping = False
            for dir_node in dir_nodes:
                if set(func_node.children) & set(dir_node.children):
                    overlapping = True
                    break
            
            if not overlapping and func_node.file_count >= 2:
                result.append(func_node)
        
        return result
    
    def _calculate_statistics(self, nodes: list[AggregatedNode]) -> dict:
        total_files = sum(n.file_count for n in nodes)
        collapsed_count = sum(1 for n in nodes if n.is_collapsed)
        
        type_counts = {}
        for node in nodes:
            node_type = node.node_type
            type_counts[node_type] = type_counts.get(node_type, 0) + 1
        
        return {
            "total_nodes": len(nodes),
            "total_files": total_files,
            "collapsed_nodes": collapsed_count,
            "expanded_nodes": len(nodes) - collapsed_count,
            "node_types": type_counts
        }
    
    def expand_node(self, nodes: list[dict], node_id: str) -> list[dict]:
        for node in nodes:
            if node["node_id"] == node_id:
                node["is_collapsed"] = False
                break
        return nodes
    
    def collapse_node(self, nodes: list[dict], node_id: str) -> list[dict]:
        for node in nodes:
            if node["node_id"] == node_id:
                node["is_collapsed"] = True
                break
        return nodes


def aggregate_nodes(
    files: list[dict],
    zoom_level: float = 1.0,
    expanded_nodes: Optional[list] = None
) -> dict:
    aggregator = NodeAggregator()
    return aggregator.aggregate(files, zoom_level, expanded_nodes)
