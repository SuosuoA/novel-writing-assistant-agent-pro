"""
AI调用包装器 - 自动集成WAL协议

V1.0版本
创建日期：2026-03-28

功能：
- 自动在AI调用前执行WAL写入
- 自动在AI调用后标记完成/失败状态
- 统一AI调用入口
- 无侵入式集成（通过包装器模式）

设计参考：
- OpenClaw mem9 WAL协议
- 升级方案10.1

使用示例：
    from core.ai_call_wrapper import AICallWrapper
    
    wrapper = AICallWrapper()
    
    # 自动WAL写入 + AI调用
    result = wrapper.call(
        prompt="生成第3章",
        context={
            "operation": "生成章节",
            "chapter_number": 3,
            "outline": "..."
        }
    )
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .wal_manager import get_wal_manager, WALManager
from .session_state import get_session_state_manager, SessionStateManager
from .config_service import get_config_service

logger = logging.getLogger(__name__)


class AICallWrapper:
    """
    AI调用包装器 - 自动集成WAL协议
    
    核心功能：
    1. 调用前：自动写入WAL状态（同步阻塞，确保落盘）
    2. 调用中：执行AI生成
    3. 调用后：自动标记完成/失败状态
    
    线程安全：
    - WAL写入使用RLock保护
    - 状态更新原子化
    """
    
    def __init__(self, workspace: Optional[Path] = None):
        """
        初始化AI调用包装器
        
        Args:
            workspace: 工作区路径（可选，默认使用项目根目录）
        """
        self.workspace = workspace or Path.cwd()
        
        # 获取管理器实例
        self.wal_manager = get_wal_manager(self.workspace)
        self.session_manager = get_session_state_manager(self.workspace)
        
        # 读取配置
        self.config = get_config_service()
        self._wal_enabled = self._check_wal_enabled()
        
        logger.info(f"[AICallWrapper] 初始化完成，WAL自动保存: {self._wal_enabled}")
    
    def _check_wal_enabled(self) -> bool:
        """检查WAL自动保存是否启用"""
        try:
            # 直接读取config.yaml文件（Pydantic模型可能没有memory字段）
            import yaml
            config_path = self.workspace / "config.yaml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_dict = yaml.safe_load(f)
                memory_config = config_dict.get("memory", {})
                return memory_config.get("wal_auto_save", False)
            return False
        except Exception as e:
            logger.warning(f"[AICallWrapper] 读取WAL配置失败: {e}")
            return False
    
    def call(
        self,
        prompt: str,
        context: Dict[str, Any],
        generator_func: Callable,
        operation: str = "",
        task_id: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        包装AI调用，自动执行WAL协议
        
        Args:
            prompt: AI提示词
            context: 调用上下文（用于WAL记录）
            generator_func: AI生成函数
            operation: 操作描述
            task_id: 任务ID（可选）
            **kwargs: 传递给generator_func的其他参数
            
        Returns:
            Any: AI生成结果
            
        Example:
            def my_generator(prompt, **kwargs):
                # 调用AI API
                return ai_api.generate(prompt)
            
            result = wrapper.call(
                prompt="生成第3章",
                context={"chapter_number": 3},
                generator_func=my_generator,
                operation="生成章节"
            )
        """
        # 1. WAL写入（如果启用）
        if self._wal_enabled:
            try:
                success = self.wal_manager.write_before_ai_call(
                    context=context,
                    operation=operation or context.get("operation", ""),
                    task_id=task_id or context.get("task_id")
                )
                
                if not success:
                    logger.error("[AICallWrapper] WAL写入失败，但继续执行AI调用")
            except Exception as e:
                logger.error(f"[AICallWrapper] WAL写入异常: {e}")
        
        # 2. 更新SessionState
        try:
            self.session_manager.write_before_ai_call({
                "task": operation or context.get("operation", ""),
                "file": context.get("file", ""),
                "operation": operation or context.get("operation", ""),
                "pending": context
            })
        except Exception as e:
            logger.warning(f"[AICallWrapper] SessionState更新失败: {e}")
        
        # 3. 执行AI调用
        try:
            result = generator_func(prompt, **kwargs)
            
            # 4. 标记成功
            if self._wal_enabled:
                try:
                    self.wal_manager.mark_completed(
                        result={"success": True} if result else None
                    )
                except Exception as e:
                    logger.warning(f"[AICallWrapper] WAL标记完成失败: {e}")
            
            return result
            
        except Exception as e:
            # 5. 标记失败
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"[AICallWrapper] AI调用失败: {error_msg}")
            
            if self._wal_enabled:
                try:
                    self.wal_manager.mark_failed(error_msg)
                except Exception as we:
                    logger.warning(f"[AICallWrapper] WAL标记失败异常: {we}")
            
            # 记录异常状态
            try:
                self.session_manager.set_error(
                    error_type=type(e).__name__,
                    error_message=str(e),
                    recovery_hint="请检查API配置或网络连接"
                )
            except Exception as se:
                logger.warning(f"[AICallWrapper] SessionState错误记录失败: {se}")
            
            # 重新抛出异常
            raise
    
    async def call_async(
        self,
        prompt: str,
        context: Dict[str, Any],
        generator_func: Callable,
        operation: str = "",
        task_id: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        异步包装AI调用，自动执行WAL协议
        
        Args:
            同call()
            
        Returns:
            Any: AI生成结果
        """
        # 1. WAL写入
        if self._wal_enabled:
            try:
                self.wal_manager.write_before_ai_call(
                    context=context,
                    operation=operation or context.get("operation", ""),
                    task_id=task_id or context.get("task_id")
                )
            except Exception as e:
                logger.error(f"[AICallWrapper] WAL写入异常: {e}")
        
        # 2. 更新SessionState
        try:
            self.session_manager.write_before_ai_call({
                "task": operation or context.get("operation", ""),
                "file": context.get("file", ""),
                "operation": operation or context.get("operation", ""),
                "pending": context
            })
        except Exception as e:
            logger.warning(f"[AICallWrapper] SessionState更新失败: {e}")
        
        # 3. 执行异步AI调用
        try:
            result = await generator_func(prompt, **kwargs)
            
            # 4. 标记成功
            if self._wal_enabled:
                try:
                    self.wal_manager.mark_completed(
                        result={"success": True} if result else None
                    )
                except Exception as e:
                    logger.warning(f"[AICallWrapper] WAL标记完成失败: {e}")
            
            return result
            
        except Exception as e:
            # 5. 标记失败
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"[AICallWrapper] 异步AI调用失败: {error_msg}")
            
            if self._wal_enabled:
                try:
                    self.wal_manager.mark_failed(error_msg)
                except Exception as we:
                    logger.warning(f"[AICallWrapper] WAL标记失败异常: {we}")
            
            # 记录异常状态
            try:
                self.session_manager.set_error(
                    error_type=type(e).__name__,
                    error_message=str(e),
                    recovery_hint="请检查API配置或网络连接"
                )
            except Exception as se:
                logger.warning(f"[AICallWrapper] SessionState错误记录失败: {se}")
            
            raise


# ============================================================================
# 全局实例（单例模式）
# ============================================================================

_ai_call_wrapper_instance: Optional[AICallWrapper] = None


def get_ai_call_wrapper(workspace: Optional[Path] = None) -> AICallWrapper:
    """
    获取AI调用包装器单例
    
    Args:
        workspace: 工作区路径（可选）
        
    Returns:
        AICallWrapper: 包装器实例
    """
    global _ai_call_wrapper_instance
    
    if _ai_call_wrapper_instance is None:
        _ai_call_wrapper_instance = AICallWrapper(workspace)
    
    return _ai_call_wrapper_instance
