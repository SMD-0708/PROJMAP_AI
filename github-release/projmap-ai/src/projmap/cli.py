"""ProjMap CLI 入口（完整版）

提供命令行接口用于生成和管理 .projmap 文件。
命令：
- init: 初始化项目，生成 .projmap 文件
- scan: 扫描项目并显示文件信息
- validate: 验证 .projmap 文件格式
- decision: 管理决策点
- status: 管理节点状态
- annotate: 使用 LLM 进行语义标注
- navigate: 项目导航（解决知识断层）
- state: 状态机管理（解决AI污染）
- trace: 决策追溯（解决决策遗忘）
- failure: 失败检索（解决踩坑复现）
- workspace: 工作区管理（解决迷失症）
- config: 配置管理
- incremental: 增量扫描（高性能）
- export: 导出为多种格式
- ci: CI/CD 集成
- collab: 协作功能
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from projmap import __version__
from projmap.models import ProjMap, NodeStatus, DecisionType
from projmap.scanner import ProjectScanner, scan_project
from projmap.generator import generate_projmap
from projmap.trust_level import extract_for_trust_level
from projmap.decision_manager import DecisionManager
from projmap.llm_service import create_llm_service, LLMService
from projmap.project_navigator import ProjectNavigator, generate_navigation_guide
from projmap.state_machine import PathStateMachine
from projmap.decision_tracer import DecisionTracer
from projmap.failure_retrieval import FailureRetrieval, search_similar_errors
from projmap.workspace_manager import WorkspaceManager, get_where_was_i
from projmap.settings import ProjMapSettings, get_settings, init_settings
from projmap.incremental_scanner import IncrementalScanner, scan_project_incremental
from projmap.exporters import get_exporter, list_exporters
from projmap.ci_integration import CIIntegrationManager
from projmap.collaboration import CollaborationManager, User, CommentTargetType
from projmap.research_domain import ResearchExperimentManager, AblationStudyManager
from projmap.fintech_domain import ComplianceAuditor, StrategyVersionManager, RiskManager, RiskLevel
from projmap.tech_tags import TechTagRecognizer, TechTagManager, AbandonmentManager, InferenceAnnotator


console = Console()


def load_projmap_with_settings(projmap_path: str) -> tuple[ProjMap, ProjMapSettings]:
    """加载 projmap 并初始化配置"""
    project_root = os.path.dirname(projmap_path) or "."
    init_settings(project_root)
    settings = get_settings()
    
    projmap = ProjMap.load(projmap_path)
    return projmap, settings


@click.group()
@click.version_option(version=__version__, prog_name="projmap")
def main():
    """ProjMap - 智能项目认知脉络系统核心引擎
    
    生成 .projmap 文件，记录项目结构、依赖关系和决策过程。
    """
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option(
    "-o", "--output",
    type=click.Path(),
    default=".projmap/project.projmap",
    help="输出文件路径",
)
@click.option(
    "-n", "--name",
    type=str,
    help="项目名称（默认使用目录名）",
)
@click.option(
    "-d", "--description",
    type=str,
    help="项目描述",
)
@click.option(
    "-t", "--trust-level",
    type=click.IntRange(1, 5),
    default=1,
    help="信任梯度档位：1=纯本地, 2=骨架, 3=注释, 4=参数, 5=全量",
)
@click.option(
    "--exclude",
    multiple=True,
    help="排除的文件/目录模式（可多次使用）",
)
@click.option(
    "--no-gitignore",
    is_flag=True,
    help="不使用 .gitignore 规则",
)
@click.option(
    "--llm",
    is_flag=True,
    help="启用 LLM 语义增强（需要设置 DEEPSEEK_API_KEY）",
)
@click.option(
    "--api-key",
    type=str,
    envvar="DEEPSEEK_API_KEY",
    help="DeepSeek API Key",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="以 JSON 格式输出结果",
)
def init(
    path: str,
    output: str,
    name: Optional[str],
    description: Optional[str],
    trust_level: int,
    exclude: tuple[str, ...],
    no_gitignore: bool,
    llm: bool,
    api_key: Optional[str],
    output_json: bool,
):
    """初始化项目，生成 .projmap 文件。
    
    PATH: 项目根目录路径（默认为当前目录）
    """
    root_path = os.path.abspath(path)
    
    trust_level_names = {
        1: "🔒 纯本地",
        2: "🛡️ 骨架",
        3: "⚖️ 注释",
        4: "📊 参数",
        5: "🌐 全量",
    }
    
    console.print(Panel(
        f"[bold blue]ProjMap[/bold blue] v{__version__}\n"
        f"正在扫描项目: [green]{root_path}[/green]\n"
        f"信任档位: [yellow]{trust_level_names.get(trust_level, str(trust_level))}[/yellow]",
        title="初始化项目",
    ))
    
    excludes = list(exclude) if exclude else None
    
    projmap = generate_projmap(
        root_path=root_path,
        project_name=name,
        description=description,
        trust_level=trust_level,
        excludes=excludes,
    )
    
    if llm and api_key:
        console.print("[dim]正在调用 LLM 进行语义增强...[/dim]")
        llm_service = create_llm_service(api_key)
        _annotate_with_llm(projmap, llm_service, trust_level)
    
    output_dir = os.path.dirname(output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    projmap.save(output)
    
    if output_json:
        console.print(projmap.to_json())
    else:
        _print_projmap_summary(projmap, output)


def _annotate_with_llm(projmap: ProjMap, llm_service: LLMService, trust_level: int):
    for node in projmap.nodes:
        if not node.file_path:
            continue
        
        file_info = {
            "file_path": node.file_path,
            "file_name": node.file_name,
            "language": node.language,
            "imports": node.imports,
            "exports": node.exports,
        }
        
        try:
            annotation = llm_service.annotate_code(file_info, trust_level)
            
            if annotation.get("function_tags"):
                node.function_tags = annotation["function_tags"]
            if annotation.get("task_name"):
                node.name = annotation["task_name"]
            if annotation.get("description"):
                node.description = annotation["description"]
            if annotation.get("is_entry"):
                node.is_entry = True
                node.status = NodeStatus.ACTIVE_MAIN
        except Exception as e:
            console.print(f"[yellow]警告: LLM 标注失败 ({node.file_path}): {e}[/yellow]")


@main.command()
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option(
    "--exclude",
    multiple=True,
    help="排除的文件/目录模式（可多次使用）",
)
@click.option(
    "--language",
    type=str,
    help="只显示指定语言的文件",
)
@click.option(
    "--tree",
    is_flag=True,
    help="以树形结构显示",
)
@click.option(
    "-t", "--trust-level",
    type=click.IntRange(1, 5),
    default=2,
    help="信任梯度档位（用于显示详细信息）",
)
def scan(
    path: str,
    exclude: tuple[str, ...],
    language: Optional[str],
    tree: bool,
    trust_level: int,
):
    """扫描项目目录并显示文件信息。
    
    PATH: 项目根目录路径（默认为当前目录）
    """
    root_path = os.path.abspath(path)
    
    excludes = list(exclude) if exclude else None
    
    result = scan_project(
        root_path=root_path,
        excludes=excludes,
    )
    
    if language:
        files = [f for f in result.files if f.language == language]
    else:
        files = result.files
    
    if tree:
        _print_file_tree(root_path, files)
    else:
        _print_file_table(files, result, trust_level)


@main.command()
@click.argument("file", type=click.Path(exists=True))
def validate(file: str):
    """验证 .projmap 文件格式。
    
    FILE: .projmap 文件路径
    """
    try:
        projmap = ProjMap.load(file)
        console.print(f"[green]✓[/green] 文件格式验证通过: {file}")
        console.print(f"  - 版本: {projmap.version}")
        console.print(f"  - 项目: {projmap.metadata.project_name if projmap.metadata else 'N/A'}")
        console.print(f"  - 节点数: {len(projmap.nodes)}")
        console.print(f"  - 边数: {len(projmap.edges)}")
        console.print(f"  - 决策点数: {len(projmap.decisions)}")
    except Exception as e:
        console.print(f"[red]✗[/red] 文件格式验证失败: {file}")
        console.print(f"  错误: {str(e)}")
        sys.exit(1)


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--format",
    type=click.Choice(["summary", "json", "nodes", "edges", "decisions"]),
    default="summary",
    help="输出格式",
)
def show(file: str, format: str):
    """显示 .projmap 文件内容。
    
    FILE: .projmap 文件路径
    """
    projmap = ProjMap.load(file)
    
    if format == "json":
        console.print(projmap.to_json())
    elif format == "nodes":
        _print_nodes_table(projmap)
    elif format == "edges":
        _print_edges_table(projmap)
    elif format == "decisions":
        _print_decisions_table(projmap)
    else:
        _print_projmap_summary(projmap, file)


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.argument("node_id", type=str)
@click.option(
    "--status",
    type=click.Choice(["active_main", "active_branch", "dormant", "archived"]),
    required=True,
    help="新状态",
)
def set_status(file: str, node_id: str, status: str):
    """更新节点状态。
    
    FILE: .projmap 文件路径
    NODE_ID: 节点ID
    """
    projmap = ProjMap.load(file)
    
    node = None
    for n in projmap.nodes:
        if n.id == node_id:
            node = n
            break
    
    if not node:
        console.print(f"[red]错误: 找不到节点 {node_id}[/red]")
        sys.exit(1)
    
    old_status = node.status
    node.status = NodeStatus(status)
    node.updated_at = datetime.now()
    
    if status == "active_main" and projmap.active_state:
        if projmap.active_state.active_main:
            old_main = None
            for n in projmap.nodes:
                if n.id == projmap.active_state.active_main:
                    old_main = n
                    break
            if old_main:
                old_main.status = NodeStatus.ACTIVE_BRANCH
        projmap.active_state.active_main = node_id
    elif status == "active_branch" and projmap.active_state:
        if node_id not in projmap.active_state.active_branches:
            projmap.active_state.active_branches.append(node_id)
    elif status == "dormant" and projmap.active_state:
        if node_id in projmap.active_state.active_branches:
            projmap.active_state.active_branches.remove(node_id)
    
    projmap.save(file)
    
    status_colors = {
        "active_main": "[green]● 主线[/green]",
        "active_branch": "[blue]● 分支[/blue]",
        "dormant": "[yellow]● 休眠[/yellow]",
        "archived": "[dim]● 归档[/dim]",
    }
    
    console.print(f"[green]✓[/green] 节点状态已更新")
    console.print(f"  节点: {node.name} ({node.file_path})")
    console.print(f"  状态: {status_colors.get(old_status.value, old_status.value)} → {status_colors.get(status, status)}")


@main.group()
def decision():
    """管理决策点。"""
    pass


@decision.command("add")
@click.argument("file", type=click.Path(exists=True))
@click.option("--node", required=True, help="节点ID")
@click.option("--type", "decision_type", 
    type=click.Choice(["parameter", "architecture", "algorithm", "abandoned", "milestone", "failure"]),
    required=True,
    help="决策类型")
@click.option("--content", required=True, help="决策内容")
@click.option("--reason", help="决策原因")
@click.option("--param", multiple=True, help="参数（格式: key=value）")
def add_decision(
    file: str,
    node: str,
    decision_type: str,
    content: str,
    reason: Optional[str],
    param: tuple[str, ...],
):
    """添加决策点。"""
    projmap = ProjMap.load(file)
    
    node_exists = any(n.id == node for n in projmap.nodes)
    if not node_exists:
        console.print(f"[red]错误: 找不到节点 {node}[/red]")
        sys.exit(1)
    
    parameters = {}
    for p in param:
        if "=" in p:
            key, value = p.split("=", 1)
            parameters[key.strip()] = value.strip()
    
    manager = DecisionManager(projmap)
    decision = manager.add_decision(
        node_id=node,
        decision_type=decision_type,
        content=content,
        reason=reason,
        parameters=parameters if parameters else None,
    )
    
    projmap.save(file)
    
    console.print(f"[green]✓[/green] 决策点已添加")
    console.print(f"  ID: {decision.id}")
    console.print(f"  节点: {node}")
    console.print(f"  类型: {decision_type}")
    console.print(f"  内容: {content}")


@decision.command("list")
@click.argument("file", type=click.Path(exists=True))
@click.option("--node", help="筛选节点ID")
@click.option("--type", "decision_type", help="筛选决策类型")
def list_decisions(file: str, node: Optional[str], decision_type: Optional[str]):
    """列出决策点。"""
    projmap = ProjMap.load(file)
    manager = DecisionManager(projmap)
    
    if node:
        decisions = manager.get_decisions_by_node(node)
    elif decision_type:
        decisions = manager.get_decisions_by_type(decision_type)
    else:
        decisions = projmap.decisions
    
    _print_decisions_list(decisions, projmap)


@decision.command("search")
@click.argument("file", type=click.Path(exists=True))
@click.argument("keyword", type=str)
def search_decisions(file: str, keyword: str):
    """搜索决策点。"""
    projmap = ProjMap.load(file)
    manager = DecisionManager(projmap)
    
    results = manager.search_decisions(keyword)
    
    if not results:
        console.print(f"[yellow]未找到包含 '{keyword}' 的决策点[/yellow]")
    else:
        _print_decisions_list(results, projmap)


@decision.command("report")
@click.argument("file", type=click.Path(exists=True))
def decision_report(file: str):
    """生成决策报告。"""
    projmap = ProjMap.load(file)
    manager = DecisionManager(projmap)
    
    report = manager.export_decisions_report()
    
    console.print(Panel(
        f"总决策数: {report['total_decisions']}\n"
        + "\n".join(f"  {k}: {v}" for k, v in report['by_type'].items()),
        title="决策统计",
    ))
    
    if report['recent']:
        console.print("\n[bold]最近决策:[/bold]")
        for d in report['recent'][:5]:
            console.print(f"  • [{d['type']}] {d['node']}: {d['content'][:50]}...")


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--api-key",
    type=str,
    envvar="DEEPSEEK_API_KEY",
    help="DeepSeek API Key",
)
@click.option(
    "-t", "--trust-level",
    type=click.IntRange(1, 5),
    default=2,
    help="信任梯度档位",
)
@click.option(
    "--node",
    help="只标注指定节点",
)
def annotate(
    file: str,
    api_key: Optional[str],
    trust_level: int,
    node: Optional[str],
):
    """使用 LLM 进行语义标注。"""
    if not api_key:
        console.print("[red]错误: 需要设置 DEEPSEEK_API_KEY 环境变量或使用 --api-key 参数[/red]")
        sys.exit(1)
    
    projmap = ProjMap.load(file)
    llm_service = create_llm_service(api_key)
    
    nodes_to_annotate = projmap.nodes
    if node:
        nodes_to_annotate = [n for n in projmap.nodes if n.id == node]
    
    console.print(f"[dim]正在标注 {len(nodes_to_annotate)} 个节点...[/dim]")
    
    _annotate_with_llm(projmap, llm_service, trust_level)
    
    projmap.save(file)
    console.print(f"[green]✓[/green] 标注完成，已保存到 {file}")


def _print_projmap_summary(projmap: ProjMap, output_path: str):
    console.print(f"\n[green]✓[/green] 已生成: [bold]{output_path}[/bold]\n")
    
    table = Table(title="项目概览")
    table.add_column("属性", style="cyan")
    table.add_column("值", style="green")
    
    if projmap.metadata:
        table.add_row("项目名称", projmap.metadata.project_name)
        table.add_row("项目路径", projmap.metadata.project_root)
        if projmap.metadata.description:
            table.add_row("描述", projmap.metadata.description)
        
        trust_names = {1: "🔒 纯本地", 2: "🛡️ 骨架", 3: "⚖️ 注释", 4: "📊 参数", 5: "🌐 全量"}
        table.add_row("信任档位", trust_names.get(projmap.metadata.trust_level, str(projmap.metadata.trust_level)))
    
    table.add_row("节点数量", str(len(projmap.nodes)))
    table.add_row("依赖关系", str(len(projmap.edges)))
    table.add_row("决策记录", str(len(projmap.decisions)))
    
    console.print(table)
    
    if projmap.active_state and projmap.active_state.active_main:
        main_node = None
        for n in projmap.nodes:
            if n.id == projmap.active_state.active_main:
                main_node = n
                break
        
        if main_node:
            console.print(f"\n[bold]主线入口:[/bold] {main_node.name} ({main_node.file_path})")


def _print_file_table(files, result, trust_level: int):
    table = Table(title=f"扫描结果 ({len(files)} 个文件)")
    table.add_column("文件名", style="cyan")
    table.add_column("路径", style="dim")
    table.add_column("语言", style="green")
    table.add_column("大小", justify="right")
    
    if trust_level >= 2:
        table.add_column("导入数", justify="right")
    
    for f in files[:50]:
        size_str = _format_size(f.size)
        row = [
            f.name,
            f.relative_path,
            f.language or "-",
            size_str,
        ]
        
        if trust_level >= 2:
            data = extract_for_trust_level(f.path, trust_level)
            row.append(str(len(data.get("imports", []))))
        
        table.add_row(*row)
    
    if len(files) > 50:
        table.add_row("...", f"还有 {len(files) - 50} 个文件", "", "")
    
    console.print(table)
    console.print(f"\n总计: {result.total_files} 个文件, {result.total_directories} 个目录")


def _print_file_tree(root_path: str, files):
    tree = Tree(f"[bold blue]{os.path.basename(root_path)}[/bold blue]")
    
    dir_nodes = {}
    
    for f in sorted(files, key=lambda x: x.relative_path):
        parts = f.relative_path.split("/")
        
        current = tree
        path_so_far = ""
        
        for i, part in enumerate(parts[:-1]):
            path_so_far = f"{path_so_far}/{part}" if path_so_far else part
            
            if path_so_far not in dir_nodes:
                dir_nodes[path_so_far] = current.add(f"[bold yellow]{part}[/bold yellow]/")
            
            current = dir_nodes[path_so_far]
        
        file_name = parts[-1]
        lang_str = f" [dim]({f.language})[/dim]" if f.language else ""
        current.add(f"[green]{file_name}[/green]{lang_str}")
    
    console.print(tree)


def _print_nodes_table(projmap: ProjMap):
    table = Table(title="节点列表")
    table.add_column("ID", style="dim")
    table.add_column("名称", style="cyan")
    table.add_column("路径", style="green")
    table.add_column("状态", style="yellow")
    table.add_column("语言", style="blue")
    table.add_column("功能标签", style="magenta")
    
    status_colors = {
        "active_main": "[green]●[/green] 主线",
        "active_branch": "[blue]●[/blue] 分支",
        "dormant": "[yellow]●[/yellow] 休眠",
        "archived": "[dim]●[/dim] 归档",
    }
    
    for node in projmap.nodes:
        status_str = status_colors.get(node.status.value, node.status.value)
        tags_str = ", ".join(node.function_tags[:3]) if node.function_tags else "-"
        table.add_row(
            node.id[:16] + "...",
            node.name,
            node.file_path,
            status_str,
            node.language or "-",
            tags_str,
        )
    
    console.print(table)


def _print_edges_table(projmap: ProjMap):
    table = Table(title="依赖关系")
    table.add_column("源节点", style="cyan")
    table.add_column("关系", style="yellow")
    table.add_column("目标节点", style="green")
    
    node_map = {n.id: n for n in projmap.nodes}
    
    for edge in projmap.edges:
        source = node_map.get(edge.source)
        target = node_map.get(edge.target)
        
        source_name = source.name if source else edge.source[:12]
        target_name = target.name if target else edge.target[:12]
        
        table.add_row(
            source_name,
            f"[dim]{edge.type.value}[/dim] →",
            target_name,
        )
    
    console.print(table)


def _print_decisions_table(projmap: ProjMap):
    manager = DecisionManager(projmap)
    _print_decisions_list(projmap.decisions, projmap)


def _print_decisions_list(decisions, projmap: ProjMap):
    if not decisions:
        console.print("[yellow]无决策记录[/yellow]")
        return
    
    table = Table(title=f"决策点列表 ({len(decisions)} 条)")
    table.add_column("ID", style="dim")
    table.add_column("节点", style="cyan")
    table.add_column("类型", style="yellow")
    table.add_column("内容", style="green")
    table.add_column("时间", style="blue")
    
    node_map = {n.id: n.name for n in projmap.nodes}
    
    type_icons = {
        "parameter": "📊",
        "architecture": "🏗️",
        "algorithm": "⚙️",
        "abandoned": "❌",
        "milestone": "🎯",
        "failure": "⚠️",
    }
    
    for d in sorted(decisions, key=lambda x: x.timestamp, reverse=True):
        node_name = node_map.get(d.node_id, d.node_id[:10])
        type_str = f"{type_icons.get(d.type.value, '')} {d.type.value}"
        content_str = d.content[:40] + "..." if len(d.content) > 40 else d.content
        time_str = d.timestamp.strftime("%m-%d %H:%M")
        
        table.add_row(
            d.id[:14] + "...",
            node_name,
            type_str,
            content_str,
            time_str,
        )
    
    console.print(table)


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@main.group()
def hook():
    """管理 Git Hook 集成。"""
    pass


@hook.command("install")
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option(
    "--type", "hook_type",
    type=click.Choice(["post-commit"]),
    default="post-commit",
    help="Hook 类型",
)
def install_hook(path: str, hook_type: str):
    """安装 Git Hook。"""
    from projmap.git_hook import install_git_hook, check_hook_installed
    
    if check_hook_installed(path, hook_type):
        console.print(f"[yellow]Git Hook ({hook_type}) 已安装[/yellow]")
        return
    
    if install_git_hook(path, hook_type):
        console.print(f"[green]✓[/green] Git Hook ({hook_type}) 安装成功")
        console.print(f"  每次 git commit 后将自动更新 .projmap 文件")
    else:
        console.print(f"[red]✗[/red] Git Hook 安装失败（请确认是否在 Git 仓库中）")


@hook.command("uninstall")
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option(
    "--type", "hook_type",
    type=click.Choice(["post-commit"]),
    default="post-commit",
    help="Hook 类型",
)
def uninstall_hook(path: str, hook_type: str):
    """卸载 Git Hook。"""
    from projmap.git_hook import uninstall_git_hook
    
    if uninstall_git_hook(path, hook_type):
        console.print(f"[green]✓[/green] Git Hook ({hook_type}) 已卸载")
    else:
        console.print(f"[red]✗[/red] Git Hook 卸载失败")


@hook.command("status")
@click.argument("path", type=click.Path(exists=True), default=".")
def hook_status(path: str):
    """检查 Git Hook 状态。"""
    from projmap.git_hook import check_hook_installed, GitHookManager
    
    manager = GitHookManager(path)
    
    if not manager.is_git_repo():
        console.print("[red]当前目录不是 Git 仓库[/red]")
        return
    
    console.print(f"[bold]Git Hook 状态:[/bold]")
    
    hooks = ["post-commit"]
    for hook_type in hooks:
        installed = check_hook_installed(path, hook_type)
        status = "[green]✓ 已安装[/green]" if installed else "[dim]✗ 未安装[/dim]"
        console.print(f"  {hook_type}: {status}")


@main.group()
def navigate():
    """项目导航（解决知识断层）- 生成阅读路径推荐"""
    pass


@navigate.command("quick-start")
@click.argument("file", type=click.Path(exists=True))
def navigate_quick_start(file: str):
    """显示快速入门路径"""
    projmap = ProjMap.load(file)
    navigator = ProjectNavigator(projmap)
    path = navigator.get_quick_start_path()
    
    console.print(Panel(
        f"[bold]{path.name}[/bold]\n"
        f"{path.description}\n\n"
        f"目标读者: {path.target_audience}\n"
        f"预计时间: {path.estimated_time} 分钟\n"
        f"节点数: {path.node_count}",
        title="项目导航",
    ))
    
    table = Table(title="阅读顺序")
    table.add_column("#", style="dim", justify="right")
    table.add_column("文件", style="cyan")
    table.add_column("路径", style="green")
    table.add_column("状态", style="yellow")
    table.add_column("重要度", justify="right")
    
    status_icons = {
        "active_main": "🟢",
        "active_branch": "🔵",
        "dormant": "🟡",
        "archived": "⚪",
    }
    
    for rn in path.nodes:
        status = status_icons.get(rn.node.status.value, "⚪")
        table.add_row(
            str(rn.reading_order),
            rn.node.name,
            rn.node.file_path,
            f"{status} {rn.node.status.value}",
            f"{rn.importance_score:.1f}",
        )
    
    console.print(table)


@navigate.command("architecture")
@click.argument("file", type=click.Path(exists=True))
def navigate_architecture(file: str):
    """显示架构概览路径"""
    projmap = ProjMap.load(file)
    navigator = ProjectNavigator(projmap)
    path = navigator.get_architecture_overview()
    
    console.print(Panel(
        f"[bold]{path.name}[/bold]\n{path.description}",
        title="架构导航",
    ))
    
    for rn in path.nodes:
        console.print(f"  {rn.reading_order}. {rn.node.name} ({rn.node.type.value})")


@navigate.command("guide")
@click.argument("file", type=click.Path(exists=True))
@click.option("-o", "--output", help="输出文件路径")
def navigate_guide(file: str, output: Optional[str]):
    """生成导航指南文档"""
    projmap = ProjMap.load(file)
    
    if not output:
        output = os.path.join(
            os.path.dirname(file) if os.path.dirname(file) else ".",
            "NAVIGATION_GUIDE.md"
        )
    
    content = generate_navigation_guide(projmap, output)
    console.print(f"[green]✓[/green] 导航指南已生成: {output}")


@main.group()
def state():
    """状态机管理（解决AI污染）- 管理节点状态转换"""
    pass


@state.command("show")
@click.argument("file", type=click.Path(exists=True))
def state_show(file: str):
    """显示当前状态机状态"""
    projmap = ProjMap.load(file)
    machine = PathStateMachine(projmap)
    report = machine.generate_state_report()
    
    console.print(Panel(
        f"总计: {report['summary']['total_nodes']} 个节点\n"
        f"主线: {report['summary']['active_main']} | "
        f"分支: {report['summary']['active_branches']} | "
        f"休眠: {report['summary']['dormant']} | "
        f"归档: {report['summary']['archived']}",
        title="状态机概览",
    ))
    
    if report["active_main"]["id"]:
        console.print(f"\n[bold green]当前主线:[/bold green] {report['active_main']['name']}")
        console.print(f"  路径: {report['active_main']['file_path']}")
    
    if report["active_branches"]:
        console.print(f"\n[bold blue]活跃分支 ({len(report['active_branches'])}):[/bold blue]")
        for branch in report["active_branches"][:5]:
            console.print(f"  • {branch['name']}")


@state.command("transition")
@click.argument("file", type=click.Path(exists=True))
@click.option("--node", required=True, help="节点ID")
@click.option("--to", "to_status", required=True,
              type=click.Choice(["active_main", "active_branch", "dormant", "archived"]),
              help="目标状态")
@click.option("--reason", help="转换原因")
def state_transition(file: str, node: str, to_status: str, reason: Optional[str]):
    """执行状态转换"""
    projmap = ProjMap.load(file)
    machine = PathStateMachine(projmap)
    
    to_status_enum = NodeStatus(to_status)
    success, message = machine.transition(node, to_status_enum, reason or "")
    
    if success:
        projmap.save(file)
        console.print(f"[green]✓[/green] {message}")
    else:
        console.print(f"[red]✗[/red] {message}")


@state.command("context")
@click.argument("file", type=click.Path(exists=True))
@click.option("--include-dormant", is_flag=True, help="包含休眠节点")
def state_context(file: str, include_dormant: bool):
    """获取用于LLM的上下文（解决AI污染）"""
    projmap = ProjMap.load(file)
    machine = PathStateMachine(projmap)
    context = machine.get_context_for_llm(include_dormant=include_dormant)
    
    console.print("[bold]LLM 上下文（已过滤废线）:[/bold]")
    
    if context["active_main"]:
        console.print(f"\n[green]主线:[/green] {context['active_main']['name']}")
    
    if context["active_branches"]:
        console.print(f"\n[blue]分支 ({len(context['active_branches'])}):[/blue]")
        for branch in context["active_branches"][:5]:
            console.print(f"  • {branch['name']}")
    
    if include_dormant and context["dormant_nodes"]:
        console.print(f"\n[yellow]休眠 ({len(context['dormant_nodes'])}):[/yellow]")


@main.group()
def trace():
    """决策追溯（解决决策遗忘）- 追踪决策历史和参数变更"""
    pass


@trace.command("parameter")
@click.argument("file", type=click.Path(exists=True))
@click.argument("param_name", type=str)
@click.option("--node", help="指定节点")
def trace_parameter(file: str, param_name: str, node: Optional[str]):
    """追溯参数变更历史"""
    projmap = ProjMap.load(file)
    tracer = DecisionTracer(projmap)
    
    changes = tracer.trace_parameter(param_name, node)
    
    if not changes:
        console.print(f"[yellow]未找到参数 '{param_name}' 的变更记录[/yellow]")
        return
    
    table = Table(title=f"参数历史: {param_name}")
    table.add_column("时间", style="dim")
    table.add_column("旧值", style="red")
    table.add_column("新值", style="green")
    table.add_column("原因", style="cyan")
    
    for change in changes:
        old_val = str(change.old_value) if change.old_value is not None else "-"
        new_val = str(change.new_value)
        time_str = change.timestamp.strftime("%m-%d %H:%M")
        
        table.add_row(time_str, old_val, new_val, change.reason or "-")
    
    console.print(table)
    
    # 显示当前值
    current, last_decision = tracer.get_parameter_current_value(param_name, node)
    if current is not None:
        console.print(f"\n[bold]当前值:[/bold] {current}")


@trace.command("alternatives")
@click.argument("file", type=click.Path(exists=True))
@click.argument("decision_id", type=str)
def trace_alternatives(file: str, decision_id: str):
    """查看决策的方案取舍"""
    projmap = ProjMap.load(file)
    tracer = DecisionTracer(projmap)
    
    analysis = tracer.get_alternatives_analysis(decision_id)
    
    if not analysis:
        console.print(f"[red]未找到决策 {decision_id}[/red]")
        return
    
    console.print(Panel(
        f"[bold]选中方案:[/bold] {analysis['selected']}\n"
        f"[bold]原因:[/bold] {analysis['reason'] or '未记录'}",
        title="方案取舍分析",
    ))
    
    if analysis["alternatives"]:
        console.print("\n[bold]被放弃的备选方案:[/bold]")
        for alt in analysis["alternatives"]:
            console.print(f"  ❌ {alt['name']}")
            if alt["reason_rejected"]:
                console.print(f"     原因: {alt['reason_rejected']}")


@trace.command("abandoned")
@click.argument("file", type=click.Path(exists=True))
def trace_abandoned(file: str):
    """查看所有被放弃的方案"""
    projmap = ProjMap.load(file)
    tracer = DecisionTracer(projmap)
    
    abandoned = tracer.find_abandoned_approaches()
    
    if not abandoned:
        console.print("[yellow]没有被放弃的方案记录[/yellow]")
        return
    
    table = Table(title=f"被放弃的方案 ({len(abandoned)})")
    table.add_column("时间", style="dim")
    table.add_column("节点", style="cyan")
    table.add_column("方案", style="yellow")
    table.add_column("放弃原因", style="red")
    
    for item in abandoned[:20]:
        time_str = item["timestamp"][:10]
        table.add_row(
            time_str,
            item["node_name"],
            item["content"][:30] + "..." if len(item["content"]) > 30 else item["content"],
            item["reason"][:40] + "..." if item["reason"] and len(item["reason"]) > 40 else (item["reason"] or "-"),
        )
    
    console.print(table)


@main.group()
def failure():
    """失败检索（解决踩坑复现）- 记录和检索失败经验"""
    pass


@failure.command("search")
@click.argument("file", type=click.Path(exists=True))
@click.argument("query", type=str)
@click.option("--error-type", help="错误类型过滤")
def failure_search(file: str, query: str, error_type: Optional[str]):
    """搜索失败记录"""
    projmap = ProjMap.load(file)
    retriever = FailureRetrieval(projmap)
    
    results = retriever.search_failures(query, error_type=error_type)
    
    if not results:
        console.print(f"[yellow]未找到匹配 '{query}' 的失败记录[/yellow]")
        return
    
    table = Table(title=f"失败记录搜索结果 ({len(results)})")
    table.add_column("类型", style="red")
    table.add_column("错误信息", style="yellow")
    table.add_column("解决方案", style="green")
    table.add_column("时间", style="dim")
    
    for pattern in results[:10]:
        time_str = pattern.timestamp.strftime("%m-%d")
        error_msg = pattern.error_message[:40] + "..." if len(pattern.error_message) > 40 else pattern.error_message
        solution = pattern.solution[:40] + "..." if len(pattern.solution) > 40 else pattern.solution
        
        table.add_row(pattern.error_type, error_msg, solution, time_str)
    
    console.print(table)


@failure.command("similar")
@click.argument("file", type=click.Path(exists=True))
@click.argument("error_message", type=str)
def failure_similar(file: str, error_message: str):
    """查找相似错误"""
    projmap = ProjMap.load(file)
    similar = search_similar_errors(projmap, error_message)
    
    if not similar:
        console.print("[yellow]未找到相似错误记录[/yellow]")
        return
    
    console.print("[bold]相似错误记录:[/bold]\n")
    
    for item in similar:
        similarity = item["similarity"]
        color = "green" if similarity > 0.7 else "yellow" if similarity > 0.4 else "dim"
        
        console.print(f"[bold]相似度: [{color}]{similarity}[/{color}][/bold]")
        console.print(f"  类型: {item['error_type']}")
        console.print(f"  错误: {item['error_message'][:80]}...")
        console.print(f"  解决方案: {item['solution'][:80]}...")
        console.print()


@failure.command("stats")
@click.argument("file", type=click.Path(exists=True))
def failure_stats(file: str):
    """显示失败统计"""
    projmap = ProjMap.load(file)
    retriever = FailureRetrieval(projmap)
    stats = retriever.get_failure_statistics()
    
    console.print(Panel(
        f"总失败记录: {stats['total_failures']}\n"
        f"最常见错误: {stats.get('most_common_error', 'N/A')}",
        title="失败统计",
    ))
    
    if stats["by_error_type"]:
        console.print("\n[bold]错误类型分布:[/bold]")
        for error_type, count in sorted(stats["by_error_type"].items(), key=lambda x: x[1], reverse=True)[:5]:
            console.print(f"  {error_type}: {count}")


@main.group()
def workspace():
    """工作区管理（解决迷失症）- 保存和恢复工作进度"""
    pass


@workspace.command("start")
@click.argument("file", type=click.Path(exists=True))
@click.option("--notes", help="会话上下文笔记")
def workspace_start(file: str, notes: Optional[str]):
    """开始新工作会话"""
    projmap = ProjMap.load(file)
    manager = WorkspaceManager(projmap)
    
    session = manager.start_session(notes or "")
    console.print(f"[green]✓[/green] 工作会话已启动: {session.session_id}")
    
    if notes:
        console.print(f"  笔记: {notes}")


@workspace.command("where")
@click.argument("file", type=click.Path(exists=True))
def workspace_where(file: str):
    """我在哪里？显示当前工作上下文"""
    projmap = ProjMap.load(file)
    context = get_where_was_i(projmap)
    
    if "error" in context:
        console.print(f"[yellow]{context['error']}[/yellow]")
        return
    
    console.print(Panel(
        f"会话: {context['session_id']}\n"
        f"持续时间: {context['duration_hours']:.1f} 小时\n"
        f"待办任务: {context['pending_tasks_count']}",
        title="当前工作上下文",
    ))
    
    if context["active_nodes"]:
        console.print("\n[bold]当前活跃节点:[/bold]")
        for node in context["active_nodes"][:5]:
            status_icon = {"active_main": "🟢", "active_branch": "🔵"}.get(node["status"], "⚪")
            console.print(f"  {status_icon} {node['name']}")
    
    if context["pending_tasks"]:
        console.print("\n[bold]待办任务:[/bold]")
        for task in context["pending_tasks"][:5]:
            priority_color = {"high": "red", "medium": "yellow", "low": "dim"}.get(task.get("priority", "medium"), "white")
            console.print(f"  [{priority_color}]{task['priority']}[/{priority_color}] {task['description']}")


@workspace.command("checkpoint")
@click.argument("file", type=click.Path(exists=True))
@click.option("--description", required=True, help="检查点描述")
def workspace_checkpoint(file: str, description: str):
    """创建进度检查点"""
    projmap = ProjMap.load(file)
    manager = WorkspaceManager(projmap)
    
    checkpoint = manager.create_checkpoint(description)
    console.print(f"[green]✓[/green] 检查点已创建: {checkpoint.checkpoint_id}")
    console.print(f"  描述: {description}")


@workspace.command("task")
@click.argument("file", type=click.Path(exists=True))
@click.argument("description", type=str)
@click.option("--priority", default="medium", type=click.Choice(["high", "medium", "low"]))
@click.option("--node", help="关联节点")
def workspace_task(file: str, description: str, priority: str, node: Optional[str]):
    """添加任务"""
    projmap = ProjMap.load(file)
    manager = WorkspaceManager(projmap)
    
    manager.add_task(description, priority, node)
    console.print(f"[green]✓[/green] 任务已添加: {description}")


@main.group()
def config():
    """配置管理 - 管理 ProjMap 配置"""
    pass


@config.command("init")
@click.option("-o", "--output", default=".projmaprc.json", help="配置文件路径")
@click.option("--global", "is_global", is_flag=True, help="创建全局配置（在用户主目录）")
def config_init(output: str, is_global: bool):
    """初始化配置文件"""
    settings = ProjMapSettings()
    
    if is_global:
        output = os.path.join(Path.home(), ".projmaprc.json")
    
    settings.create_default_config_file(output)
    console.print(f"[green]✓[/green] 配置文件已创建: {output}")


@config.command("show")
@click.option("-f", "--file", help="指定配置文件路径")
def config_show(file: Optional[str]):
    """显示当前配置"""
    if file and os.path.exists(file):
        settings = ProjMapSettings.from_file(file)
    else:
        settings = get_settings()
    
    console.print(Panel("[bold]当前配置[/bold]", title="ProjMap 配置"))
    
    # 导航器配置
    console.print("\n[bold cyan]导航器配置:[/bold cyan]")
    console.print(f"  缓存启用: {settings.navigator.enable_cache}")
    console.print(f"  缓存TTL: {settings.navigator.cache_ttl} 秒")
    console.print(f"  最大快速入门节点: {settings.navigator.max_quick_start_nodes}")
    
    # 状态机配置
    console.print("\n[bold cyan]状态机配置:[/bold cyan]")
    console.print(f"  自动归档: {settings.state_machine.auto_archive_enabled}")
    console.print(f"  归档天数: {settings.state_machine.auto_archive_days}")
    console.print(f"  历史记录: {settings.state_machine.history_enabled}")
    
    # 异步配置
    console.print("\n[bold cyan]异步配置:[/bold cyan]")
    console.print(f"  异步启用: {settings.async_config.enabled}")
    console.print(f"  最大工作线程: {settings.async_config.max_workers}")
    console.print(f"  最大并发数: {settings.async_config.max_concurrency}")
    
    # 日志配置
    console.print("\n[bold cyan]日志配置:[/bold cyan]")
    console.print(f"  日志级别: {settings.logging.level}")
    console.print(f"  控制台输出: {settings.logging.console}")


@config.command("set")
@click.argument("key", type=str)
@click.argument("value", type=str)
@click.option("-f", "--file", default=".projmaprc.json", help="配置文件路径")
def config_set(key: str, value: str, file: str):
    """设置配置项
    
    示例:
        projmap config set navigator.enable_cache false
        projmap config set logging.level DEBUG
    """
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    
    # 解析 key 路径
    keys = key.split(".")
    current = data
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]
    
    # 尝试转换 value 类型
    final_value = value
    if value.lower() in ("true", "false"):
        final_value = value.lower() == "true"
    elif value.isdigit():
        final_value = int(value)
    elif value.replace(".", "").isdigit():
        final_value = float(value)
    
    current[keys[-1]] = final_value
    
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    console.print(f"[green]✓[/green] 配置已更新: {key} = {final_value}")


@config.command("env")
def config_env():
    """显示环境变量配置"""
    env_vars = {
        "PROJMAP_CONFIG": os.getenv("PROJMAP_CONFIG", "未设置"),
        "PROJMAP_LOG_LEVEL": os.getenv("PROJMAP_LOG_LEVEL", "未设置"),
        "PROJMAP_ASYNC_ENABLED": os.getenv("PROJMAP_ASYNC_ENABLED", "未设置"),
        "PROJMAP_MAX_WORKERS": os.getenv("PROJMAP_MAX_WORKERS", "未设置"),
        "PROJMAP_CACHE_ENABLED": os.getenv("PROJMAP_CACHE_ENABLED", "未设置"),
    }
    
    console.print(Panel("[bold]环境变量配置[/bold]", title="ProjMap 环境"))
    for var, val in env_vars.items():
        status = "[dim]未设置[/dim]" if val == "未设置" else f"[green]{val}[/green]"
        console.print(f"  {var}: {status}")


# ========== 增量扫描命令 ==========

@main.command()
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option(
    "-o", "--output",
    type=click.Path(),
    default=".projmap/project.projmap",
    help="输出文件路径",
)
@click.option(
    "--full",
    is_flag=True,
    help="强制全量扫描（忽略缓存）",
)
@click.option(
    "--stats",
    is_flag=True,
    help="显示扫描统计",
)
def incremental(path: str, output: str, full: bool, stats: bool):
    """增量扫描项目（高性能）
    
    只扫描变更文件，大型项目性能提升 10x+
    """
    root_path = os.path.abspath(path)
    
    console.print(Panel(
        f"[bold blue]ProjMap 增量扫描[/bold blue]\n"
        f"项目路径: [green]{root_path}[/green]",
        title="增量扫描",
    ))
    
    scanner = IncrementalScanner(root_path)
    
    if full:
        scanner.invalidate_cache()
        console.print("[yellow]缓存已清除，执行全量扫描[/yellow]")
    
    # 加载现有 projmap（如果存在）
    existing_projmap = None
    if os.path.exists(output):
        try:
            existing_projmap = ProjMap.load(output)
            console.print(f"[dim]加载现有 projmap: {output}[/dim]")
        except Exception:
            pass
    
    # 执行增量扫描
    projmap, changes = scanner.scan_incremental(existing_projmap)
    
    # 保存结果
    output_dir = os.path.dirname(output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    projmap.save(output)
    
    # 显示结果
    console.print(f"\n[green]✓[/green] 扫描完成，已保存到: {output}")
    
    if changes.has_changes:
        table = Table(title="变更摘要")
        table.add_column("类型", style="cyan")
        table.add_column("数量", style="green", justify="right")
        table.add_column("文件示例", style="dim")
        
        if changes.added:
            table.add_row("新增", str(len(changes.added)), changes.added[0][:50] + "...")
        if changes.modified:
            table.add_row("修改", str(len(changes.modified)), changes.modified[0][:50] + "...")
        if changes.deleted:
            table.add_row("删除", str(len(changes.deleted)), changes.deleted[0][:50] + "...")
        
        console.print(table)
    else:
        console.print("[dim]没有检测到变更[/dim]")
    
    if stats:
        scan_stats = scanner.get_scan_statistics()
        console.print(f"\n[bold]扫描统计:[/bold]")
        console.print(f"  缓存文件数: {scan_stats['cached_files']}")
        console.print(f"  缓存位置: {scan_stats['cache_file']}")


# ========== 导出命令 ==========

@main.group()
def export():
    """导出为多种格式（Mermaid/PlantUML/DOT）"""
    pass


@export.command("list")
def export_list():
    """列出可用导出格式"""
    exporters = list_exporters()
    
    table = Table(title="可用导出格式")
    table.add_column("名称", style="cyan")
    table.add_column("格式", style="green")
    table.add_column("扩展名", style="yellow")
    
    for exp in exporters:
        table.add_row(exp["name"], exp["format"], exp["extension"])
    
    console.print(table)


@export.command("run")
@click.argument("file", type=click.Path(exists=True))
@click.option("--format", required=True, help="导出格式 (mermaid/plantuml/dot/json)")
@click.option("-o", "--output", help="输出文件路径")
def export_run(file: str, format: str, output: Optional[str]):
    """执行导出"""
    exporter = get_exporter(format)
    
    if not exporter:
        console.print(f"[red]错误: 不支持的导出格式 '{format}'[/red]")
        console.print("使用 'projmap export list' 查看可用格式")
        sys.exit(1)
    
    projmap = ProjMap.load(file)
    
    if not output:
        base_name = os.path.splitext(file)[0]
        output = f"{base_name}{exporter.file_extension}"
    
    if exporter.export_to_file(projmap, output):
        console.print(f"[green]✓[/green] 导出成功: {output}")
        console.print(f"  格式: {exporter.format_name}")
        
        # 显示预览
        content = exporter.export(projmap)
        if len(content) < 500:
            console.print(f"\n[dim]预览:[/dim]")
            console.print(content[:500])
    else:
        console.print(f"[red]✗[/red] 导出失败")


# ========== CI/CD 命令 ==========

@main.group()
def ci():
    """CI/CD 集成（GitHub Actions）"""
    pass


@ci.command("setup")
@click.argument("path", type=click.Path(exists=True), default=".")
def ci_setup(path: str):
    """设置 GitHub Actions 集成"""
    manager = CIIntegrationManager(path)
    
    if manager.setup_github_actions():
        console.print("[green]✓[/green] GitHub Actions 工作流已创建")
        console.print("  工作流文件: .github/workflows/projmap.yml")
        console.print("\n[dim]功能:[/dim]")
        console.print("  • 每次 push 自动更新 .projmap")
        console.print("  • PR 评论显示变更报告")
        console.print("  • 支持手动触发")
    else:
        console.print("[red]✗[/red] 设置失败")


@ci.command("report")
@click.argument("file", type=click.Path(exists=True))
@click.option("--format", type=click.Choice(["markdown", "json"]), default="markdown")
@click.option("-o", "--output", help="输出文件路径")
def ci_report(file: str, format: str, output: Optional[str]):
    """生成变更报告"""
    projmap = ProjMap.load(file)
    manager = CIIntegrationManager()
    
    # 模拟变更数据（实际应从扫描结果获取）
    from projmap.incremental_scanner import IncrementalScanResult
    changes = IncrementalScanResult()
    
    report = manager.generate_change_report(changes, projmap, projmap)
    
    if not output:
        output = "PROJMAP_CHANGES.md" if format == "markdown" else "PROJMAP_CHANGES.json"
    
    if manager.save_report(report, output, format):
        console.print(f"[green]✓[/green] 报告已生成: {output}")
    else:
        console.print("[red]✗[/red] 报告生成失败")


# ========== 协作命令 ==========

@main.group()
def collab():
    """协作功能（多用户评审、评论）"""
    pass


@collab.command("user")
@click.argument("file", type=click.Path(exists=True))
@click.option("--name", required=True, help="用户名")
@click.option("--email", required=True, help="邮箱")
@click.option("--role", default="member", type=click.Choice(["admin", "member", "viewer"]))
def collab_user(file: str, name: str, email: str, role: str):
    """设置当前用户"""
    projmap = ProjMap.load(file)
    manager = CollaborationManager(projmap)
    
    user = User(
        user_id=str(hash(email))[:8],
        name=name,
        email=email,
        role=role,
    )
    
    manager.set_current_user(user)
    console.print(f"[green]✓[/green] 当前用户已设置: {name} ({role})")


@collab.command("comment")
@click.argument("file", type=click.Path(exists=True))
@click.option("--target", required=True, help="目标ID（节点ID或决策ID）")
@click.option("--type", "target_type", required=True, 
              type=click.Choice(["node", "decision", "edge", "project"]))
@click.option("--content", required=True, help="评论内容")
def collab_comment(file: str, target: str, target_type: str, content: str):
    """添加评论"""
    projmap = ProjMap.load(file)
    manager = CollaborationManager(projmap)
    
    if not manager.get_current_user():
        console.print("[red]错误: 请先设置当前用户 (projmap collab user)[/red]")
        sys.exit(1)
    
    comment = manager.add_comment(
        target_type=CommentTargetType(target_type),
        target_id=target,
        content=content,
    )
    
    console.print(f"[green]✓[/green] 评论已添加: {comment.comment_id}")


@collab.command("comments")
@click.argument("file", type=click.Path(exists=True))
@click.option("--target", help="筛选目标ID")
@click.option("--type", "target_type", type=click.Choice(["node", "decision", "edge", "project"]))
def collab_comments(file: str, target: Optional[str], target_type: Optional[str]):
    """查看评论"""
    projmap = ProjMap.load(file)
    manager = CollaborationManager(projmap)
    
    target_type_enum = CommentTargetType(target_type) if target_type else None
    comments = manager.get_comments(target_type_enum, target)
    
    if not comments:
        console.print("[yellow]暂无评论[/yellow]")
        return
    
    table = Table(title=f"评论列表 ({len(comments)})")
    table.add_column("作者", style="cyan")
    table.add_column("目标", style="green")
    table.add_column("内容", style="yellow")
    table.add_column("时间", style="dim")
    
    for c in comments:
        time_str = c.created_at.strftime("%m-%d %H:%M")
        content = c.content[:40] + "..." if len(c.content) > 40 else c.content
        table.add_row(c.author.name, c.target_id[:20], content, time_str)
    
    console.print(table)


@collab.command("stats")
@click.argument("file", type=click.Path(exists=True))
def collab_stats(file: str):
    """显示协作统计"""
    projmap = ProjMap.load(file)
    manager = CollaborationManager(projmap)
    stats = manager.get_statistics()
    
    console.print(Panel(
        f"用户: {stats['users']}\n"
        f"评论: {stats['comments']} (未解决: {stats['unresolved_comments']})\n"
        f"待评审: {stats['pending_reviews']}\n"
        f"变更记录: {stats['total_changes']}",
        title="协作统计",
    ))


# ========== 科研领域命令 ==========

@main.group()
def research():
    """科研/ML实验管理（实验追踪、可复现性）"""
    pass


@research.command("experiment")
@click.argument("file", type=click.Path(exists=True))
@click.option("--name", required=True, help="实验名称")
@click.option("--description", help="实验描述")
@click.option("--dataset", help="数据集版本")
@click.option("--seed", default=42, help="随机种子")
@click.option("--param", multiple=True, help="超参数 (key=value)")
def research_experiment(
    file: str, name: str, description: str, dataset: str, seed: int, param: tuple[str, ...]
):
    """创建实验"""
    projmap = ProjMap.load(file)
    manager = ResearchExperimentManager(projmap)
    
    hyperparameters = {}
    for p in param:
        if "=" in p:
            k, v = p.split("=", 1)
            hyperparameters[k] = v
    
    exp = manager.create_experiment(
        name=name,
        description=description or "",
        hyperparameters=hyperparameters,
        dataset_version=dataset or "",
        random_seed=seed,
    )
    
    console.print(f"[green]✓[/green] 实验已创建: {exp.experiment_id}")
    console.print(f"  名称: {name}")
    console.print(f"  随机种子: {seed}")
    console.print(f"  环境: Python {exp.environment.get('python_version', 'unknown')[:20]}")


@research.command("result")
@click.argument("file", type=click.Path(exists=True))
@click.option("--experiment", required=True, help="实验ID")
@click.option("--metrics", required=True, help="指标JSON (如 '{\"accuracy\": 0.95}')")
@click.option("--time", default=0.0, help="训练时间(秒)")
@click.option("--checkpoint", help="检查点路径")
def research_result(file: str, experiment: str, metrics: str, time: float, checkpoint: str):
    """记录实验结果"""
    projmap = ProjMap.load(file)
    manager = ResearchExperimentManager(projmap)
    
    try:
        metrics_dict = json.loads(metrics)
    except json.JSONDecodeError:
        console.print("[red]错误: 指标格式不正确，应为JSON[/red]")
        sys.exit(1)
    
    result = manager.record_result(
        experiment_id=experiment,
        metrics=metrics_dict,
        training_time=time,
        checkpoint_path=checkpoint or "",
    )
    
    console.print(f"[green]✓[/green] 结果已记录: {result.result_id}")
    console.print(f"  指标: {metrics}")


@research.command("compare")
@click.argument("file", type=click.Path(exists=True))
@click.option("--experiments", required=True, help="实验ID列表 (逗号分隔)")
def research_compare(file: str, experiments: str):
    """对比实验"""
    projmap = ProjMap.load(file)
    manager = ResearchExperimentManager(projmap)
    
    exp_ids = [e.strip() for e in experiments.split(",")]
    comparison = manager.compare_experiments(exp_ids)
    
    console.print(Panel(f"对比 {len(comparison['experiments'])} 个实验", title="实验对比"))
    
    if comparison["best_by_metric"]:
        console.print("\n[bold]各指标最佳:[/bold]")
        for metric, best in comparison["best_by_metric"].items():
            console.print(f"  {metric}: {best['experiment']} = {best['value']}")


@research.command("paper")
@click.argument("file", type=click.Path(exists=True))
@click.option("--title", required=True, help="论文标题")
@click.option("--arxiv", help="arXiv ID")
@click.option("--url", help="论文URL")
def research_paper(file: str, title: str, arxiv: str, url: str):
    """关联论文"""
    projmap = ProjMap.load(file)
    manager = ResearchExperimentManager(projmap)
    
    mapping = manager.map_paper_to_code(
        paper_title=title,
        arxiv_id=arxiv or "",
        paper_url=url or "",
    )
    
    console.print(f"[green]✓[/green] 论文已关联: {title}")
    if arxiv:
        console.print(f"  arXiv: {arxiv}")


@research.command("reproducibility")
@click.argument("file", type=click.Path(exists=True))
def research_reproducibility(file: str):
    """生成可复现性报告"""
    projmap = ProjMap.load(file)
    manager = ResearchExperimentManager(projmap)
    
    report = manager.generate_reproducibility_report()
    
    console.print(Panel(
        f"实验数: {report['total_experiments']}\n"
        f"结果数: {report['total_results']}\n"
        f"环境一致: {'是' if report['environment_consistency'] else '否'}",
        title="可复现性报告",
    ))
    
    if report["recommendations"]:
        console.print("\n[bold yellow]建议:[/bold yellow]")
        for rec in report["recommendations"]:
            console.print(f"  • {rec}")


# ========== 金融科技领域命令 ==========

@main.group()
def fintech():
    """金融科技/量化交易管理（合规审计、版本控制）"""
    pass


@fintech.command("audit")
@click.argument("file", type=click.Path(exists=True))
@click.option("--entity", required=True, help="实体ID")
@click.option("--action", required=True, help="操作描述")
@click.option("--reason", required=True, help="操作原因")
@click.option("--operator", required=True, help="操作人")
@click.option("--risk", type=click.Choice(["low", "medium", "high", "critical"]), default="medium")
def fintech_audit(file: str, entity: str, action: str, reason: str, operator: str, risk: str):
    """记录合规审计"""
    projmap = ProjMap.load(file)
    auditor = ComplianceAuditor(projmap)
    
    risk_level = RiskLevel(risk)
    
    record = auditor.record_action(
        record_type="manual_action",
        entity_id=entity,
        operator=operator,
        action=action,
        reason=reason,
        risk_level=risk_level,
    )
    
    console.print(f"[green]✓[/green] 审计记录已创建: {record.record_id}")
    console.print(f"  风险等级: {risk}")
    if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        console.print(f"  [yellow]状态: 待审批[/yellow]")


@fintech.command("approve")
@click.argument("file", type=click.Path(exists=True))
@click.option("--record", required=True, help="记录ID")
@click.option("--approver", required=True, help="审批人")
@click.option("--reject", is_flag=True, help="拒绝而非批准")
def fintech_approve(file: str, record: str, approver: str, reject: bool):
    """审批操作"""
    projmap = ProjMap.load(file)
    auditor = ComplianceAuditor(projmap)
    
    success = auditor.approve_action(record, approver, not reject)
    
    if success:
        action = "拒绝" if reject else "批准"
        console.print(f"[green]✓[/green] 已{action}: {record}")
    else:
        console.print(f"[red]✗[/red] 审批失败")


@fintech.command("audit-report")
@click.argument("file", type=click.Path(exists=True))
def fintech_audit_report(file: str):
    """生成审计报告"""
    projmap = ProjMap.load(file)
    auditor = ComplianceAuditor(projmap)
    
    report = auditor.generate_audit_report()
    
    console.print(Panel(
        f"总操作: {report['total_actions']}\n"
        f"待审批: {report['pending_approvals']}\n"
        f"数据完整性: {'通过' if report['integrity_check']['is_valid'] else '异常'}",
        title="审计报告",
    ))
    
    if report["by_risk_level"]:
        console.print("\n[bold]风险分布:[/bold]")
        for level, count in report["by_risk_level"].items():
            console.print(f"  {level}: {count}")


@fintech.command("strategy")
@click.argument("file", type=click.Path(exists=True))
@click.option("--name", required=True, help="策略名称")
@click.option("--version", required=True, help="版本号 (如 1.2.3)")
@click.option("--files", required=True, help="代码文件路径 (逗号分隔)")
@click.option("--operator", required=True, help="操作人")
@click.option("--framework", help="监管框架")
def fintech_strategy(file: str, name: str, version: str, files: str, operator: str, framework: str):
    """创建策略版本"""
    projmap = ProjMap.load(file)
    auditor = ComplianceAuditor(projmap)
    manager = StrategyVersionManager(projmap, auditor)
    
    file_list = [f.strip() for f in files.split(",")]
    
    strategy = manager.create_version(
        strategy_name=name,
        version_number=version,
        code_files=file_list,
        parameters={},
        regulatory_framework=framework or "",
        operator=operator,
    )
    
    console.print(f"[green]✓[/green] 策略版本已创建: {strategy.version_id}")
    console.print(f"  {name}@{version}")
    console.print(f"  代码哈希: {strategy.code_hash}")


@fintech.command("backtest")
@click.argument("file", type=click.Path(exists=True))
@click.option("--version", required=True, help="策略版本ID")
@click.option("--start", required=True, help="开始日期 (YYYY-MM-DD)")
@click.option("--end", required=True, help="结束日期 (YYYY-MM-DD)")
@click.option("--return", "total_return", type=float, required=True, help="总收益率")
@click.option("--sharpe", type=float, required=True, help="夏普比率")
@click.option("--drawdown", type=float, required=True, help="最大回撤")
def fintech_backtest(
    file: str, version: str, start: str, end: str, total_return: float, sharpe: float, drawdown: float
):
    """记录回测结果"""
    projmap = ProjMap.load(file)
    auditor = ComplianceAuditor(projmap)
    manager = StrategyVersionManager(projmap, auditor)
    
    from projmap.fintech_domain import BacktestRecord
    
    backtest = BacktestRecord(
        backtest_id=str(uuid4())[:12],
        strategy_version=version,
        start_date=start,
        end_date=end,
        initial_capital=1000000.0,
        final_capital=1000000.0 * (1 + total_return),
        total_return=total_return,
        sharpe_ratio=sharpe,
        max_drawdown=drawdown,
        win_rate=0.0,
        trade_count=0,
    )
    
    success = manager.record_backtest(version, backtest)
    
    if success:
        console.print(f"[green]✓[/green] 回测结果已记录: {backtest.backtest_id}")
        console.print(f"  收益率: {total_return:.2%}")
        console.print(f"  夏普比率: {sharpe:.2f}")
        console.print(f"  最大回撤: {drawdown:.2%}")
    else:
        console.print("[red]✗[/red] 记录失败")


@fintech.command("compare-versions")
@click.argument("file", type=click.Path(exists=True))
@click.option("--v1", required=True, help="版本ID 1")
@click.option("--v2", required=True, help="版本ID 2")
def fintech_compare_versions(file: str, v1: str, v2: str):
    """对比策略版本"""
    projmap = ProjMap.load(file)
    auditor = ComplianceAuditor(projmap)
    manager = StrategyVersionManager(projmap, auditor)
    
    comparison = manager.compare_versions(v1, v2)
    
    if "error" in comparison:
        console.print(f"[red]错误: {comparison['error']}[/red]")
        return
    
    console.print(Panel(
        f"版本1: {comparison['version1']['number']}\n"
        f"版本2: {comparison['version2']['number']}",
        title="版本对比",
    ))
    
    if comparison["parameter_diff"]:
        console.print("\n[bold]参数差异:[/bold]")
        for param, diff in comparison["parameter_diff"].items():
            console.print(f"  {param}: {diff['old']} → {diff['new']}")
    
    if comparison["backtest_comparison"]:
        console.print("\n[bold]回测对比:[/bold]")
        bc = comparison["backtest_comparison"]
        if "total_return" in bc:
            console.print(f"  收益率: {bc['total_return']['v1']:.2%} → {bc['total_return']['v2']:.2%} "
                         f"(差值: {bc['total_return']['diff']:+.2%})")


# ========== HTML生成命令 ==========

@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "-o", "--output",
    type=click.Path(),
    help="输出HTML文件路径（默认：同名_map.html）",
)
@click.option(
    "-n", "--name",
    type=str,
    help="项目名称（显示在标题）",
)
@click.option(
    "--minify",
    is_flag=True,
    help="压缩JSON数据（减小文件大小）",
)
@click.option(
    "--open",
    "open_browser",
    is_flag=True,
    help="生成后自动在浏览器中打开",
)
def html(
    file: str,
    output: Optional[str],
    name: Optional[str],
    minify: bool,
    open_browser: bool,
):
    """生成可独立运行的HTML脉络图。
    
    将.projmap数据内嵌到HTML中，解决浏览器CORS限制问题。
    生成的HTML文件可双击直接打开，无需服务器。
    
    示例:
        projmap html my_project.projmap
        projmap html my_project.projmap -o report.html --open
    """
    from projmap.html_generator import HTMLGenerator
    
    generator = HTMLGenerator()
    
    if output is None:
        base_name = os.path.splitext(file)[0]
        output = f"{base_name}_map.html"
    
    try:
        result_path = generator.generate_from_file(
            projmap_file=file,
            output_path=output,
            project_name=name,
            minify_json=minify,
        )
        
        file_size = os.path.getsize(result_path)
        size_kb = file_size / 1024
        
        console.print(Panel(
            f"[green]✓[/green] HTML文件已生成\n\n"
            f"输出路径: [cyan]{result_path}[/cyan]\n"
            f"文件大小: [yellow]{size_kb:.1f} KB[/yellow]\n\n"
            f"[dim]💡 双击HTML文件即可在浏览器中查看脉络图[/dim]",
            title="HTML生成成功",
        ))
        
        if open_browser:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(result_path)}")
            console.print("[dim]已在浏览器中打开[/dim]")
        
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
    except Exception as e:
        console.print(f"[red]生成失败: {e}[/red]")


@main.command()
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option(
    "-o", "--output",
    type=click.Path(),
    default="project_map.html",
    help="输出HTML文件路径",
)
@click.option(
    "-n", "--name",
    type=str,
    help="项目名称",
)
@click.option(
    "--scan/--no-scan",
    default=True,
    help="是否先扫描项目生成.projmap",
)
@click.option(
    "--open",
    "open_browser",
    is_flag=True,
    help="生成后自动在浏览器中打开",
)
def quick(
    path: str,
    output: str,
    name: Optional[str],
    scan: bool,
    open_browser: bool,
):
    """快速生成HTML脉络图（一键扫描+生成）。
    
    自动扫描项目并生成可独立运行的HTML文件。
    适合快速查看项目结构。
    
    示例:
        projmap quick ./my_project
        projmap quick ./my_project -o overview.html --open
    """
    from projmap.html_generator import HTMLGenerator
    
    root_path = os.path.abspath(path)
    project_name = name or os.path.basename(root_path)
    
    console.print(f"[dim]正在扫描项目: {root_path}[/dim]")
    
    if scan:
        projmap = generate_projmap(
            root_path=root_path,
            project_name=project_name,
        )
        projmap_data = projmap.to_dict()
    else:
        projmap_file = os.path.join(root_path, ".projmap", "project.projmap")
        if os.path.exists(projmap_file):
            projmap = ProjMap.load(projmap_file)
            projmap_data = projmap.to_dict()
        else:
            console.print(f"[red]错误: 未找到.projmap文件，请使用 --scan 参数[/red]")
            return
    
    generator = HTMLGenerator()
    
    try:
        result_path = generator.generate(
            projmap_data=projmap_data,
            output_path=output,
            project_name=project_name,
        )
        
        file_size = os.path.getsize(result_path)
        size_kb = file_size / 1024
        
        console.print(Panel(
            f"[green]✓[/green] HTML文件已生成\n\n"
            f"项目: [cyan]{project_name}[/cyan]\n"
            f"节点: [yellow]{len(projmap_data.get('nodes', []))}[/yellow]\n"
            f"输出: [cyan]{result_path}[/cyan]\n"
            f"大小: [yellow]{size_kb:.1f} KB[/yellow]\n\n"
            f"[dim]💡 双击HTML文件即可在浏览器中查看[/dim]",
            title="快速生成完成",
        ))
        
        if open_browser:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(result_path)}")
            console.print("[dim]已在浏览器中打开[/dim]")
        
    except Exception as e:
        console.print(f"[red]生成失败: {e}[/red]")


if __name__ == "__main__":
    main()


# ========== 技术标签命令 ==========

@main.group()
def tag():
    """技术标签管理（自动识别、决策关联）"""
    pass


@tag.command("scan")
@click.argument("file", type=click.Path(exists=True))
@click.option("--node", help="只扫描指定节点")
@click.option("--domain", type=click.Choice(["fintech", "research", "software", "all"]), default="all",
              help="标签领域")
def tag_scan(file: str, node: Optional[str], domain: str):
    """扫描并自动打标签"""
    projmap = ProjMap.load(file)
    manager = TechTagManager(projmap)
    
    nodes_to_scan = projmap.nodes
    if node:
        nodes_to_scan = [n for n in projmap.nodes if n.id == node]
    
    total_new_tags = 0
    table = Table(title="扫描结果")
    table.add_column("节点", style="cyan")
    table.add_column("新标签", style="green")
    table.add_column("标签列表", style="yellow")
    
    for n in nodes_to_scan:
        new_tags = manager.auto_tag_node(n.id)
        total_new_tags += len(new_tags)
        
        if new_tags:
            tag_names = [t.name for t in new_tags[:5]]
            if len(new_tags) > 5:
                tag_names.append(f"... (+{len(new_tags) - 5})")
            table.add_row(n.name, str(len(new_tags)), ", ".join(tag_names))
    
    projmap.save(file)
    
    console.print(table)
    console.print(f"\n[green]✓[/green] 共发现 {total_new_tags} 个新标签")


@tag.command("list")
@click.argument("file", type=click.Path(exists=True))
@click.option("--node", help="筛选节点ID")
@click.option("--domain", help="筛选领域")
@click.option("--unlinked", is_flag=True, help="只显示未关联决策的标签")
def tag_list(file: str, node: Optional[str], domain: Optional[str], unlinked: bool):
    """列出技术标签"""
    projmap = ProjMap.load(file)
    
    table = Table(title="技术标签列表")
    table.add_column("节点", style="cyan")
    table.add_column("标签", style="green")
    table.add_column("领域", style="yellow")
    table.add_column("类别", style="blue")
    table.add_column("决策", style="magenta")
    
    domain_colors = {
        "fintech": "[blue]金融科技[/blue]",
        "research": "[green]科研分析[/green]",
        "software": "[magenta]软件开发[/magenta]",
        "custom": "[dim]自定义[/dim]",
    }
    
    for n in projmap.nodes:
        if node and n.id != node:
            continue
        
        if not n.tech_tags:
            continue
        
        for t in n.tech_tags:
            if domain and t.domain != domain:
                continue
            
            if unlinked and t.decision_id:
                continue
            
            decision_status = "[green]✓[/green]" if t.decision_id else "[dim]✗[/dim]"
            domain_str = domain_colors.get(t.domain, t.domain)
            
            table.add_row(
                n.name[:20],
                t.name,
                domain_str,
                t.category,
                decision_status,
            )
    
    console.print(table)


@tag.command("add")
@click.argument("file", type=click.Path(exists=True))
@click.option("--node", required=True, help="节点ID")
@click.option("--name", required=True, help="标签名称")
@click.option("--category", default="custom", help="标签类别")
@click.option("--domain", default="custom", help="标签领域")
def tag_add(file: str, node: str, name: str, category: str, domain: str):
    """手动添加标签"""
    projmap = ProjMap.load(file)
    manager = TechTagManager(projmap)
    
    try:
        tag = manager.add_manual_tag(node, name, category, domain)
        projmap.save(file)
        console.print(f"[green]✓[/green] 标签已添加: {name}")
    except ValueError as e:
        console.print(f"[red]错误: {e}[/red]")


@tag.command("suggest")
@click.argument("partial", type=str)
def tag_suggest(partial: str):
    """获取标签建议（自动补全）"""
    recognizer = TechTagRecognizer()
    suggestions = recognizer.get_tag_suggestions(partial)
    
    if not suggestions:
        console.print(f"[yellow]未找到匹配 '{partial}' 的标签[/yellow]")
        return
    
    table = Table(title=f"标签建议 (输入: {partial})")
    table.add_column("标签", style="cyan")
    table.add_column("关键词", style="green")
    table.add_column("领域", style="yellow")
    table.add_column("类别", style="blue")
    
    for s in suggestions:
        table.add_row(s["name"], s["keyword"], s["domain"], s["category"])
    
    console.print(table)


@tag.command("link-decision")
@click.argument("file", type=click.Path(exists=True))
@click.option("--node", required=True, help="节点ID")
@click.option("--tag", "tag_name", required=True, help="标签名称")
@click.option("--content", required=True, help="决策内容")
@click.option("--reason", help="决策理由")
@click.option("--alternatives", help="备选方案（逗号分隔）")
@click.option("--basis", help="决策依据")
def tag_link_decision(
    file: str, node: str, tag_name: str, content: str, 
    reason: Optional[str], alternatives: Optional[str], basis: Optional[str]
):
    """为标签关联决策记录"""
    projmap = ProjMap.load(file)
    manager = TechTagManager(projmap)
    
    alt_list = [a.strip() for a in alternatives.split(",")] if alternatives else []
    
    try:
        decision = manager.create_decision_for_tag(
            node_id=node,
            tag_name=tag_name,
            content=content,
            reason=reason or "",
            alternatives=alt_list,
            decision_basis=basis or "",
        )
        projmap.save(file)
        console.print(f"[green]✓[/green] 决策已关联到标签: {tag_name}")
        console.print(f"  决策ID: {decision.id}")
    except ValueError as e:
        console.print(f"[red]错误: {e}[/red]")


@tag.command("vocab")
@click.option("--domain", type=click.Choice(["fintech", "research", "software", "all"]), default="all")
def tag_vocab(domain: str):
    """显示技术标签词库"""
    from projmap.tech_tags import TECH_TAG_VOCABULARY
    
    domains_to_show = [domain] if domain != "all" else ["fintech", "research", "software"]
    
    for d in domains_to_show:
        if d not in TECH_TAG_VOCABULARY:
            continue
        
        console.print(f"\n[bold cyan]{d.upper()} 词库:[/bold cyan]")
        
        for category, info in TECH_TAG_VOCABULARY[d].items():
            console.print(f"\n  [bold]{category}[/bold] - {info['description']}")
            keywords = info["keywords"][:10]
            keyword_str = ", ".join(keywords)
            if len(info["keywords"]) > 10:
                keyword_str += f" ... (+{len(info['keywords']) - 10})"
            console.print(f"  [dim]{keyword_str}[/dim]")


# ========== 废弃路径命令 ==========

@main.group()
def abandon():
    """废弃路径管理（强制决策记录）"""
    pass


@abandon.command("node")
@click.argument("file", type=click.Path(exists=True))
@click.option("--node", required=True, help="节点ID")
@click.option("--method", required=True, help="废弃的方法名称")
@click.option("--reason", required=True, help="废弃原因")
@click.option("--solutions", help="尝试过的解决方案（逗号分隔）")
@click.option("--revive-condition", help="唤醒条件")
@click.option("--no-revive", is_flag=True, help="标记为不可唤醒")
def abandon_node(
    file: str, node: str, method: str, reason: str, 
    solutions: Optional[str], revive_condition: Optional[str], no_revive: bool
):
    """废弃节点（强制记录决策）"""
    projmap = ProjMap.load(file)
    manager = AbandonmentManager(projmap)
    
    solutions_list = [s.strip() for s in solutions.split(",")] if solutions else []
    
    try:
        node_obj, decision = manager.abandon_node(
            node_id=node,
            abandoned_method=method,
            abandon_reason=reason,
            attempted_solutions=solutions_list,
            can_revive=not no_revive,
            revive_condition=revive_condition or "",
        )
        projmap.save(file)
        
        console.print(f"[yellow]✓[/yellow] 节点已废弃: {node_obj.name}")
        console.print(f"  废弃方法: {method}")
        console.print(f"  决策ID: {decision.id}")
        if revive_condition:
            console.print(f"  唤醒条件: {revive_condition}")
    except ValueError as e:
        console.print(f"[red]错误: {e}[/red]")


@abandon.command("revive")
@click.argument("file", type=click.Path(exists=True))
@click.option("--node", required=True, help="节点ID")
@click.option("--reason", required=True, help="唤醒原因")
def abandon_revive(file: str, node: str, reason: str):
    """唤醒废弃节点"""
    projmap = ProjMap.load(file)
    manager = AbandonmentManager(projmap)
    
    try:
        node_obj, decision = manager.revive_node(node_id=node, revive_reason=reason)
        projmap.save(file)
        
        console.print(f"[green]✓[/green] 节点已唤醒: {node_obj.name}")
        console.print(f"  决策ID: {decision.id}")
    except ValueError as e:
        console.print(f"[red]错误: {e}[/red]")


@abandon.command("list")
@click.argument("file", type=click.Path(exists=True))
@click.option("--revivable", is_flag=True, help="只显示可唤醒的节点")
def abandon_list(file: str, revivable: bool):
    """列出废弃节点"""
    projmap = ProjMap.load(file)
    manager = AbandonmentManager(projmap)
    
    if revivable:
        nodes = manager.get_revivable_nodes()
        title = "可唤醒的废弃节点"
    else:
        nodes = [n for n in projmap.nodes if n.abandon_info]
        title = "所有废弃节点"
    
    if not nodes:
        console.print(f"[yellow]无{title}[/yellow]")
        return
    
    table = Table(title=title)
    table.add_column("节点", style="cyan")
    table.add_column("废弃方法", style="yellow")
    table.add_column("废弃原因", style="red")
    table.add_column("可唤醒", style="green")
    
    for n in nodes:
        can_revive = "✓" if n.abandon_info.can_revive else "✗"
        reason = n.abandon_info.abandon_reason[:40] + "..." if len(n.abandon_info.abandon_reason) > 40 else n.abandon_info.abandon_reason
        table.add_row(n.name, n.abandon_info.abandoned_method, reason, can_revive)
    
    console.print(table)


# ========== 推断标注命令 ==========

@main.group()
def inference():
    """推断标注管理（冷启动支持）"""
    pass


@inference.command("list")
@click.argument("file", type=click.Path(exists=True))
def inference_list(file: str):
    """列出未确认的推断节点"""
    projmap = ProjMap.load(file)
    annotator = InferenceAnnotator(projmap)
    
    nodes = annotator.get_unconfirmed_nodes()
    
    if not nodes:
        console.print("[green]✓ 所有推断内容已确认[/green]")
        return
    
    table = Table(title=f"待确认推断 ({len(nodes)})")
    table.add_column("节点", style="cyan")
    table.add_column("推断来源", style="yellow")
    table.add_column("置信度", style="green")
    table.add_column("文件", style="dim")
    
    source_labels = {
        "llm": "AI推断",
        "rule": "规则推断",
        "git": "Git历史",
        "manual": "手动",
        "unknown": "未知",
    }
    
    for n in nodes:
        source_str = source_labels.get(n.inferred_by, n.inferred_by)
        table.add_row(n.name, source_str, f"{n.confidence:.0%}", n.file_path[:40])
    
    console.print(table)


@inference.command("confirm")
@click.argument("file", type=click.Path(exists=True))
@click.option("--node", required=True, help="节点ID")
def inference_confirm(file: str, node: str):
    """确认推断内容"""
    projmap = ProjMap.load(file)
    annotator = InferenceAnnotator(projmap)
    
    annotator.confirm_inference(node)
    projmap.save(file)
    
    console.print(f"[green]✓[/green] 推断已确认")


@inference.command("confirm-all")
@click.argument("file", type=click.Path(exists=True))
def inference_confirm_all(file: str):
    """确认所有推断内容"""
    projmap = ProjMap.load(file)
    annotator = InferenceAnnotator(projmap)
    
    nodes = annotator.get_unconfirmed_nodes()
    for n in nodes:
        annotator.confirm_inference(n.id)
    
    projmap.save(file)
    
    console.print(f"[green]✓[/green] 已确认 {len(nodes)} 个推断")


@inference.command("infer-name")
@click.argument("file_path", type=click.Path(exists=True))
def inference_infer_name(file_path: str):
    """推断文件任务名称"""
    recognizer = TechTagRecognizer()
    annotator = InferenceAnnotator(ProjMap(nodes=[], edges=[], decisions=[]))
    
    name, confidence = annotator.infer_task_name(file_path)
    
    console.print(f"[bold]推断结果:[/bold]")
    console.print(f"  任务名称: [green]{name}[/green]")
    console.print(f"  置信度: [yellow]{confidence:.0%}[/yellow]")


@inference.command("infer-flow")
@click.argument("file_path", type=click.Path(exists=True))
def inference_infer_flow(file_path: str):
    """推断数据流向"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        console.print(f"[red]错误: 无法读取文件 - {e}[/red]")
        return
    
    annotator = InferenceAnnotator(ProjMap(nodes=[], edges=[], decisions=[]))
    inputs, outputs = annotator.infer_data_flow(content)
    
    console.print(f"[bold]数据流向推断:[/bold]")
    
    if inputs:
        console.print(f"\n[green]输入源 ({len(inputs)}):[/green]")
        for inp in inputs[:10]:
            console.print(f"  • {inp}")
    else:
        console.print(f"\n[dim]未检测到输入源[/dim]")
    
    if outputs:
        console.print(f"\n[blue]输出目标 ({len(outputs)}):[/blue]")
        for out in outputs[:10]:
            console.print(f"  • {out}")
    else:
        console.print(f"\n[dim]未检测到输出目标[/dim]")
