"""CI/CD 集成模块

支持 GitHub Actions 等 CI/CD 平台，自动更新项目文档。
核心特性：
- GitHub Actions 工作流生成
- 自动扫描和更新 .projmap
- PR 评论集成
- 变更报告生成
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from projmap.models import ProjMap
from projmap.incremental_scanner import IncrementalScanResult

logger = logging.getLogger(__name__)


GITHUB_ACTIONS_TEMPLATE = """# ProjMap CI/CD 集成
# 自动生成项目认知地图

name: ProjMap Update

on:
  push:
    branches: [ main, master, develop ]
  pull_request:
    branches: [ main, master ]
  workflow_dispatch:  # 允许手动触发

jobs:
  update-projmap:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
      with:
        fetch-depth: 0  # 获取完整历史用于增量扫描
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'
    
    - name: Install ProjMap
      run: |
        pip install projmap
    
    - name: Run ProjMap Scan
      run: |
        projmap scan --incremental --output project.projmap
      env:
        PROJMAP_TRUST_LEVEL: ${{ secrets.PROJMAP_TRUST_LEVEL || '3' }}
    
    - name: Generate Change Report
      run: |
        projmap report --format markdown --output PROJMAP_CHANGES.md
    
    - name: Commit changes (on push)
      if: github.event_name == 'push'
      run: |
        git config --local user.email "action@github.com"
        git config --local user.name "GitHub Action"
        git add project.projmap PROJMAP_CHANGES.md
        git diff --quiet && git diff --staged --quiet || git commit -m "chore: update project cognitive map [skip ci]"
        git push
    
    - name: Comment on PR
      if: github.event_name == 'pull_request'
      uses: actions/github-script@v7
      with:
        script: |
          const fs = require('fs');
          const report = fs.readFileSync('PROJMAP_CHANGES.md', 'utf8');
          
          github.rest.issues.createComment({
            issue_number: context.issue.number,
            owner: context.repo.owner,
            repo: context.repo.repo,
            body: `## 📊 ProjMap 变更报告\\n\\n${report}`
          });
