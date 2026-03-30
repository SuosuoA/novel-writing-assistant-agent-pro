"""
小说生成Agent - NovelGenerationAgent

调用 novel-generator-v3 插件，实现 Generator 能力

功能:
- 整合上下文构建
- 迭代生成章节内容
- 多维度评分验证
- 循环优化直到达标
- 异步执行支持（解决卡顿问题）

核心流程（强制保护）:
1. 整理打包请求内容（强制附加【本章完】要求）
2. 向大模型发送请求
3. 接受返回文章
4. 多维度评分
5. 分数<0.8 → 发送评分+修改建议 → 再次生成
6. 评分≥0.8且有【本章完】→ 输出保存

创建日期: 2026-03-23
更新日期: 2026-03-28
"""

import logging
import asyncio
from typing import Any, Dict, Optional, Callable

import sys
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agents.core.base_agent import (
    BaseAgent,
    AgentMetadata,
    AgentContext,
    AgentResult,
    AgentState,
    AgentCapability,
)


class NovelGenerationAgent(BaseAgent):
    """小说生成Agent - 调用 novel-generator-v3 插件
    
    实现 Generator 能力:
    - 构建优化的提示词
    - 执行迭代生成流程
    - 多维度评分验证
    - 循环优化直到达标
    - 上下文记忆管理（保持前5章）
    
    核心流程（强制保护）:
    1. 整理打包请求内容（强制附加【本章完】要求）
    2. 向大模型发送请求
    3. 接受返回文章
    4. 多维度评分
    5. 分数<0.8 → 发送评分+修改建议 → 再次生成
    6. 评分≥0.8且有【本章完】→ 输出保存
    
    被MasterAgent调度，用于生成小说章节内容。
    """
    
    # 类常量
    AGENT_TYPE = "novel_generation"
    PLUGIN_ID = "novel-generator-v3"
    
    def __init__(self):
        """初始化小说生成Agent"""
        metadata = AgentMetadata(
            agent_type=self.AGENT_TYPE,
            name="小说生成Agent",
            description="调用 novel-generator-v3 插件进行迭代优化的章节生成",
            version="1.0.0",
            capabilities=[AgentCapability.GENERATION],
            dependencies=["context-builder-v1", "iterative-generator-v2", "quality-validator-v1"],
            tags=["novel", "generation", "iteration", "optimization"],
            author="项目组",
            priority=120,  # 高优先级
            timeout_seconds=300,  # 生成任务可能需要较长时间
            max_retries=0,  # 插件内部已有重试机制
            max_concurrent_tasks=1,
        )
        super().__init__(self.AGENT_TYPE, metadata)
        
        # 插件引用（延迟初始化）
        self._plugin = None
        self._api_client = None
        self._logger = logging.getLogger(f"agent.{self.AGENT_TYPE}")
    
    def initialize(self) -> bool:
        """初始化Agent
        
        Returns:
            是否初始化成功
        """
        try:
            self._set_state(AgentState.LOADED)
            
            # P2-2修复：验证依赖插件是否可用
            missing_deps = self._check_dependencies()
            if missing_deps:
                self._logger.warning(
                    f"[{self.AGENT_TYPE}] 依赖插件不可用: {missing_deps}，"
                    "部分功能可能受限"
                )
            
            # 尝试从服务定位器获取插件
            if self._service_locator:
                try:
                    self._plugin = self._service_locator.try_get(self.PLUGIN_ID)
                    if self._plugin:
                        self._logger.info(f"[{self.AGENT_TYPE}] 从服务定位器获取插件成功: {self.PLUGIN_ID}")
                except Exception as e:
                    self._logger.warning(f"[{self.AGENT_TYPE}] 服务定位器获取插件失败: {e}")
            
            # 如果没有获取到，尝试动态导入
            if not self._plugin:
                try:
                    from plugins.novel_generator_v3.plugin import NovelGeneratorPlugin
                    self._plugin = NovelGeneratorPlugin()
                    self._logger.info(f"[{self.AGENT_TYPE}] 创建本地插件实例: {self.PLUGIN_ID}")
                except ImportError as e:
                    self._logger.error(f"[{self.AGENT_TYPE}] 无法导入插件: {e}")
                    self._set_state(AgentState.ERROR)
                    self._set_error(f"插件导入失败: {e}")
                    return False
            
            self._initialized = True
            self._set_state(AgentState.ACTIVE)
            self._logger.info(f"[{self.AGENT_TYPE}] 初始化完成")
            return True
            
        except Exception as e:
            self._set_state(AgentState.ERROR)
            self._set_error(str(e))
            self._logger.error(f"[{self.AGENT_TYPE}] 初始化失败: {e}", exc_info=True)
            return False
    
    def _check_dependencies(self) -> list:
        """检查依赖插件是否可用
        
        P2-2修复：验证dependencies字段定义的依赖插件是否已加载
        
        Returns:
            不可用的依赖插件列表
        """
        missing = []
        dependencies = self._metadata.dependencies or []
        
        for dep_id in dependencies:
            try:
                if self._service_locator:
                    dep = self._service_locator.try_get(dep_id)
                    if not dep:
                        missing.append(dep_id)
                else:
                    missing.append(dep_id)
            except Exception:
                missing.append(dep_id)
        
        return missing
    
    def set_api_client(self, api_client: Any):
        """设置API客户端
        
        Args:
            api_client: API客户端实例
        """
        self._api_client = api_client
        if self._plugin and hasattr(self._plugin, 'set_api_client'):
            self._plugin.set_api_client(api_client)
        self._logger.info(f"[{self.AGENT_TYPE}] API客户端已设置")
    
    def set_config(
        self,
        model_name: str = "deepseek-chat",
        quality_threshold: float = 0.8,
        max_iterations: int = 5,
        target_word_count: int = 3500
    ):
        """设置生成配置
        
        Args:
            model_name: 模型名称
            quality_threshold: 质量阈值
            max_iterations: 最大迭代次数
            target_word_count: 目标字数
        """
        if self._plugin and hasattr(self._plugin, 'set_config'):
            self._plugin.set_config(
                model_name=model_name,
                quality_threshold=quality_threshold,
                max_iterations=max_iterations,
                target_word_count=target_word_count
            )
        self._logger.info(f"[{self.AGENT_TYPE}] 配置已更新 - 模型: {model_name}, 阈值: {quality_threshold}, 迭代: {max_iterations}, 字数: {target_word_count}")
    
    def execute(
        self,
        task_id: str,
        payload: Dict[str, Any],
        context: AgentContext = None
    ) -> AgentResult:
        """执行小说生成任务
        
        Args:
            task_id: 任务ID
            payload: 任务载荷
                - chapter_title: 章节标题
                - chapter_outline: 章节大纲
                - world_view: 世界观设定
                - style: 写作风格
                - characters: 人物列表
                - target_word_count: 目标字数
                - style_profile: 风格档案（可选）
                - use_context_memory: 是否使用上下文记忆（默认True）
            context: 执行上下文
            
        Returns:
            AgentResult 执行结果
        """
        if not self._initialized or not self._plugin:
            return AgentResult.failure_result(
                task_id=task_id,
                agent_type=self.AGENT_TYPE,
                error="Agent未初始化或插件不可用",
                error_type="InitializationError"
            )
        
        try:
            self._logger.info(f"[{self.AGENT_TYPE}] 开始执行任务: {task_id}")
            self._status.current_task_id = task_id
            
            # 提取参数
            chapter_title = payload.get("chapter_title", "")
            chapter_outline = payload.get("chapter_outline", "")
            world_view = payload.get("world_view", "")
            style = payload.get("style", "")
            characters = payload.get("characters", [])
            target_word_count = payload.get("target_word_count", 3500)
            style_profile = payload.get("style_profile")
            use_context_memory = payload.get("use_context_memory", True)
            
            # V2.12新增：提取知识库和写作技巧参数
            knowledge_categories = payload.get("knowledge_categories", [])
            knowledge_domains = payload.get("knowledge_domains", [])
            writing_techniques = payload.get("writing_techniques", [])
            
            # 调用插件进行生成
            final_content, stats = self._plugin.generate_chapter(
                chapter_title=chapter_title,
                chapter_outline=chapter_outline,
                world_view=world_view,
                style=style,
                characters=characters,
                target_word_count=target_word_count,
                style_profile=style_profile,
                use_context_memory=use_context_memory,
                knowledge_categories=knowledge_categories,  # V2.12新增
                knowledge_domains=knowledge_domains,        # V2.12新增
                writing_techniques=writing_techniques,      # V2.12新增
            )
            
            # 检查生成结果
            if final_content and not final_content.startswith("【生成器未初始化】"):
                agent_result = AgentResult.success_result(
                    task_id=task_id,
                    agent_type=self.AGENT_TYPE,
                    data={
                        "content": final_content,
                        "word_count": len(final_content),
                        "stats": stats,
                    },
                    metadata={
                        "chapter_title": chapter_title,
                        "word_count": len(final_content),
                        "target_word_count": target_word_count,
                        "final_score": stats.get("final_score", 0.0),
                        "total_iterations": stats.get("total_iterations", 0),
                        "has_chapter_end": "【本章完】" in final_content,
                    }
                )
                self._increment_completed()
                self._logger.info(f"[{self.AGENT_TYPE}] 任务完成: {task_id}, 字数: {len(final_content)}, 评分: {stats.get('final_score', 0):.3f}, 迭代: {stats.get('total_iterations', 0)}")
            else:
                agent_result = AgentResult.failure_result(
                    task_id=task_id,
                    agent_type=self.AGENT_TYPE,
                    error="生成失败：内容为空或生成器未初始化",
                    error_type="GenerationError"
                )
                self._increment_failed()
                self._logger.error(f"[{self.AGENT_TYPE}] 任务失败: {task_id}")
            
            self._status.current_task_id = None
            return agent_result
            
        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            self._status.current_task_id = None
            self._logger.error(f"[{self.AGENT_TYPE}] 执行异常: {e}", exc_info=True)
            return AgentResult.failure_result(
                task_id=task_id,
                agent_type=self.AGENT_TYPE,
                error=str(e),
                error_type="ExecutionError"
            )
    
    # === 异步执行方法（V1.1新增 - 解决卡顿问题）===
    
    async def execute_async(
        self,
        task_id: str,
        payload: Dict[str, Any],
        context: AgentContext = None,
        on_progress: Optional[Callable[[str], None]] = None,
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> AgentResult:
        """
        异步执行小说生成任务（新增方法）
        
        核心要点：
        - 使用统一线程池执行
        - 包装V5插件（不修改V5代码）
        - 支持进度回调和流式输出
        - 不阻塞UI线程
        
        Args:
            task_id: 任务ID
            payload: 任务载荷
            context: 执行上下文
            on_progress: 进度回调
            on_chunk: 流式输出回调（逐字显示）
            
        Returns:
            AgentResult 执行结果
        """
        from core.thread_pool_manager import thread_pool_manager
        
        if not self._initialized or not self._plugin:
            return AgentResult.failure_result(
                task_id=task_id,
                agent_type=self.AGENT_TYPE,
                error="Agent未初始化或插件不可用",
                error_type="InitializationError"
            )
        
        try:
            self._logger.info(f"[{self.AGENT_TYPE}] 开始异步执行任务: {task_id}")
            
            # 进度回调
            if on_progress:
                on_progress("正在准备生成...")
            
            # 在统一线程池中执行同步方法
            result = await thread_pool_manager.run_in_executor(
                self.execute,  # 复用同步方法
                task_id,
                payload,
                context
            )
            
            if on_progress:
                on_progress("生成完成")
            
            return result
            
        except Exception as e:
            self._logger.error(f"[{self.AGENT_TYPE}] 异步执行异常: {e}", exc_info=True)
            return AgentResult.failure_result(
                task_id=task_id,
                agent_type=self.AGENT_TYPE,
                error=str(e),
                error_type="ExecutionError"
            )
    
    def submit_async(
        self,
        task_id: str,
        payload: Dict[str, Any],
        on_complete: Callable[[AgentResult], None] = None,
        on_error: Callable[[Exception], None] = None,
        on_progress: Callable[[str], None] = None,
        context: AgentContext = None
    ) -> str:
        """
        提交异步任务（便捷方法）
        
        使用ThreadPoolManager提交异步任务，适合GUI层调用
        
        Args:
            task_id: 任务ID
            payload: 任务载荷
            on_complete: 完成回调
            on_error: 错误回调
            on_progress: 进度回调
            context: 执行上下文
            
        Returns:
            str: 任务ID
        """
        from core.thread_pool_manager import thread_pool_manager
        
        # 创建异步任务
        coro = self.execute_async(
            task_id=task_id,
            payload=payload,
            context=context,
            on_progress=on_progress
        )
        
        # 提交到统一线程池
        thread_pool_manager.submit_async(
            coro,
            on_complete=on_complete,
            on_error=on_error
        )
        
        return task_id
    
    def can_handle(self, task_type: str, payload: Dict[str, Any]) -> bool:
        """判断是否能处理该任务
        
        Args:
            task_type: 任务类型
            payload: 任务载荷
            
        Returns:
            是否能处理
        """
        # 可以处理的任务类型
        supported_types = [
            "novel_generation",
            "chapter_generation",
            "content_generation",
            "generate_chapter",
        ]
        
        if task_type in supported_types:
            return True
        
        # 检查payload中是否有生成相关内容
        if payload.get("chapter_title") or payload.get("chapter_outline"):
            if any(kw in task_type.lower() for kw in ["generat", "生成", "创作", "write"]):
                return True
        
        return False
    
    def cleanup(self) -> bool:
        """清理资源
        
        Returns:
            是否清理成功
        """
        try:
            self._plugin = None
            self._api_client = None
            self._initialized = False
            self._set_state(AgentState.UNLOADED)
            self._logger.info(f"[{self.AGENT_TYPE}] 资源清理完成")
            return True
        except Exception as e:
            self._logger.error(f"[{self.AGENT_TYPE}] 清理失败: {e}")
            return False


# 模块级函数（供AgentPool使用）
def get_agent_class():
    """获取Agent类"""
    return NovelGenerationAgent


def register_agent():
    """注册Agent"""
    return NovelGenerationAgent
