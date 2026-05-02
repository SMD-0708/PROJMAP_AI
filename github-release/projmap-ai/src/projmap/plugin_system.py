"""插件系统模块

提供完整的插件架构，支持第三方扩展。
核心设计原则：
- 接口驱动：所有功能通过接口定义
- 生命周期管理：插件有明确的加载、启用、禁用、卸载阶段
- 事件机制：支持插件间通信
- 依赖管理：插件可以声明依赖关系
"""

import abc
import importlib
import importlib.util
import inspect
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, ClassVar, Optional, TypeVar, get_type_hints
from enum import Enum, auto
from datetime import datetime

logger = logging.getLogger(__name__)


class PluginState(Enum):
    """插件状态"""
    REGISTERED = auto()      # 已注册但未加载
    LOADING = auto()         # 正在加载
    LOADED = auto()          # 已加载但未启用
    ENABLING = auto()        # 正在启用
    ENABLED = auto()         # 已启用
    DISABLING = auto()       # 正在禁用
    DISABLED = auto()        # 已禁用
    ERROR = auto()           # 加载/运行出错
    UNLOADING = auto()       # 正在卸载


class PluginPriority(Enum):
    """插件优先级"""
    CRITICAL = 0      # 系统关键插件，最先加载
    HIGH = 100        # 高优先级
    NORMAL = 500      # 普通优先级（默认）
    LOW = 1000        # 低优先级
    BACKGROUND = 2000 # 后台任务


