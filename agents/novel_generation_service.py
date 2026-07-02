"""
小说生成服务

V1.1版本（异步支持）
创建日期: 2026-03-24
更新日期: 2026-03-28

特性:
- 封装流水线调用逻辑
- 管理Agent注册表
- 提供GUI回调接口
- 异步生成支持（解决卡顿问题）
"""

import logging
import threading
import os
import asyncio
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

from agents.pipeline_orchestrator import (
    PipelineOrchestrator,
    PipelineState,
    PipelineExecutionResult,
    NovelGenerationConfig,
)
from agents.core.base_agent import BaseAgent
# P0修复：统一使用plugins模块的Agent实现
from agents.plugins import (
    OutlineAnalysisAgent,
    StyleLearningAgent,
    NovelGenerationAgent,
    QualityValidationAgent,
)

logger = logging.getLogger(__name__)


@dataclass
class GenerationProgress:
    """生成进度"""
    pipeline_id: str
    stage_name: str
    progress_percent: float
    iteration: int
    max_iterations: int
    message: str


class NovelGenerationService:
    """
    小说生成服务
    
    负责：
    1. 初始化Agent注册表
    2. 管理流水线编排器
    3. 提供GUI回调接口
    4. 处理LLM客户端配置
    """
    
    def __init__(self, event_bus=None, llm_client=None):
        """
        初始化服务
        
        Args:
            event_bus: 事件总线
            llm_client: LLM客户端实例
        """
        self._event_bus = event_bus
        self._llm_client = llm_client
        
        # Agent注册表
        self._agents: Dict[str, BaseAgent] = {}
        self._initialize_agents()
        
        # 流水线编排器
        self._orchestrator = PipelineOrchestrator(
            agent_registry=self,
            event_bus=event_bus,
        )
        
        # 进度回调
        self._progress_callbacks: List[Callable[[GenerationProgress], None]] = []
        self._orchestrator.add_progress_callback(self._on_progress)
        
        # 当前执行状态
        self._current_pipeline_id: Optional[str] = None
        self._lock = threading.RLock()
    
    def _initialize_agents(self) -> None:
        """初始化内置Agent
        
        P0修复：统一使用plugins模块的Agent实现
        """
        # 注册小说生成流水线Agent（来自plugins模块）
        agents = [
            OutlineAnalysisAgent(),
            StyleLearningAgent(),
            NovelGenerationAgent(),  # 替代原ContentGenerationAgent
            QualityValidationAgent(),
        ]
        
        for agent in agents:
            agent.initialize()
            self._agents[agent.agent_type] = agent
            logger.info(f"Agent已注册: {agent.agent_type}")
    
    def set_llm_client(self, llm_client) -> None:
        """设置LLM客户端"""
        self._llm_client = llm_client
        # 更新小说生成Agent的LLM客户端
        generation_agent = self._agents.get("novel_generation")
        if generation_agent and hasattr(generation_agent, "set_llm_client"):
            generation_agent.set_llm_client(llm_client)
    
    # === Agent注册表接口 ===
    
    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """获取Agent实例"""
        return self._agents.get(agent_type)
    
    def register_agent(self, agent: BaseAgent) -> bool:
        """注册Agent"""
        if agent.agent_type in self._agents:
            logger.warning(f"Agent已存在，将覆盖: {agent.agent_type}")
        
        if not agent.is_initialized:
            if not agent.initialize():
                logger.error(f"Agent初始化失败: {agent.agent_type}")
                return False
        
        self._agents[agent.agent_type] = agent
        logger.info(f"Agent注册成功: {agent.agent_type}")
        return True
    
    def unregister_agent(self, agent_type: str) -> bool:
        """注销Agent"""
        if agent_type not in self._agents:
            return False
        
        agent = self._agents[agent_type]
        agent.cleanup()
        del self._agents[agent_type]
        logger.info(f"Agent注销成功: {agent_type}")
        return True
    
    def list_agents(self) -> List[str]:
        """列出所有Agent"""
        return list(self._agents.keys())
    
    # === 生成接口 ===
    
    def generate_chapter(
        self,
        chapter_title: str,
        chapter_number: int,
        outline_content: str,
        chapter_outline: str,
        target_word_count: int = 2000,
        style_sample_path: str = "",
        style_profile: Dict[str, Any] = None,
        characters: List[Dict[str, Any]] = None,
        worldview: Dict[str, Any] = None,
        previous_chapter_text: str = "",
        max_iterations: int = 5,
        callback: Callable[[PipelineExecutionResult], None] = None,
        knowledge_categories: List[str] = None,  # V2.12新增
        knowledge_domains: List[str] = None,      # V2.12新增
        writing_techniques: List[str] = None,     # V2.12新增
    ) -> str:
        """
        生成章节内容（异步）
        
        Args:
            chapter_title: 章节标题
            chapter_number: 章节编号
            outline_content: 完整大纲内容
            chapter_outline: 当前章节大纲
            target_word_count: 目标字数
            style_sample_path: 风格样本路径
            style_profile: 风格档案
            characters: 人物设定
            worldview: 世界观设定
            previous_chapter_text: 上一章内容
            max_iterations: 最大迭代次数
            callback: 完成回调
            knowledge_categories: 选中的知识库分类（V2.12新增）
            knowledge_domains: 选中的知识领域（V2.12新增）
            writing_techniques: 选中的写作技巧（V2.12新增）
            
        Returns:
            流水线ID
        """
        config = NovelGenerationConfig(
            chapter_title=chapter_title,
            chapter_number=chapter_number,
            target_word_count=target_word_count,
            outline_content=outline_content,
            chapter_outline=chapter_outline,
            style_sample_path=style_sample_path,
            style_profile=style_profile or {},
            characters=characters or [],
            worldview=worldview or {},
            max_iterations=max_iterations,
            previous_chapter_text=previous_chapter_text,
            knowledge_categories=knowledge_categories or [],
            knowledge_domains=knowledge_domains or [],
            writing_techniques=writing_techniques or [],
        )
        
        # 包装回调
        def _callback_wrapper(result: PipelineExecutionResult):
            with self._lock:
                if self._current_pipeline_id == result.pipeline_id:
                    self._current_pipeline_id = None
            
            if callback:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"回调执行异常: {e}")
        
        with self._lock:
            pipeline_id = self._orchestrator.execute_novel_generation_async(
                config=config,
                callback=_callback_wrapper,
            )
            self._current_pipeline_id = pipeline_id
        
        return pipeline_id
    
    def generate_chapter_sync(
        self,
        chapter_title: str,
        chapter_number: int,
        outline_content: str,
        chapter_outline: str,
        **kwargs
    ) -> PipelineExecutionResult:
        """
        生成章节内容（同步）
        
        Returns:
            流水线执行结果
        """
        config = NovelGenerationConfig(
            chapter_title=chapter_title,
            chapter_number=chapter_number,
            outline_content=outline_content,
            chapter_outline=chapter_outline,
            **kwargs
        )
        
        return self._orchestrator.execute_novel_generation(config)
    
    def cancel_generation(self) -> bool:
        """取消当前生成"""
        return self._orchestrator.cancel()
    
    # === 异步生成接口（V1.1新增 - 解决卡顿问题）===
    
    async def generate_chapter_async(
        self,
        chapter_title: str,
        chapter_number: int,
        outline_content: str,
        chapter_outline: str,
        target_word_count: int = 2000,
        style_sample_path: str = "",
        style_profile: Dict[str, Any] = None,
        characters: List[Dict[str, Any]] = None,
        worldview: Dict[str, Any] = None,
        previous_chapter_text: str = "",
        max_iterations: int = 5,
        quality_threshold: float = 0.8,  # P0修复：新增参数
        on_progress: Callable[[GenerationProgress], None] = None,
        on_chunk: Callable[[str], None] = None,
        knowledge_categories: List[str] = None,
        knowledge_domains: List[str] = None,
        writing_techniques: List[str] = None,
    ) -> PipelineExecutionResult:
        """
        异步生成章节内容（新增方法）
        
        核心设计：
        - Service层负责异步调度
        - 使用统一线程池执行
        - 支持进度回调和流式输出
        - 不阻塞UI线程
        
        Args:
            chapter_title: 章节标题
            chapter_number: 章节编号
            outline_content: 完整大纲内容
            chapter_outline: 当前章节大纲
            target_word_count: 目标字数
            style_sample_path: 风格样本路径
            style_profile: 风格档案
            characters: 人物设定
            worldview: 世界观设定
            previous_chapter_text: 上一章内容
            max_iterations: 最大迭代次数
            quality_threshold: 质量阈值（P0修复：专家配置参数）
            on_progress: 进度回调
            on_chunk: 流式输出回调（逐字显示）
            knowledge_categories: 选中的知识库分类
            knowledge_domains: 选中的知识领域
            writing_techniques: 选中的写作技巧
            
        Returns:
            PipelineExecutionResult: 流水线执行结果
        """
        from core.thread_pool_manager import thread_pool_manager
        
        config = NovelGenerationConfig(
            chapter_title=chapter_title,
            chapter_number=chapter_number,
            target_word_count=target_word_count,
            outline_content=outline_content,
            chapter_outline=chapter_outline,
            style_sample_path=style_sample_path,
            style_profile=style_profile or {},
            characters=characters or [],
            worldview=worldview or {},
            max_iterations=max_iterations,
            validation_threshold=quality_threshold,  # P0修复：映射参数
            previous_chapter_text=previous_chapter_text,
            knowledge_categories=knowledge_categories or [],
            knowledge_domains=knowledge_domains or [],
            writing_techniques=writing_techniques or [],
        )
        
        # 添加进度回调（如果有）
        if on_progress:
            self.add_progress_callback(on_progress)
        
        try:
            # 在统一线程池中执行同步方法
            result = await thread_pool_manager.run_in_executor(
                self._orchestrator.execute_novel_generation,
                config
            )
            
            return result
            
        finally:
            # 移除进度回调
            if on_progress:
                self.remove_progress_callback(on_progress)
    
    def submit_async_generation(
        self,
        chapter_title: str,
        chapter_number: int,
        outline_content: str,
        chapter_outline: str,
        on_complete: Callable[[PipelineExecutionResult], None] = None,
        on_error: Callable[[Exception], None] = None,
        on_progress: Callable[[GenerationProgress], None] = None,
        **kwargs
    ) -> str:
        """
        提交异步生成任务（便捷方法）
        
        使用ThreadPoolManager提交异步任务，适合GUI层调用
        
        Args:
            chapter_title: 章节标题
            chapter_number: 章节编号
            outline_content: 完整大纲内容
            chapter_outline: 当前章节大纲
            on_complete: 完成回调
            on_error: 错误回调
            on_progress: 进度回调
            **kwargs: 其他参数
            
        Returns:
            str: 任务ID（可用于取消）
        """
        from core.thread_pool_manager import thread_pool_manager
        
        # 创建异步任务
        coro = self.generate_chapter_async(
            chapter_title=chapter_title,
            chapter_number=chapter_number,
            outline_content=outline_content,
            chapter_outline=chapter_outline,
            on_progress=on_progress,
            **kwargs
        )
        
        # 提交到统一线程池
        future = thread_pool_manager.submit_async(
            coro,
            on_complete=on_complete,
            on_error=on_error
        )
        
        return str(id(future))
    
    def get_generation_state(self) -> PipelineState:
        """获取当前生成状态"""
        return self._orchestrator.get_state()
    
    def get_generation_result(self, pipeline_id: str) -> Optional[PipelineExecutionResult]:
        """获取生成结果"""
        return self._orchestrator.get_result(pipeline_id)
    
    # === 进度回调 ===
    
    def add_progress_callback(
        self,
        callback: Callable[[GenerationProgress], None]
    ) -> None:
        """添加进度回调"""
        self._progress_callbacks.append(callback)
    
    def remove_progress_callback(
        self,
        callback: Callable[[GenerationProgress], None]
    ) -> None:
        """移除进度回调"""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    def _on_progress(
        self,
        pipeline_id: str,
        stage_name: str,
        progress_percent: float,
        iteration: int = 1,
        max_iterations: int = 5,
    ) -> None:
        """内部进度处理
        
        P2修复：支持迭代信息传递
        """
        progress = GenerationProgress(
            pipeline_id=pipeline_id,
            stage_name=stage_name,
            progress_percent=progress_percent,
            iteration=iteration,
            max_iterations=max_iterations,
            message=f"[迭代{iteration}/{max_iterations}] 正在执行: {stage_name}",
        )
        
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception as e:
                logger.error(f"进度回调异常: {e}")
    
    # === 清理 ===
    
    def shutdown(self) -> None:
        """关闭服务"""
        self._orchestrator.shutdown()
        
        # 清理所有Agent
        for agent in self._agents.values():
            try:
                agent.cleanup()
            except Exception as e:
                logger.error(f"清理Agent失败: {e}")
        
        self._agents.clear()
        logger.info("NovelGenerationService已关闭")


