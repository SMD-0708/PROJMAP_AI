"""配置管理模块

提供集中式的配置管理，支持从文件、环境变量和代码中读取配置。
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


@dataclass
class NavigatorConfig:
    """导航器配置"""
    # 重要性评分权重
    status_weight_multiplier: float = 30.0
    incoming_weight: float = 5.0
    incoming_max: float = 20.0
    outgoing_weight: float = 3.0
    outgoing_max: float = 15.0
    description_bonus: float = 5.0
    decision_bonus: float = 2.0
    decision_max: float = 10.0
    
    # 状态权重
    status_weights: dict[str, float] = field(default_factory=lambda: {
        "active_main": 1.0,
        "active_branch": 0.7,
        "dormant": 0.3,
        "archived": 0.1,
    })
    
    # 节点类型权重
    type_weights: dict[str, float] = field(default_factory=lambda: {
        "package": 10.0,
        "module": 8.0,
        "directory": 5.0,
        "file": 3.0,
    })
    
    # 路径生成配置
    max_quick_start_nodes: int = 15
    max_architecture_nodes: int = 10
    max_feature_nodes: int = 20
    max_active_dev_nodes: int = 12
    
    # 缓存配置
    enable_cache: bool = True
    cache_ttl: int = 300  # 秒
    importance_cache_ttl: int = 600  # 秒
    max_cache_size: int = 256
    max_importance_cache_size: int = 512


@dataclass
class StateMachineConfig:
    """状态机配置"""
    # 自动归档配置
    auto_archive_enabled: bool = True
    auto_archive_days: int = 30
    auto_archive_dry_run: bool = True
    
    # 历史记录配置
    history_enabled: bool = True
    history_dir: str = ".projmap/state_history"
    max_history_in_memory: int = 1000
    
    # 转换规则配置
    require_reason_for_main_activation: bool = True
    require_confirmation_for_archive: bool = True


@dataclass
class FailureRetrievalConfig:
    """失败检索配置"""
    # 相似度阈值
    similarity_threshold: float = 0.2
    max_similar_results: int = 5
    
    # 错误类型模式（可以扩展）
    custom_error_patterns: dict[str, str] = field(default_factory=dict)
    
    # 标签提取配置
    tech_keywords: list[str] = field(default_factory=lambda: [
        "python", "javascript", "java", "go", "rust",
        "api", "database", "cache", "async", "thread",
        "memory", "performance", "security", "config",
        "dependency", "version", "build", "deploy",
    ])


@dataclass
class AsyncConfig:
    """异步配置"""
    enabled: bool = False  # 默认关闭，需要显式启用
    max_workers: int = 4
    max_concurrency: int = 10
    batch_size: int = 100
    use_processes: bool = False  # 默认使用线程池


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    file: Optional[str] = None
    console: bool = True


@dataclass
class ProjMapSettings:
    """ProjMap 全局配置"""
    navigator: NavigatorConfig = field(default_factory=NavigatorConfig)
    state_machine: StateMachineConfig = field(default_factory=StateMachineConfig)
    failure_retrieval: FailureRetrievalConfig = field(default_factory=FailureRetrievalConfig)
    async_config: AsyncConfig = field(default_factory=AsyncConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ProjMapSettings":
        """从字典创建配置"""
        return cls(
            navigator=NavigatorConfig(**data.get("navigator", {})),
            state_machine=StateMachineConfig(**data.get("state_machine", {})),
            failure_retrieval=FailureRetrievalConfig(**data.get("failure_retrieval", {})),
            async_config=AsyncConfig(**data.get("async", {})),
            logging=LoggingConfig(**data.get("logging", {})),
        )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "navigator": asdict(self.navigator),
            "state_machine": asdict(self.state_machine),
            "failure_retrieval": asdict(self.failure_retrieval),
            "async": asdict(self.async_config),
            "logging": asdict(self.logging),
        }
    
    @classmethod
    def from_file(cls, path: str) -> "ProjMapSettings":
        """从 JSON 文件加载配置"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def to_file(self, path: str):
        """保存配置到 JSON 文件"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def from_env(cls) -> "ProjMapSettings":
        """从环境变量加载配置"""
        settings = cls()
        
        # 日志级别
        log_level = os.getenv("PROJMAP_LOG_LEVEL")
        if log_level:
            settings.logging.level = log_level
        
        # 异步配置
        async_enabled = os.getenv("PROJMAP_ASYNC_ENABLED")
        if async_enabled:
            settings.async_config.enabled = async_enabled.lower() in ("true", "1", "yes")
        
        max_workers = os.getenv("PROJMAP_MAX_WORKERS")
        if max_workers:
            settings.async_config.max_workers = int(max_workers)
        
        # 导航器配置
        cache_enabled = os.getenv("PROJMAP_CACHE_ENABLED")
        if cache_enabled:
            settings.navigator.enable_cache = cache_enabled.lower() in ("true", "1", "yes")
        
        return settings
    
    @classmethod
    def auto_load(cls, project_root: str = ".") -> "ProjMapSettings":
        """自动加载配置
        
        按以下顺序查找配置文件：
        1. 环境变量 PROJMAP_CONFIG
        2. 项目根目录下的 .projmaprc.json
        3. 用户主目录下的 .projmaprc.json
        4. 默认配置
        """
        # 1. 检查环境变量
        env_config = os.getenv("PROJMAP_CONFIG")
        if env_config and os.path.exists(env_config):
            return cls.from_file(env_config)
        
        # 2. 检查项目根目录
        project_config = os.path.join(project_root, ".projmaprc.json")
        if os.path.exists(project_config):
            return cls.from_file(project_config)
        
        # 3. 检查用户主目录
        home_config = os.path.join(Path.home(), ".projmaprc.json")
        if os.path.exists(home_config):
            return cls.from_file(home_config)
        
        # 4. 从环境变量加载部分配置
        return cls.from_env()
    
    def create_default_config_file(self, path: str):
        """创建默认配置文件"""
        default_config = {
            "navigator": {
                "enable_cache": True,
                "cache_ttl": 300,
                "max_quick_start_nodes": 15,
                "status_weights": {
                    "active_main": 1.0,
                    "active_branch": 0.7,
                    "dormant": 0.3,
                    "archived": 0.1,
                },
            },
            "state_machine": {
                "auto_archive_enabled": True,
                "auto_archive_days": 30,
                "history_enabled": True,
            },
            "async": {
                "enabled": False,
                "max_workers": 4,
                "max_concurrency": 10,
            },
            "logging": {
                "level": "INFO",
                "console": True,
            },
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)


# 全局配置实例
_global_settings: Optional[ProjMapSettings] = None


def get_settings() -> ProjMapSettings:
    """获取全局配置"""
    global _global_settings
    if _global_settings is None:
        _global_settings = ProjMapSettings.auto_load()
    return _global_settings


def set_settings(settings: ProjMapSettings):
    """设置全局配置"""
    global _global_settings
    _global_settings = settings


def init_settings(project_root: str = "."):
    """初始化配置"""
    global _global_settings
    _global_settings = ProjMapSettings.auto_load(project_root)
