"""多类型链路识别器

识别项目中的多种链路类型：
- 数据流：文件读写、数据传递
- 控制流：函数调用链
- 时序流：执行顺序、版本演进
- 配置依赖：配置文件读取
- 继承关系：类继承、接口实现
- 逻辑分组：目录结构、功能聚类
"""

import ast
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LinkType(Enum):
    DATA_FLOW = "data_flow"
    CONTROL_FLOW = "control_flow"
    TEMPORAL_FLOW = "temporal_flow"
    CONFIG_DEPENDENCY = "config_dependency"
    INHERITANCE = "inheritance"
    LOGICAL_GROUP = "logical_group"


@dataclass
class Link:
    source: str
    target: str
    link_type: LinkType
    label: str = ""
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "link_type": self.link_type.value,
            "label": self.label,
            "weight": self.weight,
            "metadata": self.metadata
        }


@dataclass
class NodeGroup:
    group_id: str
    group_name: str
    nodes: list
    group_type: str = "directory"
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "nodes": self.nodes,
            "group_type": self.group_type,
            "metadata": self.metadata
        }


class DataFlowAnalyzer:
    """数据流分析器 - 识别文件读写和数据传递"""
    
    DATA_PATTERNS = {
        "read_csv": r"pd\.read_csv\s*\(\s*['\"]([^'\"]+)['\"]",
        "read_excel": r"pd\.read_excel\s*\(\s*['\"]([^'\"]+)['\"]",
        "read_parquet": r"pd\.read_parquet\s*\(\s*['\"]([^'\"]+)['\"]",
        "read_json": r"pd\.read_json\s*\(\s*['\"]([^'\"]+)['\"]",
        "read_pickle": r"pd\.read_pickle\s*\(\s*['\"]([^'\"]+)['\"]",
        "to_csv": r"\.to_csv\s*\(\s*['\"]([^'\"]+)['\"]",
        "to_excel": r"\.to_excel\s*\(\s*['\"]([^'\"]+)['\"]",
        "to_parquet": r"\.to_parquet\s*\(\s*['\"]([^'\"]+)['\"]",
        "to_json": r"\.to_json\s*\(\s*['\"]([^'\"]+)['\"]",
        "open_read": r"open\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]r['\"]",
        "open_write": r"open\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]w['\"]",
    }
    
    def analyze(self, file_path: str, content: str) -> list[Link]:
        links = []
        
        for pattern_name, pattern in self.DATA_PATTERNS.items():
            matches = re.findall(pattern, content)
            for match in matches:
                is_input = "read" in pattern_name or pattern_name == "open_read"
                
                link = Link(
                    source=file_path if not is_input else match,
                    target=match if not is_input else file_path,
                    link_type=LinkType.DATA_FLOW,
                    label=self._generate_label(pattern_name, match),
                    weight=self._calculate_weight(pattern_name),
                    metadata={
                        "operation": pattern_name,
                        "data_file": match
                    }
                )
                links.append(link)
        
        return links
    
    def _generate_label(self, operation: str, data_file: str) -> str:
        filename = os.path.basename(data_file)
        if "read" in operation:
            return f"读取 {filename}"
        elif "to_" in operation or "write" in operation:
            return f"产出 {filename}"
        return f"数据: {filename}"
    
    def _calculate_weight(self, operation: str) -> float:
        weight_map = {
            "read_csv": 1.5,
            "read_parquet": 1.5,
            "to_csv": 1.5,
            "to_parquet": 1.5,
            "read_excel": 1.2,
            "to_excel": 1.2,
            "read_json": 1.0,
            "to_json": 1.0,
        }
        return weight_map.get(operation, 1.0)


class ControlFlowAnalyzer:
    """控制流分析器 - 识别函数调用链"""
    
    def analyze(self, file_path: str, content: str, project_files: dict) -> list[Link]:
        links = []
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return links
        
        current_module = self._get_module_name(file_path)
        imported_modules = self._extract_imports(tree)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_info = self._analyze_call(node, imported_modules, project_files)
                if call_info:
                    link = Link(
                        source=file_path,
                        target=call_info["target_file"],
                        link_type=LinkType.CONTROL_FLOW,
                        label=call_info["label"],
                        weight=0.8,
                        metadata={
                            "function": call_info["function"],
                            "module": call_info.get("module")
                        }
                    )
                    links.append(link)
        
        return links
    
    def _get_module_name(self, file_path: str) -> str:
        return os.path.splitext(os.path.basename(file_path))[0]
    
    def _extract_imports(self, tree: ast.AST) -> dict:
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports[alias.asname or alias.name] = f"{module}.{alias.name}"
        return imports
    
    def _analyze_call(self, node: ast.Call, imports: dict, project_files: dict) -> Optional[dict]:
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in imports:
                module = imports[func_name]
                if module in project_files:
                    return {
                        "target_file": project_files[module],
                        "function": func_name,
                        "label": f"调用 {func_name}()",
                        "module": module
                    }
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                module_name = node.func.value.id
                func_name = node.func.attr
                if module_name in imports:
                    full_module = imports[module_name]
                    if full_module in project_files:
                        return {
                            "target_file": project_files[full_module],
                            "function": func_name,
                            "label": f"调用 {module_name}.{func_name}()",
                            "module": full_module
                        }
        return None


