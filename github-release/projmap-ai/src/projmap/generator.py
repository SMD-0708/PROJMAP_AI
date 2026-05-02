"""ProjMap 生成器模块

本模块负责整合扫描和依赖分析结果，生成最终的 .projmap 文件。
设计原则：
1. 整合 Scanner 和 Analyzer 的输出
2. 自动识别入口文件并标记为 active_main
3. 根据依赖关系生成 Edge
4. 支持纯本地模式和 LLM 增强模式
"""

import os
from datetime import datetime
from typing import Optional

from projmap.models import (
    Node,
    Edge,
    ProjMap,
    Metadata,
    GeneratorInfo,
    ActiveState,
    NodeStatus,
    NodeType,
    EdgeType,
    generate_node_id,
    generate_edge_id,
)
from projmap.scanner import ScanResult, FileInfo, ProjectScanner
from projmap.analyzer import DependencyAnalyzer, DependencyInfo, DependencyEdge


ENTRY_FILE_NAMES = [
    "main.py", "app.py", "run.py", "server.py", "index.py",
    "main.js", "index.js", "app.js", "server.js",
    "main.go", "main.rs", "Main.java",
    "__main__.py", "index.ts", "main.ts",
]


class ProjMapGenerator:
    def __init__(
        self,
        root_path: str,
        project_name: Optional[str] = None,
        description: Optional[str] = None,
        trust_level: int = 1,
        llm_model: Optional[str] = None,
    ):
        self.root_path = os.path.abspath(root_path)
        self.project_name = project_name or os.path.basename(self.root_path)
        self.description = description
        self.trust_level = trust_level
        self.llm_model = llm_model
        self._node_map: dict[str, Node] = {}
        self._dep_analyzer: Optional[DependencyAnalyzer] = None

    def _is_entry_file(self, file_info: FileInfo) -> bool:
        if file_info.name in ENTRY_FILE_NAMES:
            return True
        
        if file_info.name == "__main__.py":
            return True
        
        return False

    def _infer_node_name(self, file_info: FileInfo) -> str:
        name = os.path.splitext(file_info.name)[0]
        
        name = name.replace("_", " ").replace("-", " ")
        name = name.title()
        
        return name

    def _create_node(self, file_info: FileInfo, is_entry: bool = False) -> Node:
        node_id = generate_node_id(file_info.relative_path)
        
        node = Node(
            id=node_id,
            name=self._infer_node_name(file_info),
            file_path=file_info.relative_path,
            file_name=file_info.name,
            status=NodeStatus.ACTIVE_MAIN if is_entry else NodeStatus.ACTIVE_BRANCH,
            type=NodeType.FILE,
            language=file_info.language,
            is_entry=is_entry,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        return node

    def _create_edge(
        self,
        source_node: Node,
        target_node: Node,
        dep_edge: DependencyEdge,
    ) -> Edge:
        edge_id = generate_edge_id(source_node.id, target_node.id, EdgeType.IMPORTS)
        
        return Edge(
            id=edge_id,
            source=source_node.id,
            target=target_node.id,
            type=EdgeType.IMPORTS,
            description=f"{source_node.file_name} imports from {target_node.file_name}",
        )

    def _update_node_with_deps(
        self,
        node: Node,
        dep_info: DependencyInfo,
    ) -> None:
        imports = [imp.module for imp in dep_info.imports]
        exports = [exp.name for exp in dep_info.exports]
        
        node.imports = imports
        node.exports = exports

    def generate(
        self,
        scanner: Optional[ProjectScanner] = None,
        excludes: Optional[list[str]] = None,
    ) -> ProjMap:
        if scanner is None:
            scanner = ProjectScanner(
                root_path=self.root_path,
                excludes=excludes,
            )
        
        scan_result = scanner.scan()
        
        file_list = [f.to_dict() for f in scan_result.files]
        self._dep_analyzer = DependencyAnalyzer(self.root_path, [f["path"] for f in file_list])
        
        entry_files = scanner.get_entry_files()
        entry_paths = {f.relative_path for f in entry_files}
        
        nodes: list[Node] = []
        edges: list[Edge] = []
        
        for file_info in scan_result.files:
            is_entry = file_info.relative_path in entry_paths
            node = self._create_node(file_info, is_entry)
            self._node_map[file_info.relative_path] = node
            
            if file_info.language:
                dep_info = self._dep_analyzer.analyze_file(
                    file_info.path,
                    file_info.language,
                )
                self._update_node_with_deps(node, dep_info)
            
            nodes.append(node)
        
        for file_info in scan_result.files:
            if not file_info.language:
                continue
            
            dep_info = self._dep_analyzer.analyze_file(
                file_info.path,
                file_info.language,
            )
            
            source_node = self._node_map.get(file_info.relative_path)
            if not source_node:
                continue
            
            dep_edges = self._dep_analyzer.resolve_dependencies(dep_info)
            
            for dep_edge in dep_edges:
                target_node = self._node_map.get(dep_edge.target_file)
                if target_node:
                    edge = self._create_edge(source_node, target_node, dep_edge)
                    edges.append(edge)
        
        metadata = Metadata(
            project_name=self.project_name,
            project_root=self.root_path,
            description=self.description,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            generator=GeneratorInfo(name="projmap-cli", version="0.1.0"),
            trust_level=self.trust_level,
            llm_model=self.llm_model,
        )
        
        active_main = None
        active_branches = []
        
        for node in nodes:
            if node.status == NodeStatus.ACTIVE_MAIN:
                if active_main is None:
                    active_main = node.id
                else:
                    node.status = NodeStatus.ACTIVE_BRANCH
                    active_branches.append(node.id)
            elif node.status == NodeStatus.ACTIVE_BRANCH:
                active_branches.append(node.id)
        
        active_state = ActiveState(
            active_main=active_main,
            active_branches=active_branches,
        )
        
        projmap = ProjMap(
            version="1.0",
            metadata=metadata,
            nodes=nodes,
            edges=edges,
            decisions=[],
            active_state=active_state,
        )
        
        return projmap


def generate_projmap(
    root_path: str,
    project_name: Optional[str] = None,
    description: Optional[str] = None,
    trust_level: int = 1,
    llm_model: Optional[str] = None,
    excludes: Optional[list[str]] = None,
) -> ProjMap:
    generator = ProjMapGenerator(
        root_path=root_path,
        project_name=project_name,
        description=description,
        trust_level=trust_level,
        llm_model=llm_model,
    )
    return generator.generate(excludes=excludes)
