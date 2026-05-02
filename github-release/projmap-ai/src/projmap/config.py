"""配置文件支持模块

支持 .projmaprc 配置文件，用于存储项目级别的默认设置。
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


CONFIG_FILE_NAMES = [".projmaprc", ".projmaprc.json", "projmap.json"]


@dataclass
class ProjMapConfig:
    trust_level: int = 1
    llm_model: Optional[str] = None
    llm_base_url: str = "https://api.deepseek.com/v1"
    excludes: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    max_depth: Optional[int] = None
    auto_update: bool = False
    output_path: str = ".projmap/project.projmap"
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ProjMapConfig":
        return cls(
            trust_level=data.get("trust_level", 1),
            llm_model=data.get("llm_model"),
            llm_base_url=data.get("llm_base_url", "https://api.deepseek.com/v1"),
            excludes=data.get("excludes", []),
            include_patterns=data.get("include_patterns", []),
            max_depth=data.get("max_depth"),
            auto_update=data.get("auto_update", False),
            output_path=data.get("output_path", ".projmap/project.projmap"),
        )
    
    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: str) -> "ProjMapConfig":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


def find_config_file(start_path: str = ".") -> Optional[str]:
    start = Path(start_path).resolve()
    
    for path in [start] + list(start.parents):
        for name in CONFIG_FILE_NAMES:
            config_path = path / name
            if config_path.exists():
                return str(config_path)
    
    return None


def load_config(start_path: str = ".") -> ProjMapConfig:
    config_file = find_config_file(start_path)
    
    if config_file:
        try:
            return ProjMapConfig.load(config_file)
        except (json.JSONDecodeError, KeyError):
            pass
    
    return ProjMapConfig()


def save_config(config: ProjMapConfig, path: str = ".projmaprc") -> None:
    config.save(path)


def create_default_config(path: str = ".projmaprc") -> ProjMapConfig:
    config = ProjMapConfig(
        trust_level=2,
        excludes=[
            "*.pyc",
            "__pycache__",
            ".git",
            "node_modules",
            "*.egg-info",
        ],
    )
    config.save(path)
    return config