class TemporalFlowAnalyzer:
    """时序流分析器 - 识别执行顺序和版本演进"""
    
    VERSION_PATTERNS = [
        r"v(\d+\.\d+\.\d+)",
        r"v(\d+)",
        r"_(\d{8})",
        r"_(\d{4}-\d{2}-\d{2})",
        r"_(\d{6})",
    ]
    
    def analyze(self, files: list[str], git_log: Optional[list] = None) -> list[Link]:
        links = []
        
        versioned_files = self._extract_versioned_files(files)
        
        sorted_files = sorted(versioned_files, key=lambda x: x["version"])
        
        for i in range(len(sorted_files) - 1):
            current = sorted_files[i]
            next_file = sorted_files[i + 1]
            
            link = Link(
                source=current["path"],
                target=next_file["path"],
                link_type=LinkType.TEMPORAL_FLOW,
                label=f"{current['version']} → {next_file['version']}",
                weight=0.6,
                metadata={
                    "from_version": current["version"],
                    "to_version": next_file["version"]
                }
            )
            links.append(link)
        
        if git_log:
            git_links = self._analyze_git_history(git_log)
            links.extend(git_links)
        
        return links
    
    def _extract_versioned_files(self, files: list[str]) -> list[dict]:
        versioned = []
        for file_path in files:
            for pattern in self.VERSION_PATTERNS:
                match = re.search(pattern, file_path)
                if match:
                    versioned.append({
                        "path": file_path,
                        "version": match.group(1)
                    })
                    break
        return versioned
    
    def _analyze_git_history(self, git_log: list) -> list[Link]:
        return []


class ConfigDependencyAnalyzer:
    """配置依赖分析器 - 识别配置文件读取"""
    
    CONFIG_PATTERNS = {
        "yaml": [r"yaml\.load\s*\(\s*open\s*\(\s*['\"]([^'\"]+)['\"]", r"yaml\.safe_load\s*\(\s*open\s*\(\s*['\"]([^'\"]+)['\"]"],
        "json": [r"json\.load\s*\(\s*open\s*\(\s*['\"]([^'\"]+)['\"]"],
        "env": [r"os\.getenv\s*\(\s*['\"]([^'\"]+)['\"]", r"os\.environ\[['\"]([^'\"]+)['\"]\]"],
        "toml": [r"toml\.load\s*\(\s*['\"]([^'\"]+)['\"]"],
        "ini": [r"configparser\.ConfigParser\(\).*?read\s*\(\s*['\"]([^'\"]+)['\"]"],
    }
    
    def analyze(self, file_path: str, content: str) -> list[Link]:
        links = []
        
        for config_type, patterns in self.CONFIG_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, content, re.DOTALL)
                for match in matches:
                    link = Link(
                        source=file_path,
                        target=match if match.endswith(('.yaml', '.yml', '.json', '.toml', '.ini', '.env')) else f".env:{match}",
                        link_type=LinkType.CONFIG_DEPENDENCY,
                        label=f"配置: {match}" if not match.startswith('.') else f"环境变量: {match}",
                        weight=0.5,
                        metadata={
                            "config_type": config_type,
                            "config_key": match
                        }
                    )
                    links.append(link)
        
        return links


class InheritanceAnalyzer:
    """继承关系分析器 - 识别类继承和接口实现"""
    
    def analyze(self, file_path: str, content: str, project_classes: dict) -> list[Link]:
        links = []
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return links
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                
                for base in node.bases:
                    base_name = self._get_base_name(base)
                    
                    if base_name in project_classes:
                        link = Link(
                            source=file_path,
                            target=project_classes[base_name],
                            link_type=LinkType.INHERITANCE,
                            label=f"{class_name} 继承 {base_name}",
                            weight=1.2,
                            metadata={
                                "child_class": class_name,
                                "parent_class": base_name
                            }
                        )
                        links.append(link)
        
        return links
    
    def _get_base_name(self, base: ast.expr) -> str:
        if isinstance(base, ast.Name):
            return base.id
        elif isinstance(base, ast.Attribute):
            return base.attr
        return ""
    
    def extract_classes(self, file_path: str, content: str) -> dict:
        classes = {}
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes[node.name] = file_path
        except SyntaxError:
            pass
        return classes