# === 单例模式 ===

_service_instance: Optional[NovelGenerationService] = None
_service_lock = threading.Lock()


def get_generation_service(
    event_bus=None,
    llm_client=None,
) -> NovelGenerationService:
    """
    获取生成服务单例
    
    Args:
        event_bus: 事件总线
        llm_client: LLM客户端
        
    Returns:
        NovelGenerationService实例
    """
    global _service_instance
    
    with _service_lock:
        if _service_instance is None:
            _service_instance = NovelGenerationService(
                event_bus=event_bus,
                llm_client=llm_client,
            )
        elif llm_client:
            _service_instance.set_llm_client(llm_client)
        
        return _service_instance


class GenerationDataService:
    """
    生成数据服务 - 数据加工逻辑的唯一入口
    
    设计原则（V3.0修订 - 数据引用传递模式）：
    - GUI传入原始数据引用（GUI是数据持有者，这由用户交互架构决定）
    - 服务层负责数据加工（格式化、降级、前文回退等业务逻辑）
    - GUI不持有任何业务逻辑方法
    
    解决技术债务：P0-V3（7个数据获取）+ P1-V1（前文获取）
    
    架构约束：
    outline-parser-v3/style-learner-v5/character-manager-v1/worldview-parser-v1
    等插件的analyze()是无状态的，不缓存结果。
    数据唯一缓存在MainWindow实例属性中。
    因此GenerationDataService不能"从插件拉取数据"，
    而必须接收GUI传入的原始数据引用。
    """
    
    def __init__(self):
        pass  # 无状态，不需要plugin_registry/service_locator
    
    def build_generation_context(
        self,
        chapter_number: int,
        target_words: int,
        raw_data: dict,
        selected_knowledge_bases: List[str] = None,
        selected_writing_techniques: List[str] = None,
        expert_config: dict = None,
    ) -> Dict[str, Any]:
        """
        构建生成上下文 - 对原始数据执行业务逻辑加工
        
        Args:
            chapter_number: 章节号（用户选择）
            target_words: 目标字数（用户选择）
            raw_data: GUI传入的原始数据引用，格式：
                {
                    'outline_chapters_data': list,
                    'outline_content': str,
                    'chapter_outlines': dict,
                    'style_profile': dict,
                    'character_data': list,
                    'worldview': dict,
                    'reverse_chapters': dict,
                    'generated_content': list,
                    'project_data': dict,
                }
            selected_knowledge_bases: 勾选的知识库分类
            selected_writing_techniques: 勾选的写作技巧
            expert_config: 专家配置
            
        Returns:
            dict: 包含全部生成所需数据的上下文字典
        """
        context = {
            'chapter_number': chapter_number,
            'target_words': target_words,
            'knowledge_categories': selected_knowledge_bases or [],
            'writing_techniques': selected_writing_techniques or [],
            'expert_config': expert_config,
        }
        
        # 1. 大纲内容（业务逻辑：格式化章节列表为文本 + 后备策略）
        context['outline_content'] = self._format_outline(raw_data)
        context['chapter_outline'] = self._format_chapter_outline(
            raw_data, chapter_number
        )
        
        # 2. 风格档案（业务逻辑：8维度→生成器格式 转换 + 模板格式处理）
        context['style_profile'] = self._format_style_profile(raw_data)
        
        # 3. 人物设定（业务逻辑：列表→字典 转换）
        context['characters'] = self._format_characters(raw_data)
        
        # 4. 世界观（直接传递，无业务逻辑）
        context['worldview'] = raw_data.get('worldview', {})
        
        # 5. 前文内容（业务逻辑：3级回退策略，P1-V1技术债务解决）
        context['previous_chapter_text'] = self._get_previous_chapters(
            chapter_number, raw_data
        )
        
        return context
    
    # ========== 数据加工方法（业务逻辑，从GUI层迁移）==========
    
    def _format_outline(self, raw_data: dict) -> str:
        """格式化大纲文本（原GUI._get_outline_content逻辑）
        
        策略：优先从outline_chapters_data格式化，后备从outline_content获取
        """
        chapters_data = raw_data.get('outline_chapters_data')
        if chapters_data:
            outline_text = ""
            for i, chapter in enumerate(chapters_data, 1):
                ch_num = chapter.get('chapter_number', i)
                title = chapter.get('title', f'第{ch_num}章')
                summary = chapter.get('summary', '')
                outline_text += f"第{ch_num}章：{title}\n{summary}\n\n"
            return outline_text.strip()
        
        # 后备：从用户输入的原始大纲获取
        return raw_data.get('outline_content', '')
    
    def _format_chapter_outline(self, raw_data: dict, chapter_number: int) -> str:
        """格式化章节大纲（原GUI._get_chapter_outline逻辑）
        
        策略：优先从outline_chapters_data格式化，后备从chapter_outlines获取
        """
        chapters_data = raw_data.get('outline_chapters_data')
        if chapters_data:
            for chapter in chapters_data:
                if chapter.get('chapter_number') == chapter_number:
                    title = chapter.get('title', '')
                    summary = chapter.get('summary', '')
                    key_content = chapter.get('key_content', '')
                    plot_points = chapter.get('plot_points', [])
                    characters = chapter.get('characters', [])
                    outline = f"【章节标题】{title}\n"
                    outline += f"【内容摘要】{summary}\n"
                    if key_content:
                        outline += f"【关键内容】{key_content}\n"
                    if plot_points:
                        outline += f"【情节要点】{'；'.join(plot_points)}\n"
                    if characters:
                        outline += f"【出场人物】{', '.join(characters)}\n"
                    return outline.strip()
        
        # 后备：从用户手动输入的章节大纲获取
        chapter_outlines = raw_data.get('chapter_outlines', {})
        if isinstance(chapter_outlines, dict):
            return chapter_outlines.get(chapter_number, "")
        return ""
    
    def _format_style_profile(self, raw_data: dict) -> dict:
        """格式化风格档案（原GUI._get_style_profile逻辑）
        
        业务逻辑：8维度分析结果→生成器格式 转换
        两种格式：作者分析结果 / 模板格式
        """
        profile = raw_data.get('style_profile')
        if not profile or not isinstance(profile, dict):
            return {}
        
        # 格式1：插件8维度分析结果，转换为生成器可用的格式
        if profile.get('author_name') or profile.get('style_tags'):
            return {
                "author_name": profile.get('author_name', ''),
                "genre": profile.get('genre', ''),
                "style_tags": profile.get('style_tags', []),
                "writing_characteristics": profile.get('writing_characteristics', []),
                "prompt_suggestions": profile.get('prompt_suggestions', []),
                "register": profile.get('language_style', {}).get('register', '通用'),
                "sentiment": profile.get('emotional_tone', {}).get('overall_sentiment', '中性'),
                "similar_authors": profile.get('similar_authors', []),
                "_full_profile": profile,
            }
        
        # 格式2：模板格式
        if profile.get('is_template'):
            result = {
                "author_name": profile.get('name', '自定义'),
                "genre": profile.get('description', '')[:20],
                "style_tags": profile.get('style_tags', []),
                "dimensions": profile.get('dimensions', {}),
            }
            # 合并模板原始字段（等价于原GUI代码的**profile展开）
            for k, v in profile.items():
                if k not in result:
                    result[k] = v
            return result
        
        # 默认返回原始数据
        return profile
    
    def _format_characters(self, raw_data: dict) -> dict:
        """格式化人物设定（原GUI._get_characters逻辑）
        
        业务逻辑：列表→字典 转换（匹配GenerationRequest.character_profiles要求）
        """
        character_list = raw_data.get('character_data', [])
        if not character_list:
            return {}
        
        character_dict = {}
        for char in character_list:
            if isinstance(char, dict):
                name = char.get('name', '未命名')
                character_dict[name] = char
        
        return character_dict
    
    def _get_previous_chapters(
        self, 
        chapter_number: int, 
        raw_data: dict
    ) -> str:
        """获取前5章文本内容（原GUI._get_previous_chapters_text逻辑）
        
        P1-V1技术债务解决：3级回退策略从GUI迁移到服务层
        
        策略优先级：
        1. 从reverse_chapters获取（逆向反馈区的已导入章节）
        2. 从generated_content获取（已生成的章节内容）
        3. 从project_data获取（项目管理器数据）
        
        限制6000字符避免token溢出
        """
        previous_text = ""
        
        # 策略1：从逆向反馈区的已导入章节获取
        reverse_chapters = raw_data.get('reverse_chapters')
        if reverse_chapters:
            for ch_id, ch_data in reverse_chapters.items():
                if isinstance(ch_data, dict):
                    ch_num = ch_data.get('chapter_number', 0)
                    if ch_num == 0:
                        try:
                            ch_num = int(ch_id.replace('ch_', '').replace('chapter_', ''))
                        except (ValueError, AttributeError):
                            continue
                    if 0 < ch_num < chapter_number:
                        content = ch_data.get('content', '')
                        if content:
                            previous_text += f"--- 第{ch_num}章 ---\n{content}\n\n"
        
        # 策略2：从已生成的章节内容获取
        if not previous_text:
            generated_content = raw_data.get('generated_content')
            if generated_content:
                max_prev = min(chapter_number - 1, 5)
                start_idx = max(0, len(generated_content) - max_prev)
                for i, content in enumerate(generated_content[start_idx:], start_idx + 1):
                    if content and isinstance(content, str):
                        previous_text += f"--- 第{i}章 ---\n{content}\n\n"
        
        # 策略3：从项目管理器获取
        if not previous_text:
            project_data = raw_data.get('project_data')
            if project_data:
                try:
                    completed = project_data.get('completed_chapters', [])
                    for ch in completed:
                        if isinstance(ch, dict):
                            ch_num = ch.get('chapter_number', 0)
                            content = ch.get('content', '')
                            if 0 < ch_num < chapter_number and content:
                                previous_text += f"--- 第{ch_num}章 ---\n{content}\n\n"
                except Exception:
                    pass
        
        return previous_text[-6000:] if previous_text else ""
