"""缓存模块

提供简单的内存缓存和文件缓存功能。
"""

import functools
import hashlib
import json
import os
import pickle
import time
from typing import Any, Callable, Optional


class MemoryCache:
    """简单的内存缓存"""
    
    def __init__(self, max_size: int = 128, ttl: Optional[int] = None):
        """
        Args:
            max_size: 最大缓存条目数
            ttl: 缓存过期时间（秒），None表示永不过期
        """
        self._cache: dict[str, tuple[Any, Optional[float]]] = {}
        self._max_size = max_size
        self._ttl = ttl
    
    def _make_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        key_data = {
            "args": args,
            "kwargs": kwargs,
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key not in self._cache:
            return None
        
        value, expire_time = self._cache[key]
        
        # 检查是否过期
        if expire_time is not None and time.time() > expire_time:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存值"""
        # 如果缓存已满，删除最旧的条目
        if len(self._cache) >= self._max_size and key not in self._cache:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        
        # 计算过期时间
        expire_time = None
        if ttl is not None:
            expire_time = time.time() + ttl
        elif self._ttl is not None:
            expire_time = time.time() + self._ttl
        
        self._cache[key] = (value, expire_time)
    
    def delete(self, key: str):
        """删除缓存"""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
    
    def cached(self, ttl: Optional[int] = None):
        """装饰器：缓存函数结果"""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # 生成缓存键
                key_data = {
                    "func": func.__name__,
                    "args": args[1:] if args else args,  # 跳过self
                    "kwargs": kwargs,
                }
                key_str = json.dumps(key_data, sort_keys=True, default=str)
                key = hashlib.md5(key_str.encode()).hexdigest()
                
                # 尝试从缓存获取
                cached_value = self.get(key)
                if cached_value is not None:
                    return cached_value
                
                # 执行函数
                result = func(*args, **kwargs)
                
                # 存入缓存
                self.set(key, result, ttl)
                
                return result
            
            # 添加清除缓存的方法
            wrapper.cache_clear = lambda: self.clear()
            
            return wrapper
        return decorator


class FileCache:
    """文件缓存"""
    
    def __init__(self, cache_dir: str, ttl: Optional[int] = 3600):
        """
        Args:
            cache_dir: 缓存目录
            ttl: 默认过期时间（秒）
        """
        self._cache_dir = cache_dir
        self._ttl = ttl
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_file(self, key: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self._cache_dir, f"{key}.cache")
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        cache_file = self._get_cache_file(key)
        
        if not os.path.exists(cache_file):
            return None
        
        try:
            with open(cache_file, "rb") as f:
                data = pickle.load(f)
            
            # 检查是否过期
            if self._ttl is not None:
                mtime = os.path.getmtime(cache_file)
                if time.time() - mtime > self._ttl:
                    os.remove(cache_file)
                    return None
            
            return data
        except Exception:
            return None
    
    def set(self, key: str, value: Any):
        """设置缓存值"""
        cache_file = self._get_cache_file(key)
        
        try:
            with open(cache_file, "wb") as f:
                pickle.dump(value, f)
        except Exception:
            pass
    
    def delete(self, key: str):
        """删除缓存"""
        cache_file = self._get_cache_file(key)
        if os.path.exists(cache_file):
            os.remove(cache_file)
    
    def clear(self):
        """清空缓存"""
        for filename in os.listdir(self._cache_dir):
            if filename.endswith(".cache"):
                try:
                    os.remove(os.path.join(self._cache_dir, filename))
                except Exception:
                    pass


# 全局缓存实例
_global_memory_cache = MemoryCache()


def get_global_cache() -> MemoryCache:
    """获取全局内存缓存"""
    return _global_memory_cache


def cached(ttl: Optional[int] = None, cache: Optional[MemoryCache] = None):
    """缓存装饰器
    
    Args:
        ttl: 缓存过期时间（秒）
        cache: 使用的缓存实例，默认使用全局缓存
    """
    target_cache = cache or _global_memory_cache
    return target_cache.cached(ttl)
