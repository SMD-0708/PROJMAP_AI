"""异步工具模块

提供异步执行和并发处理功能。
"""

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import Any, Callable, Coroutine, TypeVar, Optional
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AsyncExecutor:
    """异步执行器
    
    提供线程池和进程池执行功能。
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        use_processes: bool = False,
    ):
        """
        Args:
            max_workers: 最大工作线程/进程数
            use_processes: 是否使用进程池（适用于CPU密集型任务）
        """
        self._max_workers = max_workers
        self._use_processes = use_processes
        self._executor: Optional[ThreadPoolExecutor | ProcessPoolExecutor] = None
    
    def _get_executor(self):
        """获取或创建执行器"""
        if self._executor is None:
            if self._use_processes:
                self._executor = ProcessPoolExecutor(max_workers=self._max_workers)
            else:
                self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
        return self._executor
    
    async def run_in_executor(
        self,
        func: Callable[..., T],
        *args,
        **kwargs,
    ) -> T:
        """在 executor 中运行函数"""
        loop = asyncio.get_event_loop()
        executor = self._get_executor()
        
        if kwargs:
            func = functools.partial(func, **kwargs)
        
        return await loop.run_in_executor(executor, func, *args)
    
    async def map(
        self,
        func: Callable[[Any], T],
        items: list[Any],
    ) -> list[T]:
        """并发执行函数到多个项目"""
        tasks = [self.run_in_executor(func, item) for item in items]
        return await asyncio.gather(*tasks)
    
    def shutdown(self):
        """关闭执行器"""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


async def gather_with_limit(
    *coroutines: Coroutine,
    limit: int = 10,
) -> list[Any]:
    """限制并发数量的 gather
    
    Args:
        *coroutines: 协程列表
        limit: 最大并发数
    
    Returns:
        执行结果列表
    """
    semaphore = asyncio.Semaphore(limit)
    
    async def sem_coro(coro):
        async with semaphore:
            return await coro
    
    return await asyncio.gather(*[sem_coro(c) for c in coroutines])


def async_to_sync(coro: Coroutine) -> Any:
    """将协程转换为同步调用
    
    Args:
        coro: 协程对象
    
    Returns:
        协程执行结果
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环已在运行，创建新循环
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
                asyncio.set_event_loop(loop)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # 没有事件循环
        return asyncio.run(coro)


def make_async(func: Callable[..., T]) -> Callable[..., Coroutine[Any, Any, T]]:
    """将同步函数转换为异步函数的装饰器
    
    Args:
        func: 同步函数
    
    Returns:
        异步函数
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
    
    return wrapper


class AsyncBatchProcessor:
    """异步批处理器
    
    用于批量处理大量数据，支持并发和进度回调。
    """
    
    def __init__(
        self,
        batch_size: int = 100,
        max_concurrency: int = 10,
    ):
        self.batch_size = batch_size
        self.max_concurrency = max_concurrency
    
    async def process(
        self,
        items: list[Any],
        processor: Callable[[Any], Coroutine],
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[tuple[Any, Any]]:
        """批量处理项目
        
        Args:
            items: 待处理项目列表
            processor: 处理函数（异步）
            on_progress: 进度回调函数(current, total)
        
        Returns:
            (item, result) 列表
        """
        results = []
        total = len(items)
        processed = 0
        
        # 分批处理
        for i in range(0, total, self.batch_size):
            batch = items[i:i + self.batch_size]
            
            # 并发处理批次
            semaphore = asyncio.Semaphore(self.max_concurrency)
            
            async def process_with_sem(item):
                async with semaphore:
                    try:
                        result = await processor(item)
                        return (item, result, None)
                    except Exception as e:
                        logger.error(f"处理项目失败: {e}")
                        return (item, None, e)
            
            batch_results = await asyncio.gather(*[
                process_with_sem(item) for item in batch
            ])
            
            results.extend(batch_results)
            processed += len(batch)
            
            if on_progress:
                on_progress(processed, total)
            
            logger.debug(f"批处理进度: {processed}/{total}")
        
        return results


# 便捷函数
async def parallel_map(
    func: Callable[[Any], T],
    items: list[Any],
    max_workers: int = 4,
) -> list[T]:
    """并行 map 函数
    
    Args:
        func: 处理函数
        items: 输入列表
        max_workers: 最大并发数
    
    Returns:
        结果列表
    """
    with AsyncExecutor(max_workers=max_workers) as executor:
        return await executor.map(func, items)


def run_async(coro: Coroutine) -> Any:
    """运行异步代码的便捷函数"""
    return async_to_sync(coro)