class LogicalGroupAnalyzer:
    """逻辑分组分析器 - 识别目录结构和功能聚类"""
    
    def analyze(self, files: list[str]) -> list[NodeGroup]:
        groups = {}
        
        for file_path in files:
            dir_path = os.path.dirname(file_path)
            if not dir_path:
                dir_path = "root"
            
            if dir_path not in groups:
                groups[dir_path] = {
                    "nodes": [],
                    "common_prefix": ""
                }
            groups[dir_path]["nodes"].append(file_path)
        
        result = []
        for dir_path, group_data in groups.items():
            if len(group_data["nodes"]) > 1:
                group = NodeGroup(
                    group_id=f"group_{dir_path.replace('/', '_').replace('\\', '_')}",
                    group_name=self._generate_group_name(dir_path),
                    nodes=group_data["nodes"],
                    group_type="directory",
                    metadata={"directory": dir_path}
                )
                result.append(group)
        
        return result
    
    def _generate_group_name(self, dir_path: str) -> str:
        name_map = {
            "src": "源代码",
            "tests": "测试",
            "docs": "文档",
            "data": "数据",
            "scripts": "脚本",
            "utils": "工具函数",
            "models": "模型",
            "views": "视图",
            "controllers": "控制器",
            "api": "API接口",
            "config": "配置",
            "features": "特征工程",
            "notebooks": "笔记本",
        }
        
        dir_name = os.path.basename(dir_path)
        return name_map.get(dir_name, dir_name)


class LinkAnalyzer:
    """链路分析主类 - 整合所有分析器"""
    
    def __init__(self):
        self.data_flow_analyzer = DataFlowAnalyzer()
        self.control_flow_analyzer = ControlFlowAnalyzer()
        self.temporal_flow_analyzer = TemporalFlowAnalyzer()
        self.config_analyzer = ConfigDependencyAnalyzer()
        self.inheritance_analyzer = InheritanceAnalyzer()
        self.group_analyzer = LogicalGroupAnalyzer()
    
    def analyze_project(
        self,
        files: dict[str, str],
        git_log: Optional[list] = None
    ) -> dict:
        all_links = []
        project_classes = {}
        
        for file_path, content in files.items():
            if file_path.endswith('.py'):
                classes = self.inheritance_analyzer.extract_classes(file_path, content)
                project_classes.update(classes)
        
        project_modules = {}
        for file_path in files:
            if file_path.endswith('.py'):
                module_name = os.path.splitext(os.path.basename(file_path))[0]
                project_modules[module_name] = file_path
        
        for file_path, content in files.items():
            if file_path.endswith('.py'):
                data_links = self.data_flow_analyzer.analyze(file_path, content)
                all_links.extend(data_links)
                
                control_links = self.control_flow_analyzer.analyze(
                    file_path, content, project_modules
                )
                all_links.extend(control_links)
                
                config_links = self.config_analyzer.analyze(file_path, content)
                all_links.extend(config_links)
                
                inheritance_links = self.inheritance_analyzer.analyze(
                    file_path, content, project_classes
                )
                all_links.extend(inheritance_links)
        
        file_list = list(files.keys())
        temporal_links = self.temporal_flow_analyzer.analyze(file_list, git_log)
        all_links.extend(temporal_links)
        
        groups = self.group_analyzer.analyze(file_list)
        
        return {
            "links": [link.to_dict() for link in all_links],
            "groups": [group.to_dict() for group in groups],
            "statistics": self._calculate_statistics(all_links)
        }
    
    def _calculate_statistics(self, links: list[Link]) -> dict:
        stats = {
            "total_links": len(links),
            "by_type": {},
            "avg_weight": 0.0
        }
        
        type_counts = {}
        total_weight = 0.0
        
        for link in links:
            link_type = link.link_type.value
            type_counts[link_type] = type_counts.get(link_type, 0) + 1
            total_weight += link.weight
        
        stats["by_type"] = type_counts
        stats["avg_weight"] = total_weight / len(links) if links else 0.0
        
        return stats


def analyze_links(files: dict[str, str], git_log: Optional[list] = None) -> dict:
    analyzer = LinkAnalyzer()
    return analyzer.analyze_project(files, git_log)
