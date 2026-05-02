"""智能布局引擎

根据项目特征自动选择最佳布局策略：
- 层级树布局：有明显入口文件且依赖链深
- 阶段分区布局：能识别出数据处理阶段
- 星型+分组布局：多个模块围绕核心工具函数
- 时间轴布局：版本号或时间戳明显
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import os
import re


class LayoutStrategy(Enum):
    HIERARCHICAL_TREE = "hierarchical_tree"
    STAGE_PARTITION = "stage_partition"
    STAR_GROUPED = "star_grouped"
    TIMELINE = "timeline"
    HYBRID = "hybrid"


@dataclass
class LayoutConfig:
    strategy: LayoutStrategy
    direction: str = "LR"
    node_spacing: int = 50
    rank_spacing: int = 100
    groups: list = field(default_factory=list)
    stages: list = field(default_factory=list)
    center_node: Optional[str] = None
    timeline_order: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "direction": self.direction,
            "node_spacing": self.node_spacing,
            "rank_spacing": self.rank_spacing,
            "groups": self.groups,
            "stages": self.stages,
            "center_node": self.center_node,
            "timeline_order": self.timeline_order,
            "metadata": self.metadata
        }


@dataclass
class ProjectFeatures:
    node_count: int = 0
    max_depth: int = 0
    has_entry_point: bool = False
    entry_files: list = field(default_factory=list)
    data_file_ratio: float = 0.0
    has_stages: bool = False
    detected_stages: list = field(default_factory=list)
    has_versions: bool = False
    versioned_files: list = field(default_factory=list)
    has_core_module: bool = False
    core_modules: list = field(default_factory=list)
    directory_count: int = 0
    avg_files_per_dir: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "node_count": self.node_count,
            "max_depth": self.max_depth,
            "has_entry_point": self.has_entry_point,
            "entry_files": self.entry_files,
            "data_file_ratio": self.data_file_ratio,
            "has_stages": self.has_stages,
            "detected_stages": self.detected_stages,
            "has_versions": self.has_versions,
            "versioned_files": self.versioned_files,
            "has_core_module": self.has_core_module,
            "core_modules": self.core_modules,
            "directory_count": self.directory_count,
            "avg_files_per_dir": self.avg_files_per_dir
        }


class FeatureExtractor:
    """项目特征提取器"""
    
    ENTRY_FILE_PATTERNS = [
        "main.py", "app.py", "run.py", "server.py", "index.py",
        "__main__.py", "cli.py", "start.py", "wsgi.py", "asgi.py"
    ]
    
    STAGE_PATTERNS = {
        "data": ["data", "dataset", "raw", "input"],
        "preprocessing": ["clean", "preprocess", "transform", "etl"],
        "features": ["feature", "feat", "engineering"],
        "models": ["model", "train", "ml", "ai"],
        "evaluation": ["eval", "test", "validate", "metric"],
        "output": ["output", "result", "report", "export"],
    }
    
    VERSION_PATTERNS = [
        r"v\d+\.\d+\.\d+",
        r"v\d+",
        r"_\d{8}",
        r"_\d{4}-\d{2}-\d{2}",
    ]
    
    CORE_MODULE_PATTERNS = [
        "utils", "core", "lib", "common", "base", "helpers"
    ]
    
    def extract(self, files: list, dependencies: dict) -> ProjectFeatures:
        features = ProjectFeatures()
        
        features.node_count = len(files)
        
        features.entry_files = self._find_entry_files(files)
        features.has_entry_point = len(features.entry_files) > 0
        
        features.max_depth = self._calculate_max_depth(dependencies)
        
        features.data_file_ratio = self._calculate_data_ratio(files)
        
        stages = self._detect_stages(files)
        features.detected_stages = stages
        features.has_stages = len(stages) >= 2
        
        versioned = self._find_versioned_files(files)
        features.versioned_files = versioned
        features.has_versions = len(versioned) >= 2
        
        core = self._find_core_modules(files, dependencies)
        features.core_modules = core
        features.has_core_module = len(core) > 0
        
        features.directory_count = self._count_directories(files)
        features.avg_files_per_dir = features.node_count / max(features.directory_count, 1)
        
        return features
    
    def _find_entry_files(self, files: list) -> list:
        entry_files = []
        for file_path in files:
            filename = os.path.basename(file_path)
            if filename in self.ENTRY_FILE_PATTERNS:
                entry_files.append(file_path)
        return entry_files
    
    def _calculate_max_depth(self, dependencies: dict) -> int:
        if not dependencies:
            return 0
        
        def get_depth(node, visited=None):
            if visited is None:
                visited = set()
            if node in visited:
                return 0
            visited.add(node)
            
            deps = dependencies.get(node, {}).get("imports", [])
            if not deps:
                return 1
            return 1 + max(get_depth(dep, visited.copy()) for dep in deps)
        
        max_depth = 0
        for node in dependencies:
            depth = get_depth(node)
            max_depth = max(max_depth, depth)
        
        return max_depth
    
    def _calculate_data_ratio(self, files: list) -> float:
        data_extensions = {'.csv', '.json', '.parquet', '.xlsx', '.h5', '.pkl', '.xml'}
        data_count = sum(1 for f in files if os.path.splitext(f)[1].lower() in data_extensions)
        return data_count / len(files) if files else 0.0
    
    def _detect_stages(self, files: list) -> list:
        detected = []
        
        for stage_name, patterns in self.STAGE_PATTERNS.items():
            for file_path in files:
                lower_path = file_path.lower()
                if any(p in lower_path for p in patterns):
                    if stage_name not in detected:
                        detected.append(stage_name)
                    break
        
        return detected
    
    def _find_versioned_files(self, files: list) -> list:
        versioned = []
        for file_path in files:
            for pattern in self.VERSION_PATTERNS:
                if re.search(pattern, file_path):
                    versioned.append(file_path)
                    break
        return versioned
    
    def _find_core_modules(self, files: list, dependencies: dict) -> list:
        core_candidates = []
        
        for file_path in files:
            filename = os.path.basename(file_path).lower()
            dirname = os.path.dirname(file_path).lower()
            
            if any(p in filename or p in dirname for p in self.CORE_MODULE_PATTERNS):
                core_candidates.append(file_path)
        
        if core_candidates and dependencies:
            dep_counts = {}
            for core in core_candidates:
                count = 0
                for node, deps in dependencies.items():
                    if core in deps.get("imports", []):
                        count += 1
                dep_counts[core] = count
            
            if dep_counts:
                max_count = max(dep_counts.values())
                if max_count >= 2:
                    return [c for c, count in dep_counts.items() if count >= max_count * 0.5]
        
        return core_candidates
    
    def _count_directories(self, files: list) -> int:
        directories = set()
        for file_path in files:
            dir_path = os.path.dirname(file_path)
            if dir_path:
                directories.add(dir_path)
        return len(directories) if directories else 1


class LayoutStrategySelector:
    """布局策略选择器"""
    
    def __init__(self):
        self.feature_extractor = FeatureExtractor()
    
    def select_strategy(self, files: list, dependencies: dict) -> LayoutConfig:
        features = self.feature_extractor.extract(files, dependencies)
        
        if features.has_versions and len(features.versioned_files) >= 3:
            return self._create_timeline_layout(features)
        
        if features.has_stages and len(features.detected_stages) >= 2:
            return self._create_stage_layout(features)
        
        if features.has_core_module and features.has_entry_point:
            return self._create_star_grouped_layout(features)
        
        if features.has_entry_point and features.max_depth >= 3:
            return self._create_hierarchical_layout(features)
        
        return self._create_hybrid_layout(features)
    
    def _create_timeline_layout(self, features: ProjectFeatures) -> LayoutConfig:
        return LayoutConfig(
            strategy=LayoutStrategy.TIMELINE,
            direction="LR",
            node_spacing=80,
            rank_spacing=120,
            timeline_order=features.versioned_files,
            metadata={
                "description": "按时间/版本顺序排列",
                "feature_summary": features.to_dict()
            }
        )
    
    def _create_stage_layout(self, features: ProjectFeatures) -> LayoutConfig:
        stage_order = ["data", "preprocessing", "features", "models", "evaluation", "output"]
        ordered_stages = [s for s in stage_order if s in features.detected_stages]
        
        return LayoutConfig(
            strategy=LayoutStrategy.STAGE_PARTITION,
            direction="LR",
            node_spacing=60,
            rank_spacing=150,
            stages=ordered_stages,
            metadata={
                "description": "按数据处理阶段分区",
                "feature_summary": features.to_dict()
            }
        )
    
    def _create_star_grouped_layout(self, features: ProjectFeatures) -> LayoutConfig:
        center = features.core_modules[0] if features.core_modules else features.entry_files[0]
        
        return LayoutConfig(
            strategy=LayoutStrategy.STAR_GROUPED,
            direction="TB",
            node_spacing=70,
            rank_spacing=100,
            center_node=center,
            groups=features.core_modules,
            metadata={
                "description": "核心模块居中，其他模块环绕",
                "feature_summary": features.to_dict()
            }
        )
    
    def _create_hierarchical_layout(self, features: ProjectFeatures) -> LayoutConfig:
        return LayoutConfig(
            strategy=LayoutStrategy.HIERARCHICAL_TREE,
            direction="LR",
            node_spacing=50,
            rank_spacing=100,
            metadata={
                "description": "入口文件在左，逐层展开",
                "entry_points": features.entry_files,
                "feature_summary": features.to_dict()
            }
        )
    
    def _create_hybrid_layout(self, features: ProjectFeatures) -> LayoutConfig:
        return LayoutConfig(
            strategy=LayoutStrategy.HYBRID,
            direction="TB",
            node_spacing=60,
            rank_spacing=80,
            metadata={
                "description": "混合布局，根据节点关系自动调整",
                "feature_summary": features.to_dict()
            }
        )


class LayoutEngine:
    """布局引擎主类"""
    
    def __init__(self):
        self.strategy_selector = LayoutStrategySelector()
    
    def generate_layout(self, files: list, dependencies: dict) -> dict:
        config = self.strategy_selector.select_strategy(files, dependencies)
        
        positions = self._calculate_positions(files, dependencies, config)
        
        return {
            "config": config.to_dict(),
            "positions": positions,
            "strategy_reason": self._explain_strategy(config)
        }
    
    def _calculate_positions(self, files: list, dependencies: dict, config: LayoutConfig) -> dict:
        positions = {}
        
        if config.strategy == LayoutStrategy.HIERARCHICAL_TREE:
            positions = self._hierarchical_positions(files, dependencies, config)
        elif config.strategy == LayoutStrategy.STAGE_PARTITION:
            positions = self._stage_positions(files, config)
        elif config.strategy == LayoutStrategy.STAR_GROUPED:
            positions = self._star_positions(files, dependencies, config)
        elif config.strategy == LayoutStrategy.TIMELINE:
            positions = self._timeline_positions(files, config)
        else:
            positions = self._hybrid_positions(files, dependencies, config)
        
        return positions
    
    def _hierarchical_positions(self, files: list, dependencies: dict, config: LayoutConfig) -> dict:
        positions = {}
        entry_points = config.metadata.get("entry_points", [])
        
        levels = {}
        visited = set()
        
        for entry in entry_points:
            levels[entry] = 0
            visited.add(entry)
        
        current_level = 0
        while True:
            current_files = [f for f, l in levels.items() if l == current_level]
            if not current_files:
                break
            
            for file_path in current_files:
                deps = dependencies.get(file_path, {}).get("imports", [])
                for dep in deps:
                    if dep not in visited and dep in files:
                        levels[dep] = current_level + 1
                        visited.add(dep)
            
            current_level += 1
        
        for file_path in files:
            if file_path not in levels:
                levels[file_path] = current_level + 1
        
        level_counts = {}
        for file_path, level in levels.items():
            if level not in level_counts:
                level_counts[level] = 0
            level_counts[level] += 1
        
        level_indices = {}
        for file_path, level in levels.items():
            if level not in level_indices:
                level_indices[level] = 0
            
            if config.direction == "LR":
                x = level * config.rank_spacing
                y = level_indices[level] * config.node_spacing
            else:
                x = level_indices[level] * config.node_spacing
                y = level * config.rank_spacing
            
            positions[file_path] = {"x": x, "y": y}
            level_indices[level] += 1
        
        return positions
    
    def _stage_positions(self, files: list, config: LayoutConfig) -> dict:
        positions = {}
        stages = config.stages
        
        stage_files = {stage: [] for stage in stages}
        other_files = []
        
        for file_path in files:
            assigned = False
            lower_path = file_path.lower()
            for stage in stages:
                patterns = FeatureExtractor.STAGE_PATTERNS.get(stage, [])
                if any(p in lower_path for p in patterns):
                    stage_files[stage].append(file_path)
                    assigned = True
                    break
            if not assigned:
                other_files.append(file_path)
        
        x_offset = 0
        for stage in stages:
            files_in_stage = stage_files[stage]
            for i, file_path in enumerate(files_in_stage):
                positions[file_path] = {
                    "x": x_offset,
                    "y": i * config.node_spacing,
                    "stage": stage
                }
            x_offset += config.rank_spacing
        
        for i, file_path in enumerate(other_files):
            positions[file_path] = {
                "x": x_offset,
                "y": i * config.node_spacing,
                "stage": "other"
            }
        
        return positions
    
    def _star_positions(self, files: list, dependencies: dict, config: LayoutConfig) -> dict:
        positions = {}
        center = config.center_node
        
        if center and center in files:
            positions[center] = {"x": 0, "y": 0, "is_center": True}
        
        angle_step = 360 / max(len(files) - 1, 1)
        radius = config.rank_spacing * 2
        
        i = 0
        for file_path in files:
            if file_path == center:
                continue
            
            angle = i * angle_step
            import math
            x = radius * math.cos(math.radians(angle))
            y = radius * math.sin(math.radians(angle))
            
            positions[file_path] = {"x": x, "y": y}
            i += 1
        
        return positions
    
    def _timeline_positions(self, files: list, config: LayoutConfig) -> dict:
        positions = {}
        timeline_order = config.timeline_order
        
        for i, file_path in enumerate(timeline_order):
            positions[file_path] = {
                "x": i * config.rank_spacing,
                "y": 0,
                "order": i
            }
        
        y_offset = config.node_spacing
        other_files = [f for f in files if f not in timeline_order]
        for i, file_path in enumerate(other_files):
            positions[file_path] = {
                "x": i * config.node_spacing,
                "y": y_offset
            }
        
        return positions
    
    def _hybrid_positions(self, files: list, dependencies: dict, config: LayoutConfig) -> dict:
        positions = {}
        
        cols = int(len(files) ** 0.5) + 1
        for i, file_path in enumerate(files):
            row = i // cols
            col = i % cols
            positions[file_path] = {
                "x": col * config.node_spacing,
                "y": row * config.node_spacing
            }
        
        return positions
    
    def _explain_strategy(self, config: LayoutConfig) -> str:
        strategy_names = {
            LayoutStrategy.HIERARCHICAL_TREE: "层级树布局",
            LayoutStrategy.STAGE_PARTITION: "阶段分区布局",
            LayoutStrategy.STAR_GROUPED: "星型分组布局",
            LayoutStrategy.TIMELINE: "时间轴布局",
            LayoutStrategy.HYBRID: "混合布局"
        }
        
        name = strategy_names.get(config.strategy, "未知布局")
        reason = config.metadata.get("description", "")
        
        return f"选择 {name}：{reason}"


def generate_layout(files: list, dependencies: dict) -> dict:
    engine = LayoutEngine()
    return engine.generate_layout(files, dependencies)