"""


@dataclass
class ChangeReport:
    """变更报告"""
    added_files: list[str]
    modified_files: list[str]
    deleted_files: list[str]
    new_dependencies: list[dict]
    removed_dependencies: list[dict]
    complexity_delta: int
    timestamp: datetime


class CIIntegrationManager:
    """CI/CD 集成管理器"""
    
    def __init__(self, project_path: str = "."):
        self.project_path = project_path
        self._logger = logging.getLogger("projmap.ci_integration")
    
    def generate_github_actions_workflow(self) -> str:
        """生成 GitHub Actions 工作流文件"""
        return GITHUB_ACTIONS_TEMPLATE
    
    def setup_github_actions(self) -> bool:
        """设置 GitHub Actions 集成
        
        在工作流目录创建配置文件。
        """
        workflow_dir = os.path.join(self.project_path, ".github", "workflows")
        
        try:
            os.makedirs(workflow_dir, exist_ok=True)
            
            workflow_file = os.path.join(workflow_dir, "projmap.yml")
            
            with open(workflow_file, "w", encoding="utf-8") as f:
                f.write(GITHUB_ACTIONS_TEMPLATE)
            
            self._logger.info(f"GitHub Actions 工作流已创建: {workflow_file}")
            return True
            
        except Exception as e:
            self._logger.error(f"设置 GitHub Actions 失败: {e}")
            return False
    
    def generate_change_report(
        self,
        changes: IncrementalScanResult,
        old_projmap: Optional[ProjMap] = None,
        new_projmap: Optional[ProjMap] = None,
    ) -> ChangeReport:
        """生成变更报告"""
        new_deps = []
        removed_deps = []
        complexity_delta = 0
        
        if old_projmap and new_projmap:
            # 计算依赖变化
            old_edges = {(e.source, e.target, e.type.value) for e in old_projmap.edges}
            new_edges = {(e.source, e.target, e.type.value) for e in new_projmap.edges}
            
            added_edges = new_edges - old_edges
            removed_edges = old_edges - new_edges
            
            new_deps = [{"source": s, "target": t, "type": tp} for s, t, tp in added_edges]
            removed_deps = [{"source": s, "target": t, "type": tp} for s, t, tp in removed_edges]
            
            # 计算复杂度变化（简化：节点数 + 边数）
            old_complexity = len(old_projmap.nodes) + len(old_projmap.edges)
            new_complexity = len(new_projmap.nodes) + len(new_projmap.edges)
            complexity_delta = new_complexity - old_complexity
        
        return ChangeReport(
            added_files=changes.added,
            modified_files=changes.modified,
            deleted_files=changes.deleted,
            new_dependencies=new_deps,
            removed_dependencies=removed_deps,
            complexity_delta=complexity_delta,
            timestamp=datetime.now(),
        )
    
    def format_report_markdown(self, report: ChangeReport) -> str:
        """格式化为 Markdown 报告"""
        lines = [
            "# ProjMap 变更报告",
            "",
            f"生成时间: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 📁 文件变更",
            "",
        ]
        
        # 新增文件
        if report.added_files:
            lines.append(f"### ➕ 新增 ({len(report.added_files)})")
            for f in report.added_files[:10]:  # 最多显示10个
                lines.append(f"- `{f}`")
            if len(report.added_files) > 10:
                lines.append(f"- ... 和另外 {len(report.added_files) - 10} 个文件")
            lines.append("")
        
        # 修改的文件
        if report.modified_files:
            lines.append(f"### ✏️ 修改 ({len(report.modified_files)})")
            for f in report.modified_files[:10]:
                lines.append(f"- `{f}`")
            if len(report.modified_files) > 10:
                lines.append(f"- ... 和另外 {len(report.modified_files) - 10} 个文件")
            lines.append("")
        
        # 删除的文件
        if report.deleted_files:
            lines.append(f"### 🗑️ 删除 ({len(report.deleted_files)})")
            for f in report.deleted_files[:10]:
                lines.append(f"- `{f}`")
            if len(report.deleted_files) > 10:
                lines.append(f"- ... 和另外 {len(report.deleted_files) - 10} 个文件")
            lines.append("")
        
        # 依赖变化
        if report.new_dependencies or report.removed_dependencies:
            lines.append("## 🔗 依赖变化")
            lines.append("")
            
            if report.new_dependencies:
                lines.append(f"### 新增依赖 ({len(report.new_dependencies)})")
                for dep in report.new_dependencies[:5]:
                    lines.append(f"- `{dep['source'][:8]}...` → `{dep['target'][:8]}...` ({dep['type']})")
                lines.append("")
            
            if report.removed_dependencies:
                lines.append(f"### 移除依赖 ({len(report.removed_dependencies)})")
                for dep in report.removed_dependencies[:5]:
                    lines.append(f"- ~~`{dep['source'][:8]}...` → `{dep['target'][:8]}...`~~")
                lines.append("")
        
        # 复杂度
        if report.complexity_delta != 0:
            emoji = "📈" if report.complexity_delta > 0 else "📉"
            lines.append(f"## {emoji} 复杂度变化")
            lines.append(f"")
            lines.append(f"项目复杂度 {'增加' if report.complexity_delta > 0 else '减少'}了 **{abs(report.complexity_delta)}**")
            lines.append("")
        
        return "\n".join(lines)
    
    def format_report_json(self, report: ChangeReport) -> str:
        """格式化为 JSON 报告"""
        data = {
            "timestamp": report.timestamp.isoformat(),
            "files": {
                "added": report.added_files,
                "modified": report.modified_files,
                "deleted": report.deleted_files,
            },
            "dependencies": {
                "added": report.new_dependencies,
                "removed": report.removed_dependencies,
            },
            "complexity_delta": report.complexity_delta,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def save_report(
        self,
        report: ChangeReport,
        output_path: str,
        format: str = "markdown",
    ) -> bool:
        """保存报告到文件"""
        try:
            if format == "markdown":
                content = self.format_report_markdown(report)
            elif format == "json":
                content = self.format_report_json(report)
            else:
                raise ValueError(f"不支持的格式: {format}")
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            self._logger.info(f"报告已保存: {output_path}")
            return True
            
        except Exception as e:
            self._logger.error(f"保存报告失败: {e}")
            return False
