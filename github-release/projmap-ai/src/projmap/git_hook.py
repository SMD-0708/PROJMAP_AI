"""Git Hook 集成模块

提供 Git Hook 脚本生成和安装功能。
事件驱动更新机制：不做实时监控，更新由明确事件触发。
"""

import os
import stat
from pathlib import Path
from typing import Optional


POST_COMMIT_HOOK_TEMPLATE = '''#!/bin/sh
# ProjMap Git Hook - 自动更新项目脉络图
# 此脚本在每次 git commit 后自动运行

# 检查是否在 ProjMap 项目中
if [ -f ".projmap/project.projmap" ]; then
    echo "ProjMap: 检测到项目脉络图文件，正在更新..."
    
    # 获取当前项目根目录
    PROJECT_ROOT="$(git rev-parse --show-toplevel)"
    PROJMAP_FILE="$PROJECT_ROOT/.projmap/project.projmap"
    
    # 检查 projmap 命令是否可用
    if command -v projmap &> /dev/null; then
        # 更新 projmap（信任级别不变）
        projmap init "$PROJECT_ROOT" -o "$PROJMAP_FILE" --trust-level 1
        
        echo "ProjMap: 项目脉络图已更新"
    else
        echo "ProjMap: projmap 命令未找到，请安装 ProjMap CLI"
    fi
fi
'''

POST_COMMIT_HOOK_TEMPLATE_WIN = '''@echo off
REM ProjMap Git Hook - 自动更新项目脉络图
REM 此脚本在每次 git commit 后自动运行

REM 检查是否在 ProjMap 项目中
if exist .projmap\\project.projmap (
    echo ProjMap: 检测到项目脉络图文件，正在更新...
    
    REM 检查 projmap 命令是否可用
    where projmap >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        REM 更新 projmap
        projmap init . -o .projmap\\project.projmap --trust-level 1
        
        echo ProjMap: 项目脉络图已更新
    ) else (
        echo ProjMap: projmap 命令未找到，请安装 ProjMap CLI
    )
)
'''


class GitHookManager:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.git_dir = self.project_root / ".git"
        self.hooks_dir = self.git_dir / "hooks"
    
    def is_git_repo(self) -> bool:
        return self.git_dir.exists() and self.git_dir.is_dir()
    
    def install_hook(self, hook_type: str = "post-commit") -> bool:
        if not self.is_git_repo():
            return False
        
        hook_path = self.hooks_dir / hook_type
        
        is_windows = os.name == 'nt' or os.environ.get('OS', '').startswith('Windows')
        
        if is_windows and hook_type == "post-commit":
            template = POST_COMMIT_HOOK_TEMPLATE_WIN
            ext = ".bat"
            hook_path = hook_path.with_suffix(".bat")
        else:
            template = POST_COMMIT_HOOK_TEMPLATE
            ext = ""
        
        hook_path = hook_path.with_suffix(ext) if not str(hook_path).endswith(ext) else hook_path
        
        try:
            with open(hook_path, "w", encoding="utf-8") as f:
                f.write(template)
            
            if not is_windows:
                os.chmod(hook_path, os.stat(hook_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            
            return True
        except (IOError, OSError):
            return False
    
    def uninstall_hook(self, hook_type: str = "post-commit") -> bool:
        if not self.is_git_repo():
            return False
        
        hook_path = self.hooks_dir / hook_type
        
        is_windows = os.name == 'nt' or os.environ.get('OS', '').startswith('Windows')
        if is_windows:
            hook_path = hook_path.with_suffix(".bat")
        
        try:
            if hook_path.exists():
                hook_path.unlink()
            return True
        except (IOError, OSError):
            return False
    
    def is_hook_installed(self, hook_type: str = "post-commit") -> bool:
        if not self.is_git_repo():
            return False
        
        hook_path = self.hooks_dir / hook_type
        
        is_windows = os.name == 'nt' or os.environ.get('OS', '').startswith('Windows')
        if is_windows:
            hook_path = hook_path.with_suffix(".bat")
        
        if hook_path.exists():
            try:
                with open(hook_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    return "ProjMap" in content
            except (IOError, OSError):
                pass
        
        return False
    
    def get_hook_script(self, hook_type: str = "post-commit") -> Optional[str]:
        is_windows = os.name == 'nt' or os.environ.get('OS', '').startswith('Windows')
        
        if is_windows and hook_type == "post-commit":
            return POST_COMMIT_HOOK_TEMPLATE_WIN
        elif hook_type == "post-commit":
            return POST_COMMIT_HOOK_TEMPLATE
        
        return None


def install_git_hook(project_root: str, hook_type: str = "post-commit") -> bool:
    manager = GitHookManager(project_root)
    return manager.install_hook(hook_type)


def uninstall_git_hook(project_root: str, hook_type: str = "post-commit") -> bool:
    manager = GitHookManager(project_root)
    return manager.uninstall_hook(hook_type)


def check_hook_installed(project_root: str, hook_type: str = "post-commit") -> bool:
    manager = GitHookManager(project_root)
    return manager.is_hook_installed(hook_type)