@dataclass
class PluginMetadata:
    """插件元数据"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    author_email: str = ""
    url: str = ""
    license: str = "MIT"
    
    # 依赖声明
    dependencies: list[str] = field(default_factory=list)  # 其他插件名称
    python_packages: list[str] = field(default_factory=list)  # Python包依赖
    
    # 功能声明
    provides: list[str] = field(default_factory=list)  # 提供的功能点
    hooks: list[str] = field(default_factory=list)  # 注册的钩子
    
    # 系统要求
    min_projmap_version: str = "0.1.0"
    max_projmap_version: str = ""
    
    @classmethod
    def from_dict(cls, data: dict) -> "PluginMetadata":
        """从字典创建"""
        return cls(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            author_email=data.get("author_email", ""),
            url=data.get("url", ""),
            license=data.get("license", "MIT"),
            dependencies=data.get("dependencies", []),
            python_packages=data.get("python_packages", []),
            provides=data.get("provides", []),
            hooks=data.get("hooks", []),
            min_projmap_version=data.get("min_projmap_version", "0.1.0"),
            max_projmap_version=data.get("max_projmap_version", ""),
        )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "author_email": self.author_email,
            "url": self.url,
            "license": self.license,
            "dependencies": self.dependencies,
            "python_packages": self.python_packages,
            "provides": self.provides,
            "hooks": self.hooks,
            "min_projmap_version": self.min_projmap_version,
            "max_projmap_version": self.max_projmap_version,
        }


class PluginInterface(abc.ABC):
    """插件接口基类
    
    所有插件必须继承此类并实现抽象方法。
    """
    
    # 类属性：插件元数据
    METADATA: ClassVar[PluginMetadata]
    
    # 类属性：优先级
    PRIORITY: ClassVar[PluginPriority] = PluginPriority.NORMAL
    
    def __init__(self):
        self._state = PluginState.REGISTERED
        self._plugin_manager: Optional["PluginManager"] = None
        self._config: dict = {}
        self._logger = logging.getLogger(f"projmap.plugin.{self.METADATA.name}")
    
    @property
    def state(self) -> PluginState:
        """获取插件状态"""
        return self._state
    
    @property
    def name(self) -> str:
        """获取插件名称"""
        return self.METADATA.name
    
    # ========== 生命周期方法 ==========
    
    def on_load(self, plugin_manager: "PluginManager", config: dict) -> bool:
        """插件加载时调用
        
        Args:
            plugin_manager: 插件管理器实例
            config: 插件配置
        
        Returns:
            是否加载成功
        """
        self._plugin_manager = plugin_manager
        self._config = config
        self._logger.info(f"插件 {self.name} 已加载")
        return True
    
    def on_enable(self) -> bool:
        """插件启用时调用
        
        Returns:
            是否启用成功
        """
        self._state = PluginState.ENABLED
        self._logger.info(f"插件 {self.name} 已启用")
        return True
    
    def on_disable(self) -> bool:
        """插件禁用时调用
        
        Returns:
            是否禁用成功
        """
        self._state = PluginState.DISABLED
        self._logger.info(f"插件 {self.name} 已禁用")
        return True
    
    def on_unload(self) -> bool:
        """插件卸载时调用
        
        Returns:
            是否卸载成功
        """
        self._state = PluginState.UNLOADING
        self._logger.info(f"插件 {self.name} 已卸载")
        return True
    
    # ========== 功能方法 ==========
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)
    
    def set_config(self, key: str, value: Any):
        """设置配置项"""
        self._config[key] = value
    
    def emit_event(self, event_name: str, data: Any = None):
        """发送事件"""
        if self._plugin_manager:
            self._plugin_manager.emit_event(event_name, data, self.name)
    
    def call_hook(self, hook_name: str, *args, **kwargs) -> list[Any]:
        """调用钩子
        
        所有注册了该钩子的插件都会收到调用。
        
        Returns:
            各插件返回结果的列表
        """
        if self._plugin_manager:
            return self._plugin_manager.call_hook(hook_name, *args, **kwargs)
        return []


# ========== 内置插件基类 ==========

class ScannerPlugin(PluginInterface):
    """扫描器插件基类
    
    用于扩展项目扫描功能。
    """
    
    @abc.abstractmethod
    def can_scan(self, file_path: str) -> bool:
        """判断是否能扫描该文件
        
        Args:
            file_path: 文件路径
        
        Returns:
            是否能扫描
        """
        pass
    
    @abc.abstractmethod
    def scan_file(self, file_path: str) -> dict[str, Any]:
        """扫描文件
        
        Args:
            file_path: 文件路径
        
        Returns:
            扫描结果字典
        """
        pass


class AnalyzerPlugin(PluginInterface):
    """分析器插件基类
    
    用于扩展代码分析功能。
    """
    
    @abc.abstractmethod
    def analyze(self, file_path: str, content: str) -> dict[str, Any]:
        """分析代码
        
        Args:
            file_path: 文件路径
            content: 文件内容
        
        Returns:
            分析结果
        """
        pass


class LLMProviderPlugin(PluginInterface):
    """LLM提供商插件基类
    
    用于集成不同的LLM服务。
    """
    
    @abc.abstractmethod
    def get_provider_name(self) -> str:
        """获取提供商名称"""
        pass
    
    @abc.abstractmethod
    def is_available(self) -> bool:
        """检查是否可用（如API密钥是否配置）"""
        pass
    
    @abc.abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """生成文本
        
        Args:
            prompt: 提示词
            **kwargs: 额外参数
        
        Returns:
            生成的文本
        """
        pass
    
    @abc.abstractmethod
    def get_model_list(self) -> list[dict]:
        """获取可用模型列表
        
        Returns:
            模型信息列表
        """
        pass


class ExporterPlugin(PluginInterface):
    """导出器插件基类
    
    用于支持不同的导出格式。
    """
    
    @abc.abstractmethod
    def get_format_name(self) -> str:
        """获取格式名称"""
        pass
    
    @abc.abstractmethod
    def get_file_extension(self) -> str:
        """获取文件扩展名"""
        pass
    
    @abc.abstractmethod
    def export(self, projmap_data: dict, output_path: str) -> bool:
        """导出数据
        
        Args:
            projmap_data: .projmap 数据
            output_path: 输出路径
        
        Returns:
            是否导出成功
        """
        pass


class CommandPlugin(PluginInterface):
    """命令插件基类
    
    用于扩展CLI命令。
    """
    
    @abc.abstractmethod
    def get_commands(self) -> list[dict]:
        """获取命令列表
        
        Returns:
            命令定义列表，每个命令包含：
            - name: 命令名
            - description: 描述
            - arguments: 参数列表
            - options: 选项列表
            - handler: 处理函数
        """
        pass


# ========== 插件管理器 ==========

@dataclass
class PluginInfo:
    """插件信息"""
    metadata: PluginMetadata
    instance: Optional[PluginInterface] = None
    state: PluginState = PluginState.REGISTERED
    error_message: str = ""
    load_time: Optional[datetime] = None
    enable_time: Optional[datetime] = None
    module_path: str = ""


class PluginManager:
    """插件管理器
    
    负责插件的加载、启用、禁用、卸载。
    """
    
    def __init__(self, plugin_dirs: Optional[list[str]] = None):
        """
        Args:
            plugin_dirs: 插件目录列表
        """
        self._plugin_dirs = plugin_dirs or [
            os.path.expanduser("~/.projmap/plugins"),
            ".projmap/plugins",
        ]
        self._plugins: dict[str, PluginInfo] = {}
        self._hooks: dict[str, list[tuple[str, Callable]]] = {}
        self._event_handlers: dict[str, list[Callable]] = {}
        self._logger = logging.getLogger("projmap.plugin_manager")
        
        # 内置插件类型注册
        self._plugin_types: dict[str, type[PluginInterface]] = {
            "scanner": ScannerPlugin,
            "analyzer": AnalyzerPlugin,
            "llm_provider": LLMProviderPlugin,
            "exporter": ExporterPlugin,
            "command": CommandPlugin,
        }
    
    def register_plugin_type(self, type_name: str, base_class: type[PluginInterface]):
        """注册插件类型"""
        self._plugin_types[type_name] = base_class
        self._logger.debug(f"注册插件类型: {type_name}")
    
    def discover_plugins(self) -> list[PluginMetadata]:
        """发现所有可用插件
        
        Returns:
            插件元数据列表
        """
        discovered = []
        
        for plugin_dir in self._plugin_dirs:
            if not os.path.exists(plugin_dir):
                continue
            
            for item in os.listdir(plugin_dir):
                item_path = os.path.join(plugin_dir, item)
                
                # 检查插件目录
                if os.path.isdir(item_path):
                    manifest_path = os.path.join(item_path, "plugin.json")
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            metadata = PluginMetadata.from_dict(data)
                            discovered.append(metadata)
                            self._logger.debug(f"发现插件: {metadata.name}")
                        except Exception as e:
                            self._logger.warning(f"加载插件清单失败 {manifest_path}: {e}")
                
                # 检查单文件插件
                elif item.endswith("_plugin.py"):
                    try:
                        metadata = self._load_single_file_metadata(item_path)
                        if metadata:
                            discovered.append(metadata)
                    except Exception as e:
                        self._logger.warning(f"加载单文件插件失败 {item_path}: {e}")
        
        # 按优先级排序
        discovered.sort(key=lambda m: self._get_plugin_priority(m.name))
        
        return discovered
    
    def _load_single_file_metadata(self, file_path: str) -> Optional[PluginMetadata]:
        """从单文件插件加载元数据"""
        spec = importlib.util.spec_from_file_location("plugin", file_path)
        if not spec or not spec.loader:
            return None
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, "METADATA"):
            return module.METADATA
        
        return None
    
    def _get_plugin_priority(self, plugin_name: str) -> int:
        """获取插件优先级值"""
        if plugin_name in self._plugins:
            plugin_class = self._plugins[plugin_name].instance.__class__
            return plugin_class.PRIORITY.value
        return PluginPriority.NORMAL.value
    
    def load_plugin(self, plugin_name: str, config: dict = None) -> bool:
        """加载插件
        
        Args:
            plugin_name: 插件名称或路径
            config: 插件配置
        
        Returns:
            是否加载成功
        """
        if plugin_name in self._plugins:
            self._logger.warning(f"插件 {plugin_name} 已加载")
            return False
        
        try:
            # 查找插件
            plugin_path = self._find_plugin_path(plugin_name)
            if not plugin_path:
                raise ValueError(f"找不到插件: {plugin_name}")
            
            # 加载插件模块
            plugin_class = self._load_plugin_class(plugin_path)
            if not plugin_class:
                raise ValueError(f"无法加载插件类: {plugin_name}")
            
            # 创建实例
            instance = plugin_class()
            
            # 创建插件信息
            info = PluginInfo(
                metadata=plugin_class.METADATA,
                instance=instance,
                state=PluginState.LOADING,
                module_path=plugin_path,
            )
            self._plugins[plugin_name] = info
            
            # 调用加载回调
            if not instance.on_load(self, config or {}):
                raise RuntimeError("插件 on_load 返回 False")
            
            info.state = PluginState.LOADED
            info.load_time = datetime.now()
            
            self._logger.info(f"插件 {plugin_name} 加载成功")
            return True
            
        except Exception as e:
            self._logger.error(f"加载插件 {plugin_name} 失败: {e}")
            if plugin_name in self._plugins:
                self._plugins[plugin_name].state = PluginState.ERROR
                self._plugins[plugin_name].error_message = str(e)
            return False
    
    def _find_plugin_path(self, plugin_name: str) -> str:
        """查找插件路径"""
        # 如果已经是完整路径
        if os.path.exists(plugin_name):
            return plugin_name
        
        # 在插件目录中查找
        for plugin_dir in self._plugin_dirs:
            # 检查目录插件
            dir_path = os.path.join(plugin_dir, plugin_name)
            if os.path.isdir(dir_path):
                manifest_path = os.path.join(dir_path, "plugin.json")
                if os.path.exists(manifest_path):
                    return dir_path
            
            # 检查单文件插件
            file_path = os.path.join(plugin_dir, f"{plugin_name}_plugin.py")
            if os.path.exists(file_path):
                return file_path
        
        return ""
    
    def _load_plugin_class(self, plugin_path: str) -> Optional[type[PluginInterface]]:
        """加载插件类"""
        if os.path.isdir(plugin_path):
            # 目录插件
            init_path = os.path.join(plugin_path, "__init__.py")
            if os.path.exists(init_path):
                module_name = f"projmap_plugin_{os.path.basename(plugin_path)}"
                spec = importlib.util.spec_from_file_location(module_name, init_path)
            else:
                return None
        else:
            # 单文件插件
            module_name = f"projmap_plugin_{os.path.basename(plugin_path)[:-3]}"
            spec = importlib.util.spec_from_file_location(module_name, plugin_path)
        
        if not spec or not spec.loader:
            return None
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        # 查找插件类
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and 
                issubclass(obj, PluginInterface) and 
                obj is not PluginInterface and
                hasattr(obj, "METADATA")):
                return obj
        
        return None
    
    def enable_plugin(self, plugin_name: str) -> bool:
        """启用插件"""
        if plugin_name not in self._plugins:
            self._logger.error(f"插件 {plugin_name} 未加载")
            return False
        
        info = self._plugins[plugin_name]
        if info.state == PluginState.ENABLED:
            return True
        
        try:
            info.state = PluginState.ENABLING
            
            # 检查依赖
            for dep in info.metadata.dependencies:
                if dep not in self._plugins:
                    self._logger.error(f"插件 {plugin_name} 依赖 {dep} 未加载")
                    info.state = PluginState.ERROR
                    return False
                
                if self._plugins[dep].state != PluginState.ENABLED:
                    if not self.enable_plugin(dep):
                        self._logger.error(f"启用依赖 {dep} 失败")
                        info.state = PluginState.ERROR
                        return False
            
            # 启用插件
            if info.instance and info.instance.on_enable():
                info.state = PluginState.ENABLED
                info.enable_time = datetime.now()
                
                # 注册钩子
                self._register_plugin_hooks(info)
                
                self._logger.info(f"插件 {plugin_name} 启用成功")
                return True
            else:
                info.state = PluginState.ERROR
                return False
                
        except Exception as e:
            self._logger.error(f"启用插件 {plugin_name} 失败: {e}")
            info.state = PluginState.ERROR
            info.error_message = str(e)
            return False
    
    def _register_plugin_hooks(self, info: PluginInfo):
        """注册插件钩子"""
        for hook_name in info.metadata.hooks:
            if hook_name not in self._hooks:
                self._hooks[hook_name] = []
            
            # 查找处理方法
            handler_name = f"on_{hook_name}"
            if hasattr(info.instance, handler_name):
                handler = getattr(info.instance, handler_name)
                self._hooks[hook_name].append((info.metadata.name, handler))
                self._logger.debug(f"注册钩子 {hook_name} -> {info.metadata.name}")
    
    def disable_plugin(self, plugin_name: str) -> bool:
        """禁用插件"""
        if plugin_name not in self._plugins:
            return False
        
        info = self._plugins[plugin_name]
        if info.state != PluginState.ENABLED:
            return True
        
        try:
            info.state = PluginState.DISABLING
            
            # 注销钩子
            for hook_name in info.metadata.hooks:
                if hook_name in self._hooks:
                    self._hooks[hook_name] = [
                        (name, handler) for name, handler in self._hooks[hook_name]
                        if name != plugin_name
                    ]
            
            # 调用禁用回调
            if info.instance:
                info.instance.on_disable()
            
            info.state = PluginState.DISABLED
            self._logger.info(f"插件 {plugin_name} 已禁用")
            return True
            
        except Exception as e:
            self._logger.error(f"禁用插件 {plugin_name} 失败: {e}")
            return False
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """卸载插件"""
        if plugin_name not in self._plugins:
            return False
        
        # 先禁用
        self.disable_plugin(plugin_name)
        
        info = self._plugins[plugin_name]
        
        try:
            info.state = PluginState.UNLOADING
            
            if info.instance:
                info.instance.on_unload()
            
            del self._plugins[plugin_name]
            self._logger.info(f"插件 {plugin_name} 已卸载")
            return True
            
        except Exception as e:
            self._logger.error(f"卸载插件 {plugin_name} 失败: {e}")
            return False
    
    def get_plugin(self, plugin_name: str) -> Optional[PluginInterface]:
        """获取插件实例"""
        if plugin_name in self._plugins:
            return self._plugins[plugin_name].instance
        return None
    
    def get_enabled_plugins(self) -> list[PluginInterface]:
        """获取所有已启用的插件"""
        return [
            info.instance for info in self._plugins.values()
            if info.state == PluginState.ENABLED and info.instance
        ]
    
    def get_plugins_by_type(self, plugin_type: str) -> list[PluginInterface]:
        """获取指定类型的插件"""
        if plugin_type not in self._plugin_types:
            return []
        
        base_class = self._plugin_types[plugin_type]
        return [
            info.instance for info in self._plugins.values()
            if (info.state == PluginState.ENABLED and 
                info.instance and 
                isinstance(info.instance, base_class))
        ]
    
    # ========== 事件和钩子系统 ==========
    
    def register_event_handler(self, event_name: str, handler: Callable):
        """注册事件处理器"""
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(handler)
    
    def emit_event(self, event_name: str, data: Any = None, source: str = ""):
        """发送事件"""
        if event_name in self._event_handlers:
            for handler in self._event_handlers[event_name]:
                try:
                    handler(data, source)
                except Exception as e:
                    self._logger.error(f"事件处理器出错: {e}")
    
    def call_hook(self, hook_name: str, *args, **kwargs) -> list[Any]:
        """调用钩子
        
        所有注册了该钩子的插件都会收到调用。
        
        Returns:
            各插件返回结果的列表
        """
        results = []
        
        if hook_name in self._hooks:
            for plugin_name, handler in self._hooks[hook_name]:
                try:
                    result = handler(*args, **kwargs)
                    results.append(result)
                except Exception as e:
                    self._logger.error(f"钩子处理器 {plugin_name}.{hook_name} 出错: {e}")
        
        return results
    
    # ========== 便捷方法 ==========
    
    def load_all(self, configs: Optional[dict] = None):
        """加载所有发现的插件"""
        discovered = self.discover_plugins()
        
        for metadata in discovered:
            config = (configs or {}).get(metadata.name, {})
            self.load_plugin(metadata.name, config)
    
    def enable_all(self):
        """启用所有已加载的插件"""
        for plugin_name in list(self._plugins.keys()):
            self.enable_plugin(plugin_name)
    
    def get_status(self) -> dict:
        """获取插件系统状态"""
        return {
            "total": len(self._plugins),
            "enabled": sum(1 for p in self._plugins.values() if p.state == PluginState.ENABLED),
            "disabled": sum(1 for p in self._plugins.values() if p.state == PluginState.DISABLED),
            "error": sum(1 for p in self._plugins.values() if p.state == PluginState.ERROR),
            "plugins": {
                name: {
                    "version": info.metadata.version,
                    "state": info.state.name,
                    "author": info.metadata.author,
                }
                for name, info in self._plugins.items()
            },
        }


# ========== 全局插件管理器 ==========

_global_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """获取全局插件管理器"""
    global _global_plugin_manager
    if _global_plugin_manager is None:
        _global_plugin_manager = PluginManager()
    return _global_plugin_manager


def set_plugin_manager(manager: PluginManager):
    """设置全局插件管理器"""
    global _global_plugin_manager
    _global_plugin_manager = manager
