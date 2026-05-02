"""HTML生成器模块

核心功能：将.projmap数据内嵌到HTML模板中，生成可直接双击打开的脉络图HTML文件。

解决问题：
- 浏览器安全策略（CORS）禁止本地HTML通过fetch()读取本地JSON文件
- 通过数据内嵌模式，实现零网络请求、双击即看

使用方式：
    from projmap.html_generator import HTMLGenerator
    
    generator = HTMLGenerator()
    generator.generate(
        projmap_data={"nodes": [...], "edges": [...]},
        output_path="my_project_map.html",
        project_name="My Project"
    )
"""

import json
import os
from datetime import datetime
from typing import Optional, Any
from pathlib import Path


class HTMLGenerator:
    """HTML脉络图生成器
    
    将.projmap数据内嵌到HTML模板中，生成可独立运行的HTML文件。
    """
    
    DEFAULT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "web", "template.html")
    
    def __init__(self, template_path: Optional[str] = None):
        self.template_path = template_path or self.DEFAULT_TEMPLATE_PATH
        self._template_cache: Optional[str] = None
    
    def _load_template(self) -> str:
        if self._template_cache is None:
            if not os.path.exists(self.template_path):
                raise FileNotFoundError(f"HTML模板文件不存在: {self.template_path}")
            
            with open(self.template_path, "r", encoding="utf-8") as f:
                self._template_cache = f.read()
        
        return self._template_cache
    
    def generate(
        self,
        projmap_data: dict,
        output_path: str,
        project_name: Optional[str] = None,
        title: Optional[str] = None,
        include_metadata: bool = True,
        minify_json: bool = False,
    ) -> str:
        if include_metadata and "_metadata" not in projmap_data:
            projmap_data["_metadata"] = {
                "generated_at": datetime.now().isoformat(),
                "generator": "ProjMap HTML Generator v2.0",
                "project_name": project_name or "Unknown Project",
            }
        
        if minify_json:
            json_str = json.dumps(projmap_data, ensure_ascii=False, separators=(',', ':'))
        else:
            json_str = json.dumps(projmap_data, ensure_ascii=False, indent=2)
        
        template = self._load_template()
        
        template = template.replace("{{DATA_PLACEHOLDER}}", json_str)
        
        final_project_name = project_name or projmap_data.get("metadata", {}).get("project_name", "ProjMap")
        template = template.replace("{{PROJECT_NAME}}", final_project_name)
        
        if title:
            template = template.replace("<title>ProjMap - 项目脉络图</title>", f"<title>{title}</title>")
        
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(template)
        
        return output_path
    
    def generate_from_file(
        self,
        projmap_file: str,
        output_path: Optional[str] = None,
        **kwargs
    ) -> str:
        if not os.path.exists(projmap_file):
            raise FileNotFoundError(f".projmap文件不存在: {projmap_file}")
        
        with open(projmap_file, "r", encoding="utf-8") as f:
            projmap_data = json.load(f)
        
        if output_path is None:
            base_name = os.path.splitext(projmap_file)[0]
            output_path = f"{base_name}_map.html"
        
        project_name = kwargs.pop("project_name", None)
        if project_name is None:
            project_name = projmap_data.get("metadata", {}).get("project_name", os.path.basename(projmap_file))
        
        return self.generate(projmap_data, output_path, project_name=project_name, **kwargs)
    
    def generate_batch(
        self,
        projmap_files: list[str],
        output_dir: str,
        **kwargs
    ) -> list[str]:
        generated_files = []
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        for projmap_file in projmap_files:
            base_name = os.path.splitext(os.path.basename(projmap_file))[0]
            output_path = os.path.join(output_dir, f"{base_name}_map.html")
            
            try:
                result = self.generate_from_file(projmap_file, output_path, **kwargs)
                generated_files.append(result)
            except Exception as e:
                print(f"生成失败: {projmap_file} - {e}")
        
        return generated_files
    
    def preview_data(self, projmap_data: dict, max_nodes: int = 10) -> dict:
        preview = {
            "version": projmap_data.get("version", "unknown"),
            "metadata": projmap_data.get("metadata", {}),
            "node_count": len(projmap_data.get("nodes", [])),
            "edge_count": len(projmap_data.get("edges", [])),
            "decision_count": len(projmap_data.get("decisions", [])),
            "sample_nodes": projmap_data.get("nodes", [])[:max_nodes],
        }
        return preview


def generate_html(
    projmap_data: dict,
    output_path: str,
    project_name: Optional[str] = None,
    template_path: Optional[str] = None,
) -> str:
    generator = HTMLGenerator(template_path)
    return generator.generate(projmap_data, output_path, project_name)


def generate_html_from_file(
    projmap_file: str,
    output_path: Optional[str] = None,
) -> str:
    generator = HTMLGenerator()
    return generator.generate_from_file(projmap_file, output_path)


def create_standalone_html(
    nodes: list[dict],
    edges: list[dict],
    decisions: Optional[list[dict]] = None,
    metadata: Optional[dict] = None,
    output_path: str = "project_map.html",
    project_name: str = "My Project",
) -> str:
    projmap_data = {
        "version": "2.0",
        "metadata": metadata or {
            "project_name": project_name,
            "created_at": datetime.now().isoformat(),
        },
        "nodes": nodes,
        "edges": edges,
        "decisions": decisions or [],
    }
    
    return generate_html(projmap_data, output_path, project_name)
