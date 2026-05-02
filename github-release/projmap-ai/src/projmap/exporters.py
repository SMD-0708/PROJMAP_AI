"""导出器模块

支持多种导出格式：Mermaid、PlantUML、DOT 等。
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

from projmap.models import ProjMap, NodeStatus, NodeType

logger = logging.getLogger(__name__)


class BaseExporter(ABC):
    """导出器基类"""
    
    @property
    @abstractmethod
    def format_name(self) -> str:
        """格式名称"""
        pass
    
    @property
    @abstractmethod
    def file_extension(self) -> str:
        """文件扩展名"""
        pass
    
    @abstractmethod
    def export(self, projmap: ProjMap) -> str:
        """导出为字符串"""
        pass
    
    def export_to_file(self, projmap: ProjMap, output_path: str) -> bool:
        """导出到文件"""
        try:
            content = self.export(projmap)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"导出成功: {output_path}")
            return True
        except Exception as e:
            logger.error(f"导出失败: {e}")
            return False


class MermaidExporter(BaseExporter):
    """Mermaid 导出器"""
    
    @property
    def format_name(self) -> str:
        return "Mermaid"
    
    @property
    def file_extension(self) -> str:
        return ".mmd"
    
    def export(self, projmap: ProjMap) -> str:
        lines = ["graph TD"]
        
        # 节点样式映射
        status_styles = {
            NodeStatus.ACTIVE_MAIN: "fill:#4CAF50,stroke:#2E7D32",
            NodeStatus.ACTIVE_BRANCH: "fill:#2196F3,stroke:#1565C0",
            NodeStatus.DORMANT: "fill:#FFC107,stroke:#FF8F00",
            NodeStatus.ARCHIVED: "fill:#9E9E9E,stroke:#616161",
        }
        
        # 添加节点
        node_map = {n.id: n for n in projmap.nodes}
        
        for node in projmap.nodes:
            # 节点ID（去除特殊字符）
            node_id = f"node_{node.id[:8]}"
            
            # 节点标签
            label = node.name
            if node.description:
                label = f"{node.name}<br/><small>{node.description[:30]}...</small>"
            
            # 节点形状根据类型
            if node.type == NodeType.PACKAGE:
                lines.append(f"    {node_id}[{label}]")
            elif node.type == NodeType.DIRECTORY:
                lines.append(f"    {node_id}{{ {label} }}")
            else:
                lines.append(f"    {node_id}({label})")
            
            # 样式
            style = status_styles.get(node.status, "")
            if style:
                lines.append(f"    style {node_id} {style}")
        
        # 添加边
        for edge in projmap.edges:
            source_id = f"node_{edge.source[:8]}"
            target_id = f"node_{edge.target[:8]}"
            
            if source_id in [f"node_{n.id[:8]}" for n in projmap.nodes] and \
               target_id in [f"node_{n.id[:8]}" for n in projmap.nodes]:
                lines.append(f"    {source_id} -->|{edge.type.value}| {target_id}")
        
        return "\n".join(lines)


class PlantUMLExporter(BaseExporter):
    """PlantUML 导出器"""
    
    @property
    def format_name(self) -> str:
        return "PlantUML"
    
    @property
    def file_extension(self) -> str:
        return ".puml"
    
    def export(self, projmap: ProjMap) -> str:
        lines = [
            "@startuml",
            f"title {projmap.metadata.project_name} - Project Map",
            "",
            "skinparam componentStyle rectangle",
        ]
        
        # 颜色定义
        lines.extend([
            "skinparam component {",
            "    BackgroundColor<<main>> LightGreen",
            "    BackgroundColor<<branch>> LightBlue",
            "    BackgroundColor<<dormant>> LightYellow",
            "    BackgroundColor<<archived>> LightGray",
            "}",
            "",
        ])
        
        # 添加组件
        status_stereotypes = {
            NodeStatus.ACTIVE_MAIN: "<<main>>",
            NodeStatus.ACTIVE_BRANCH: "<<branch>>",
            NodeStatus.DORMANT: "<<dormant>>",
            NodeStatus.ARCHIVED: "<<archived>>",
        }
        
        for node in projmap.nodes:
            comp_id = f"comp_{node.id[:8]}"
            stereotype = status_stereotypes.get(node.status, "")
            
            if node.type == NodeType.PACKAGE:
                lines.append(f'package "{node.name}" {stereotype} as {comp_id} {{}}')
            else:
                lines.append(f'component "{node.name}" {stereotype} as {comp_id}')
        
        lines.append("")
        
        # 添加依赖
        for edge in projmap.edges:
            source_id = f"comp_{edge.source[:8]}"
            target_id = f"comp_{edge.target[:8]}"
            lines.append(f"{source_id} --> {target_id} : {edge.type.value}")
        
        lines.append("")
        lines.append("@enduml")
        
        return "\n".join(lines)


class DOTExporter(BaseExporter):
    """Graphviz DOT 导出器"""
    
    @property
    def format_name(self) -> str:
        return "DOT"
    
    @property
    def file_extension(self) -> str:
        return ".dot"
    
    def export(self, projmap: ProjMap) -> str:
        lines = [
            "digraph ProjectMap {",
            f'    label="{projmap.metadata.project_name}";',
            "    labelloc=t;",
            "    fontsize=20;",
            "    node [shape=box, style=rounded];",
            "",
        ]
        
        # 颜色映射
        status_colors = {
            NodeStatus.ACTIVE_MAIN: "#4CAF50",
            NodeStatus.ACTIVE_BRANCH: "#2196F3",
            NodeStatus.DORMANT: "#FFC107",
            NodeStatus.ARCHIVED: "#9E9E9E",
        }
        
        # 添加节点
        for node in projmap.nodes:
            node_id = f"\"{node.id[:8]}\""
            color = status_colors.get(node.status, "#FFFFFF")
            
            attrs = [
                f'label="{node.name}"',
                f'fillcolor="{color}"',
                'style="filled"',
            ]
            
            if node.type == NodeType.PACKAGE:
                attrs.append('shape=folder')
            elif node.type == NodeType.DIRECTORY:
                attrs.append('shape=house')
            
            lines.append(f"    {node_id} [{', '.join(attrs)}];")
        
        lines.append("")
        
        # 添加边
        for edge in projmap.edges:
            source_id = f"\"{edge.source[:8]}\""
            target_id = f"\"{edge.target[:8]}\""
            lines.append(f"    {source_id} -> {target_id} [label=\"{edge.type.value}\"];")
        
        lines.append("}")
        
        return "\n".join(lines)


class JSONExporter(BaseExporter):
    """JSON 导出器"""
    
    @property
    def format_name(self) -> str:
        return "JSON"
    
    @property
    def file_extension(self) -> str:
        return ".json"
    
    def export(self, projmap: ProjMap) -> str:
        return json.dumps(projmap.to_dict(), ensure_ascii=False, indent=2)


# 导出器注册表
EXPORTERS = {
    "mermaid": MermaidExporter,
    "plantuml": PlantUMLExporter,
    "dot": DOTExporter,
    "json": JSONExporter,
}


def get_exporter(format_name: str) -> Optional[BaseExporter]:
    """获取导出器实例"""
    if format_name.lower() in EXPORTERS:
        return EXPORTERS[format_name.lower()]()
    return None


def list_exporters() -> list[dict]:
    """列出所有可用导出器"""
    return [
        {
            "name": name,
            "format": exporter().format_name,
            "extension": exporter().file_extension,
        }
        for name, exporter in EXPORTERS.items()
    ]
