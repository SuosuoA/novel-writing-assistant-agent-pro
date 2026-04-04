"""
快捷创作生成器插件 V1.1
Quick Creation Generator Plugin

功能：
1. 世界观快速生成
2. 大纲快速生成
3. 人设快速生成
4. 关键情节快速生成
5. 全部生成（统一入口，确保协调一致）

V1.1新增（2026-03-24）：
- LLM调用超时保护机制（concurrent.futures强制超时）
- 自定义异常类型（QuickCreationError/TimeoutError/APIError）
- 缓存持久化机制（save_to_disk/load_from_disk）
- QuickCreationRequest统一请求入口增强

作者：AI工程师
更新：高级开发工程师
日期：2026-03-24
"""

import json
import logging
import time
import concurrent.futures
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.plugin_interface import BasePlugin, PluginMetadata, PluginContext, PluginState, PluginType
from core.models import (
    QuickCreationRequest,
    QuickCreationResult,
    QuickCreationTarget,
    WorldviewResult,
    OutlineResult,
    CharacterResult,
    PlotResult
)

# V1.4新增：导入全局缓存管理器
try:
    from core.cache_manager import get_cache_manager, generate_cache_key
    CACHE_MANAGER_AVAILABLE = True
except ImportError:
    CACHE_MANAGER_AVAILABLE = False

# 支持相对导入和绝对导入（修复动态加载问题）
try:
    from .reference_parser import ReferenceTextParser, ReferenceFusion, ParsedReference
    from .result_storage import (
        ResultStorageManager,
        ConflictStrategy,
        ConflictInfo,
        ImportResult,
        save_quick_creation_result,
        import_quick_creation_result,
        WORLDVIEW_SCHEMA,
        OUTLINE_SCHEMA,
        CHARACTER_SCHEMA,
        PLOT_SCHEMA,
        SCHEMA_VERSION
    )
except ImportError:
    # 动态加载时，将插件目录添加到sys.path
    import sys
    from pathlib import Path
    plugin_dir = Path(__file__).parent
    if str(plugin_dir) not in sys.path:
        sys.path.insert(0, str(plugin_dir))
    
    from reference_parser import ReferenceTextParser, ReferenceFusion, ParsedReference
    from result_storage import (
        ResultStorageManager,
        ConflictStrategy,
        ConflictInfo,
        ImportResult,
        save_quick_creation_result,
        import_quick_creation_result,
        WORLDVIEW_SCHEMA,
        OUTLINE_SCHEMA,
        CHARACTER_SCHEMA,
        PLOT_SCHEMA,
        SCHEMA_VERSION
    )


# ============================================================================
# 自定义异常类型
# ============================================================================

class QuickCreationError(Exception):
    """快捷创作基础异常"""
    pass


class QuickCreationTimeoutError(QuickCreationError):
    """快捷创作超时异常"""
    pass


class QuickCreationAPIError(QuickCreationError):
    """快捷创作API异常"""
    pass


class QuickCreationParseError(QuickCreationError):
    """快捷创作解析异常"""
    pass


logger = logging.getLogger(__name__)


class CreationType(Enum):
    """创作类型"""
    WORLDVIEW = "worldview"
    OUTLINE = "outline"
    CHARACTER = "character"
    PLOT = "plot"
    ALL = "all"


class GenerationType(Enum):
    """生成类型"""
    QUICK = "quick"          # 快速生成（较少细节）
    STANDARD = "standard"    # 标准生成
    DETAILED = "detailed"    # 详细生成


@dataclass
class PromptTemplate:
    """Prompt模板"""
    system: str
    user_template: str
    examples: List[str] = field(default_factory=list)


class QuickCreationPlugin(BasePlugin):
    """
    快捷创作生成器插件
    
    核心能力：
    1. 基于关键词和参考文本生成世界观设定
    2. 基于主题和大纲生成章节大纲
    3. 基于人物模板生成人物设定
    4. 基于大纲生成关键情节
    5. 统一入口确保各设定协调一致
    
    V1.1新增：
    - LLM调用超时保护机制
    - 缓存持久化机制
    - 自定义异常类型
    
    V1.5新增（Claw化增强）：
    - 评分机制：WeightedValidatorPlugin集成
    - 四层记忆集成：L1热/L2温/L3冷/L4档案
    - 低分重试机制（最多3次）
    - EventBus事件发布
    """
    
    # 类常量
    DEFAULT_TIMEOUT = 120          # 默认超时时间（秒）
    MAX_TOKENS_QUICK = 2000        # 快速生成token限制
    MAX_TOKENS_STANDARD = 4000     # 标准生成token限制
    MAX_TOKENS_DETAILED = 6000     # 详细生成token限制
    
    # V1.5新增：Claw化相关常量
    QUALITY_THRESHOLD = 0.8        # 质量评分阈值
    MAX_RETRY_COUNT = 3            # 最大重试次数
    HIGH_QUALITY_THRESHOLD = 0.9   # 高质量阈值（用于L3记录）
    
    # 插件元数据
    METADATA = PluginMetadata(
        id="quick-creator-v1",
        name="快捷创作生成器 V1",
        version="1.3.0",
        description="快速生成世界观、大纲、人设、关键情节等设定",
        author="AI工程师",
        plugin_type=PluginType.GENERATOR,
        permissions=["llm.call", "cache.readwrite"],
        dependencies=[]
    )
    
    def __init__(self):
        """初始化快捷创作插件"""
        super().__init__(self.METADATA)
        self.api_client = None
        self.config: Dict[str, Any] = {}
        
        # Prompt模板缓存
        self._prompt_templates: Dict[str, PromptTemplate] = {}
        
        # 生成历史（用于确保一致性）
        self._generation_history: Dict[str, Any] = {}
        
        # 超时时间
        self._timeout: int = self.DEFAULT_TIMEOUT
        
        # 缓存文件路径
        self._cache_file: Optional[Path] = None
        
        # 参考文本解析器（V1.2新增）
        self._reference_parser: Optional[ReferenceTextParser] = None
        
        # 解析后的参考文本缓存
        self._parsed_reference_cache: Dict[str, ParsedReference] = {}
        
        # 结果存储管理器（V1.3新增）
        self._storage_manager: Optional[ResultStorageManager] = None
        
        # V1.4新增：全局缓存管理器引用
        self._cache_manager: Optional[Any] = None
        
        # V1.5新增：Claw化组件引用
        self._validator: Optional[Any] = None  # 评分器
        self._session_manager: Optional[Any] = None  # L1热记忆
        self._vector_store: Optional[Any] = None  # L2温记忆
        self._git_notes_manager: Optional[Any] = None  # L3冷记忆
        
        # V1.5新增：评分历史（用于L4档案触发）
        self._score_history: Dict[str, List[float]] = {}
    
    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return cls.METADATA
    
    def initialize(self, context: PluginContext) -> bool:
        """
        初始化插件
        
        参数:
            context: 插件上下文
            
        返回:
            是否初始化成功
        """
        self._context = context
        self.config = getattr(context, 'config', {}) or {}
        
        # V1.4新增：初始化全局缓存管理器
        if CACHE_MANAGER_AVAILABLE:
            try:
                self._cache_manager = get_cache_manager()
                logger.info("[QuickCreator] 全局缓存管理器初始化成功")
            except Exception as e:
                logger.warning(f"[QuickCreator] 全局缓存管理器初始化失败: {e}")
        
        # 设置缓存文件路径
        if hasattr(context, 'config_manager'):
            try:
                project_path = context.config_manager.get_project_path()
                if project_path:
                    self._cache_file = Path(project_path) / ".quick_creator_cache" / "generation_cache.json"
            except Exception:
                pass
        
        # 加载Prompt模板
        self._load_prompt_templates()
        
        # 初始化参考文本解析器
        self._reference_parser = ReferenceTextParser()
        
        # 初始化结果存储管理器
        self._storage_manager = ResultStorageManager()
        if hasattr(context, 'config_manager'):
            try:
                project_path = context.config_manager.get_project_path()
                if project_path:
                    self._storage_manager.set_project_path(project_path)
            except Exception:
                pass
        
        # 尝试加载缓存
        self._load_cache_from_disk()
        
        self._state = PluginState.LOADED
        logger.info(f"快捷创作插件初始化完成: {self.METADATA.id}")
        return True
    
    def set_api_client(self, client: Any) -> None:
        """
        设置大模型API客户端
        
        Args:
            client: OpenAI客户端实例
        """
        self.api_client = client
        logger.info("大模型API客户端已设置")
    
    def _load_prompt_templates(self) -> None:
        """加载Prompt模板"""
        # 世界观生成模板
        self._prompt_templates["worldview"] = PromptTemplate(
            system="""你是一位专业的小说世界观架构师，擅长创造丰富多彩、逻辑自洽的世界设定。
你需要根据用户提供的关键词和参考文本，生成完整的世界观设定。

要求：
1. 世界观要有独特性和吸引力
2. 设定要逻辑自洽，不存在明显矛盾
3. 要有足够的细节支撑后续创作
4. 输出格式必须为JSON""",
            user_template="""请根据以下信息生成世界观设定：

关键词：{{keywords}}
参考文本：{{reference_text}}
题材类型：{{genre}}
生成详细程度：{{generation_type}}

请生成包含以下内容的世界观设定（JSON格式）：
{
    "world_name": "世界名称",
    "era": "时代背景",
    "geography": "地理环境描述",
    "social_structure": "社会结构",
    "power_system": "力量体系（如有）",
    "factions": ["势力组织列表"],
    "rules": ["世界规则/法则"],
    "resources": ["重要资源"],
    "conflicts": ["核心冲突"],
    "unique_elements": ["独特元素"]
}""",
            examples=[]
        )
        
        # 大纲生成模板
        self._prompt_templates["outline"] = PromptTemplate(
            system="""你是一位专业的小说大纲设计师，擅长设计引人入胜的故事架构。
你需要根据用户提供的主题、世界观和参考信息，生成完整的章节大纲。

要求：
1. 故事节奏合理，张弛有度
2. 情节发展有逻辑性
3. 高潮设置合理
4. 输出格式必须为Markdown""",
            user_template="""请根据以下信息生成章节大纲：

主题：{{theme}}
世界观概述：{{worldview_summary}}
主要人物：{{main_characters}}
目标字数：{{target_words}}
章节数量：{{chapter_count}}
参考文本：{{reference_text}}
生成详细程度：{{generation_type}}

请生成章节大纲（Markdown格式），每章包含：
- 章节标题
- 主要事件
- 关键情节
- 人物出场
- 字数建议""",
            examples=[]
        )
        
        # 人设生成模板
        self._prompt_templates["character"] = PromptTemplate(
            system="""你是一位专业的人物设定师，擅长创造立体丰满、有血有肉的人物形象。
你需要根据用户提供的模板和世界观，生成完整的人物设定。

要求：
1. 人物要有独特性和记忆点
2. 性格要有矛盾和成长空间
3. 背景故事要有说服力
4. 输出格式必须为JSON""",
            user_template="""请根据以下信息生成人物设定：

人物名称：{{character_name}}
角色定位：{{role}}
世界观背景：{{worldview_summary}}
性格关键词：{{personality_keywords}}
参考文本：{{reference_text}}
生成详细程度：{{generation_type}}

请生成包含以下内容的人物设定（JSON格式）：
{
    "name": "人物名称",
    "role": "角色定位",
    "age": "年龄",
    "gender": "性别",
    "appearance": "外貌描述",
    "personality": {
        "core": "核心性格",
        "traits": ["性格特点"],
        "strengths": ["优点"],
        "weaknesses": ["缺点"]
    },
    "background": "背景故事",
    "abilities": ["能力/技能"],
    "relationships": ["人物关系"],
    "goals": ["目标/动机"],
    "secrets": ["秘密/隐藏面"],
    "arc": "人物弧光/成长方向"
}""",
            examples=[]
        )
        
        # 情节生成模板
        self._prompt_templates["plot"] = PromptTemplate(
            system="""你是一位专业的情节设计师，擅长设计扣人心弦的关键情节。
你需要根据用户提供的背景和需求，生成关键情节设定。

要求：
1. 情节要有戏剧性和张力
2. 要有转折和意外
3. 要与整体故事协调
4. 输出格式必须为JSON""",
            user_template="""请根据以下信息生成关键情节：

大纲概述：{{outline_summary}}
涉及人物：{{characters}}
情节类型：{{plot_type}}
关键事件：{{key_event}}
世界观背景：{{worldview_summary}}
生成详细程度：{{generation_type}}

请生成包含以下内容的关键情节（JSON格式）：
{
    "title": "情节标题",
    "type": "情节类型",
    "importance": "重要性等级",
    "description": "情节描述",
    "setup": "铺垫/起因",
    "development": "发展过程",
    "climax": "高潮/转折",
    "resolution": "结局/影响",
    "characters_involved": ["涉及人物"],
    "consequences": ["后续影响"],
    "foreshadowing": ["伏笔"]
}""",
            examples=[]
        )
        
        logger.info("Prompt模板加载完成")
    
    def _render_prompt(self, template: PromptTemplate, variables: Dict[str, Any]) -> tuple:
        """
        渲染Prompt模板
        
        Args:
            template: Prompt模板
            variables: 变量字典
            
        Returns:
            (system_prompt, user_prompt)
        """
        user_prompt = template.user_template
        for key, value in variables.items():
            user_prompt = user_prompt.replace("{{" + key + "}}", str(value))
        
        return template.system, user_prompt
    
    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.8,
        max_tokens: int = 4000
    ) -> str:
        """
        调用大模型API（V1.1增强版）
        
        使用concurrent.futures实现强制超时保护
        
        参数:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 温度参数
            max_tokens: 最大token数
            
        返回:
            生成结果
            
        异常:
            QuickCreationTimeoutError: 调用超时
            QuickCreationAPIError: API调用失败
        """
        if not self.api_client:
            raise QuickCreationAPIError("API客户端未设置，请先调用set_api_client()")
        
        try:
            # V1.1新增：使用concurrent.futures实现强制超时
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._do_api_call,
                    system_prompt,
                    user_prompt,
                    temperature,
                    max_tokens
                )
                try:
                    content = future.result(timeout=self._timeout)
                    return content
                    
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    raise QuickCreationTimeoutError(f"LLM调用超时（{self._timeout}秒）")
                    
        except QuickCreationTimeoutError:
            raise
        except QuickCreationAPIError:
            raise
        except Exception as e:
            logger.error(f"LLM API调用失败: {e}")
            raise QuickCreationAPIError(f"API调用失败: {e}")
    
    def _do_api_call(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """
        执行实际的API调用（内部方法）
        
        参数:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 温度参数
            max_tokens: 最大token数
            
        返回:
            生成的文本
        """
        # 使用AIServiceManager统一调用
        from core.ai_service_manager import get_ai_service_manager
        from core.ai_provider import GenerationConfig

        ai_manager = get_ai_service_manager()
        
        config = GenerationConfig(
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        result = ai_manager.generate_text(
            prompt=user_prompt,
            config=config,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 检查生成结果
        if not result.success:
            logger.error(f"快捷创作生成失败: {result.error}")
            raise RuntimeError(f"AI生成失败: {result.error}")
        
        # 记录Token使用情况
        logger.info(f"生成完成，Token使用: {result.usage}")
        
        return result.text
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        解析JSON响应
        
        Args:
            response: LLM响应文本
            
        Returns:
            解析后的字典
        """
        # 尝试提取JSON块
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = response[json_start:json_end]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # 如果无法解析，返回原始响应
        return {"raw_content": response}
    
    # ==================== 公共API方法 ====================
    
    def generate_worldview(
        self,
        keywords: List[str],
        reference_text: str = "",
        genre: str = "玄幻",
        generation_type: str = "standard"
    ) -> WorldviewResult:
        """
        生成世界观设定
        
        V1.4新增：集成全局缓存，提升缓存命中率
        
        Args:
            keywords: 关键词列表
            reference_text: 参考文本
            genre: 题材类型
            generation_type: 生成详细程度
            
        Returns:
            世界观数据
        """
        logger.info(f"开始生成世界观: keywords={keywords}, genre={genre}")
        
        # V1.4新增：缓存检查
        cache_key = None
        if self._cache_manager and CACHE_MANAGER_AVAILABLE:
            cache_key = generate_cache_key(
                tuple(keywords),
                reference_text[:100] if reference_text else "",
                genre,
                generation_type
            )
            
            cached_result = self._cache_manager.get("worldview", cache_key)
            if cached_result:
                logger.info(
                    f"[QuickCreator] 世界观缓存命中 "
                    f"(命中率: {self._cache_manager.get_stats()['global']['hit_rate']:.2%})"
                )
                # 重建WorldviewResult
                return WorldviewResult(
                    success=True,
                    data=cached_result.get("data", {}),
                    error=None,
                    generation_time=0.0,
                    model_used=cached_result.get("model_used", ""),
                    tokens_used=0
                )
        
        # 解析参考文本（V1.2增强）
        parsed = None
        if reference_text and self._reference_parser:
            parsed = self._reference_parser.parse(reference_text)
            logger.info(f"参考文本解析完成: confidence={parsed.confidence:.2f}")
        
        template = self._prompt_templates["worldview"]
        
        # 准备Prompt变量
        variables = {
            "keywords": "、".join(keywords),
            "reference_text": reference_text or "无",
            "genre": genre,
            "generation_type": generation_type
        }
        
        # 融合参考文本元素（V1.2新增）
        if parsed and parsed.has_worldview():
            variables = ReferenceFusion.fusion_to_worldview_prompt(parsed, variables)
            logger.info("已将参考世界观元素融合到Prompt中")
        
        system_prompt, user_prompt = self._render_prompt(template, variables)
        
        # 根据生成类型调整token数
        max_tokens_map = {"quick": 2000, "standard": 4000, "detailed": 6000}
        max_tokens = max_tokens_map.get(generation_type, 4000)
        
        response = self._call_llm(system_prompt, user_prompt, max_tokens=max_tokens)
        worldview_dict = self._parse_json_response(response)
        
        # 缓存生成结果
        self._generation_history["worldview"] = worldview_dict
        
        # V1.4新增：存储到全局缓存
        if self._cache_manager and cache_key:
            cache_data = {
                "data": worldview_dict,
                "model_used": self.config.get("model", "deepseek-chat"),
                "keywords": keywords,
                "genre": genre,
                "generation_type": generation_type,
                "cached_at": datetime.now().isoformat()
            }
            self._cache_manager.set("worldview", cache_key, cache_data)
            
            # 记录API调用
            self._cache_manager.record_api_call()
        
        logger.info("世界观生成完成")
        
        return WorldviewResult(
            setting_name=worldview_dict.get("world_name", worldview_dict.get("setting_name", "")),
            era=worldview_dict.get("era", ""),
            geography=worldview_dict.get("geography", ""),
            social_structure=worldview_dict.get("social_structure", ""),
            power_system=worldview_dict.get("power_system", ""),
            major_forces=worldview_dict.get("factions", worldview_dict.get("major_forces", [])),
            rules_and_laws=worldview_dict.get("rules", worldview_dict.get("rules_and_laws", [])),
            special_elements=worldview_dict.get("unique_elements", worldview_dict.get("special_elements", [])),
            background_story=worldview_dict.get("background_story", "")
        )
    
    def generate_outline(
        self,
        theme: str,
        worldview_summary: str = "",
        main_characters: List[str] = None,
        target_words: int = 100000,
        chapter_count: int = 50,
        reference_text: str = "",
        generation_type: str = "standard"
    ) -> OutlineResult:
        """
        生成章节大纲
        
        Args:
            theme: 主题
            worldview_summary: 世界观概述
            main_characters: 主要人物列表
            target_words: 目标字数
            chapter_count: 章节数量
            reference_text: 参考文本
            generation_type: 生成详细程度
            
        Returns:
            大纲数据
        """
        logger.info(f"开始生成大纲: theme={theme}, chapters={chapter_count}")
        
        # 解析参考文本（V1.2增强）
        parsed = None
        if reference_text and self._reference_parser:
            parsed = self._reference_parser.parse(reference_text)
            logger.info(f"参考文本解析完成: confidence={parsed.confidence:.2f}")
        
        template = self._prompt_templates["outline"]
        
        # 准备Prompt变量
        variables = {
            "theme": theme,
            "worldview_summary": worldview_summary or self._get_worldview_summary(),
            "main_characters": "、".join(main_characters) if main_characters else "待定",
            "target_words": target_words,
            "chapter_count": chapter_count,
            "reference_text": reference_text or "无",
            "generation_type": generation_type
        }
        
        # 融合参考文本元素（V1.2新增）
        if parsed:
            variables = ReferenceFusion.fusion_to_outline_prompt(parsed, variables)
            if parsed.has_characters():
                existing_chars = [c.name for c in parsed.characters if c.name]
                if existing_chars and variables.get("main_characters") == "待定":
                    variables["main_characters"] = "、".join(existing_chars[:5])
            logger.info("已将参考元素融合到大纲Prompt中")
        
        system_prompt, user_prompt = self._render_prompt(template, variables)
        
        max_tokens_map = {"quick": 3000, "standard": 5000, "detailed": 8000}
        max_tokens = max_tokens_map.get(generation_type, 5000)
        
        response = self._call_llm(system_prompt, user_prompt, max_tokens=max_tokens)
        
        # 缓存生成结果
        self._generation_history["outline"] = response
        
        logger.info("大纲生成完成")
        
        return OutlineResult(
            title=theme,
            theme=theme,
            synopsis=response[:500] if len(response) > 500 else response,
            chapters=[{"content": response}]  # 简化处理，实际应解析章节
        )
    
    def generate_character(
        self,
        character_name: str,
        role: str = "主角",
        worldview_summary: str = "",
        personality_keywords: List[str] = None,
        reference_text: str = "",
        generation_type: str = "standard"
    ) -> CharacterResult:
        """
        生成人物设定
        
        Args:
            character_name: 人物名称
            role: 角色定位
            worldview_summary: 世界观概述
            personality_keywords: 性格关键词
            reference_text: 参考文本
            generation_type: 生成详细程度
            
        Returns:
            人物数据
        """
        logger.info(f"开始生成人物: name={character_name}, role={role}")
        
        # 解析参考文本（V1.2增强）
        parsed = None
        if reference_text and self._reference_parser:
            parsed = self._reference_parser.parse(reference_text)
            logger.info(f"参考文本解析完成: confidence={parsed.confidence:.2f}")
        
        template = self._prompt_templates["character"]
        
        # 准备Prompt变量
        variables = {
            "character_name": character_name,
            "role": role,
            "worldview_summary": worldview_summary or self._get_worldview_summary(),
            "personality_keywords": "、".join(personality_keywords) if personality_keywords else "由AI自由发挥",
            "reference_text": reference_text or "无",
            "generation_type": generation_type
        }
        
        # 融合参考文本元素（V1.2新增）
        if parsed:
            variables = ReferenceFusion.fusion_to_character_prompt(parsed, variables)
            # 如果参考文本中有同名人物，优先使用其设定
            if parsed.has_characters():
                for ref_char in parsed.characters:
                    if ref_char.name == character_name:
                        if ref_char.personality and not personality_keywords:
                            variables["personality_keywords"] = "、".join(ref_char.personality[:3])
                        if ref_char.abilities:
                            logger.info(f"发现同名参考人物 {character_name}，已融合其设定")
                        break
            logger.info("已将参考人物元素融合到Prompt中")
        
        system_prompt, user_prompt = self._render_prompt(template, variables)
        
        max_tokens_map = {"quick": 2000, "standard": 3000, "detailed": 5000}
        max_tokens = max_tokens_map.get(generation_type, 3000)
        
        response = self._call_llm(system_prompt, user_prompt, max_tokens=max_tokens)
        character_dict = self._parse_json_response(response)
        
        # 缓存生成结果
        if "characters" not in self._generation_history:
            self._generation_history["characters"] = {}
        self._generation_history["characters"][character_name] = character_dict
        
        logger.info(f"人物生成完成: {character_name}")
        
        personality = character_dict.get("personality", {})
        
        return CharacterResult(
            name=character_dict.get("name", character_name),
            role=character_dict.get("role", role),
            age=character_dict.get("age", ""),
            gender=character_dict.get("gender", ""),
            appearance=character_dict.get("appearance", ""),
            personality=personality.get("core", "") if isinstance(personality, dict) else str(personality),
            background=character_dict.get("background", ""),
            abilities=character_dict.get("abilities", []),
            goals=character_dict.get("goals", []),
            weaknesses=character_dict.get("weaknesses", []),
            relationships=character_dict.get("relationships", {}),
            character_arc=character_dict.get("arc", "")
        )
    
    def generate_plot(
        self,
        outline_summary: str,
        characters: List[str] = None,
        plot_type: str = "高潮",
        key_event: str = "",
        worldview_summary: str = "",
        reference_text: str = "",
        generation_type: str = "standard"
    ) -> PlotResult:
        """
        生成关键情节
        
        Args:
            outline_summary: 大纲概述
            characters: 涉及人物
            plot_type: 情节类型
            key_event: 关键事件
            worldview_summary: 世界观概述
            reference_text: 参考文本
            generation_type: 生成详细程度
            
        Returns:
            情节数据
        """
        logger.info(f"开始生成情节: type={plot_type}")
        
        # 解析参考文本（V1.2增强）
        parsed = None
        if reference_text and self._reference_parser:
            parsed = self._reference_parser.parse(reference_text)
            logger.info(f"参考文本解析完成: confidence={parsed.confidence:.2f}")
        
        template = self._prompt_templates["plot"]
        
        # 准备Prompt变量
        variables = {
            "outline_summary": outline_summary or self._get_outline_summary(),
            "characters": "、".join(characters) if characters else "待定",
            "plot_type": plot_type,
            "key_event": key_event or "由AI自由设计",
            "worldview_summary": worldview_summary or self._get_worldview_summary(),
            "reference_text": reference_text or "无",
            "generation_type": generation_type
        }
        
        # 融合参考文本元素（V1.2新增）
        if parsed:
            variables = ReferenceFusion.fusion_to_plot_prompt(parsed, variables)
            # 如果参考文本中有情节元素，优先使用
            if parsed.has_plot() and not key_event:
                if parsed.plot.events:
                    variables["key_event"] = parsed.plot.events[0].get("description", "由AI自由设计")
            logger.info("已将参考情节元素融合到Prompt中")
        
        system_prompt, user_prompt = self._render_prompt(template, variables)
        
        max_tokens_map = {"quick": 2000, "standard": 3000, "detailed": 5000}
        max_tokens = max_tokens_map.get(generation_type, 3000)
        
        response = self._call_llm(system_prompt, user_prompt, max_tokens=max_tokens)
        plot_dict = self._parse_json_response(response)
        
        # 缓存生成结果
        if "plots" not in self._generation_history:
            self._generation_history["plots"] = []
        self._generation_history["plots"].append(plot_dict)
        
        logger.info("情节生成完成")
        
        return PlotResult(
            plot_name=plot_dict.get("title", ""),
            plot_type=plot_dict.get("type", plot_type),
            participants=plot_dict.get("characters_involved", characters or []),
            setting="",
            beginning=plot_dict.get("setup", ""),
            development=plot_dict.get("development", ""),
            climax=plot_dict.get("climax", ""),
            resolution=plot_dict.get("resolution", ""),
            conflicts=[],
            turning_points=[],
            foreshadowing=plot_dict.get("foreshadowing", [])
        )
    
    def generate_all(
        self,
        request: QuickCreationRequest
    ) -> QuickCreationResult:
        """
        统一生成入口 - 生成全部设定
        
        确保各设定间协调一致：
        1. 先生成世界观（其他设定依赖于此）
        2. 基于世界观生成大纲
        3. 基于世界观和大纲生成人物
        4. 基于以上生成关键情节
        
        Args:
            request: 快捷创作请求
            
        Returns:
            快捷创作结果
        """
        logger.info(f"开始全部生成: keywords={request.keywords}")
        
        results = QuickCreationResult(
            keywords=request.keywords,
            target=request.target
        )
        
        try:
            # 1. 生成世界观
            if request.target in ["worldview", "all"]:
                worldview = self.generate_worldview(
                    keywords=request.keywords.split("、") if request.keywords else [],
                    reference_text=request.reference_text or "",
                    genre=request.genre or "玄幻",
                    generation_type=request.detailed_level
                )
                results.worldview = worldview
            
            # 2. 生成大纲（依赖世界观）
            if request.target in ["outline", "all"]:
                worldview_summary = self._get_worldview_summary()
                outline = self.generate_outline(
                    theme=request.keywords,
                    worldview_summary=worldview_summary,
                    main_characters=[],
                    target_words=request.chapter_count * request.word_count_per_chapter,
                    chapter_count=request.chapter_count,
                    reference_text=request.reference_text or "",
                    generation_type=request.detailed_level
                )
                results.outline = outline
            
            # 3. 生成人物（依赖世界观）
            if request.target in ["characters", "all"]:
                worldview_summary = self._get_worldview_summary()
                for i in range(request.character_count):
                    char_name = f"角色{i+1}" if i > 0 else "主角"
                    character = self.generate_character(
                        character_name=char_name,
                        role="主角" if i == 0 else "配角",
                        worldview_summary=worldview_summary,
                        personality_keywords=[],
                        reference_text=request.reference_text or "",
                        generation_type=request.detailed_level
                    )
                    if results.characters is None:
                        results.characters = []
                    results.characters.append(character)
            
            # 4. 生成关键情节（依赖以上所有）
            if request.target in ["plot", "all"]:
                worldview_summary = self._get_worldview_summary()
                outline_summary = self._get_outline_summary()
                character_names = [c.name for c in (results.characters or [])]
                
                # 生成几个关键情节类型
                plot = self.generate_plot(
                    outline_summary=outline_summary,
                    characters=character_names,
                    plot_type="主线",
                    key_event="",
                    worldview_summary=worldview_summary,
                    reference_text=request.reference_text or "",
                    generation_type=request.detailed_level
                )
                results.plot = plot
            
            results.success = True
            results.error = None
            
        except Exception as e:
            results.success = False
            results.error = f"生成失败: {str(e)}"
            logger.error(f"全部生成失败: {e}")
        
        logger.info(f"全部生成完成: success={results.success}")
        return results
    
    # ==================== 辅助方法 ====================
    
    def _get_worldview_summary(self) -> str:
        """获取世界观概述（从缓存）"""
        if "worldview" in self._generation_history:
            wv = self._generation_history["worldview"]
            return f"{wv.get('world_name', '')}：{wv.get('social_structure', '')}"
        return ""
    
    def _get_outline_summary(self) -> str:
        """获取大纲概述（从缓存）"""
        if "outline" in self._generation_history:
            # 取前500字符作为摘要
            outline = self._generation_history["outline"]
            return outline[:500] if len(outline) > 500 else outline
        return ""
    
    def get_available_creation_types(self) -> Dict[str, str]:
        """获取可用的创作类型"""
        return {
            "worldview": "世界观设定",
            "outline": "章节大纲",
            "character": "人物设定",
            "plot": "关键情节",
            "all": "全部生成"
        }
    
    def get_generation_types(self) -> Dict[str, str]:
        """获取生成详细程度选项"""
        return {
            "quick": "快速生成（较少细节）",
            "standard": "标准生成",
            "detailed": "详细生成"
        }
    
    def parse_reference_text(self, text: str) -> Dict[str, Any]:
        """
        解析参考文本并返回解析结果（V1.2新增）
        
        用于预览参考文本中提取的元素，帮助用户了解
        系统从参考文本中识别了哪些世界观、人物、情节元素。
        
        Args:
            text: 参考文本内容
            
        Returns:
            解析结果字典，包含worldview、characters、plot等元素
        """
        if not text or not self._reference_parser:
            return {"error": "参考文本为空或解析器未初始化"}
        
        parsed = self._reference_parser.parse(text)
        
        return {
            "reference_type": parsed.reference_type.value,
            "confidence": parsed.confidence,
            "worldview": parsed.worldview.to_dict() if parsed.has_worldview() else None,
            "characters": [c.to_dict() for c in parsed.characters] if parsed.has_characters() else [],
            "plot": parsed.plot.to_dict() if parsed.has_plot() else None,
            "style_keywords": parsed.style_keywords,
            "summary": {
                "has_worldview": parsed.has_worldview(),
                "has_characters": parsed.has_characters(),
                "has_plot": parsed.has_plot(),
                "character_count": len(parsed.characters),
                "style_count": len(parsed.style_keywords)
            }
        }
    
    def clear_cache(self) -> None:
        """清除生成缓存"""
        self._generation_history.clear()
        logger.info("生成缓存已清除")
    
    # ==================== V1.1新增：缓存持久化 ====================
    
    def save_cache_to_disk(self) -> bool:
        """
        将生成缓存保存到磁盘
        
        返回:
            是否保存成功
        """
        if not self._generation_history or not self._cache_file:
            return False
        
        try:
            # 确保目录存在
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 序列化缓存
            cache_data = {
                "version": "1.1",
                "timestamp": datetime.now().isoformat(),
                "generation_history": self._generation_history
            }
            
            # 写入文件
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"缓存已保存到: {self._cache_file}")
            return True
            
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")
            return False
    
    def _load_cache_from_disk(self) -> bool:
        """
        从磁盘加载生成缓存
        
        返回:
            是否加载成功
        """
        if not self._cache_file or not self._cache_file.exists():
            return False
        
        try:
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 验证版本
            if cache_data.get("version") != "1.1":
                logger.debug("缓存版本不匹配，跳过加载")
                return False
            
            # 恢复缓存
            self._generation_history = cache_data.get("generation_history", {})
            
            logger.debug(f"缓存已从磁盘加载")
            return True
            
        except Exception as e:
            logger.warning(f"加载缓存失败: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        返回:
            缓存统计字典
        """
        return {
            "worldview_cached": "worldview" in self._generation_history,
            "outline_cached": "outline" in self._generation_history,
            "characters_count": len(self._generation_history.get("characters", {})),
            "plots_count": len(self._generation_history.get("plots", [])),
            "cache_file": str(self._cache_file) if self._cache_file else None
        }
    
    def execute(self, request: QuickCreationRequest) -> QuickCreationResult:
        """
        执行插件主功能
        
        Args:
            request: 快捷创作请求
            
        Returns:
            快捷创作结果
        """
        return self.generate_all(request)
    
    def shutdown(self) -> bool:
        """关闭插件"""
        # 保存缓存到磁盘
        self.save_cache_to_disk()
        
        self._generation_history.clear()
        self._state = PluginState.UNLOADED
        logger.info("快捷创作插件已关闭")
        return True
    
    # ==================== V1.3新增：结果保存与导入 ====================
    
    def save_result_to_project(
        self,
        result: QuickCreationResult,
        project_name: str = "新建项目",
        output_path: Optional[str] = None,
        format: str = "json"
    ) -> str:
        """
        保存生成结果到新项目文件
        
        参数:
            result: 快捷创作结果
            project_name: 项目名称
            output_path: 输出路径（可选）
            format: 保存格式（json/markdown）
            
        返回:
            项目目录路径
        """
        if not self._storage_manager:
            self._storage_manager = ResultStorageManager()
        
        from pathlib import Path
        save_path = Path(output_path) if output_path else None
        
        return str(self._storage_manager.save_result(
            result, 
            project_name, 
            save_path, 
            format
        ))
    
    def import_to_current_project(
        self,
        result: QuickCreationResult,
        conflict_strategy: str = "keep_original",
        merge_mode: str = "append"
    ) -> ImportResult:
        """
        将生成结果导入到当前项目
        
        参数:
            result: 快捷创作结果
            conflict_strategy: 冲突处理策略
                - keep_original: 保留原有设定（默认）
                - overwrite: 覆盖原有设定
                - merge: 合并设定
                - rename_new: 重命名新设定
            merge_mode: 合并模式（append追加/replace替换）
            
        返回:
            ImportResult对象，包含导入结果详情
        """
        if not self._storage_manager:
            return ImportResult(
                success=False,
                imported_items=[],
                conflicts=[],
                error="存储管理器未初始化"
            )
        
        strategy = ConflictStrategy(conflict_strategy)
        return self._storage_manager.import_to_project(
            result, 
            strategy, 
            merge_mode
        )
    
    def set_storage_project_path(self, path: str) -> None:
        """设置存储管理器的项目路径"""
        if not self._storage_manager:
            self._storage_manager = ResultStorageManager()
        
        from pathlib import Path
        self._storage_manager.set_project_path(Path(path))
    
    def get_storage_project_summary(self) -> Dict[str, Any]:
        """获取当前项目存储摘要"""
        if not self._storage_manager:
            return {"error": "存储管理器未初始化"}
        
        return self._storage_manager.get_project_summary()
    
    def get_json_schemas(self) -> Dict[str, Any]:
        """获取所有JSON Schema定义"""
        return {
            "worldview": WORLDVIEW_SCHEMA,
            "outline": OUTLINE_SCHEMA,
            "character": CHARACTER_SCHEMA,
            "plot": PLOT_SCHEMA,
            "version": SCHEMA_VERSION
        }
    
    # =========================================================================
    # V1.5新增：Claw化增强方法
    # =========================================================================
    
    def _get_validator(self) -> Optional[Any]:
        """
        延迟获取评分器实例
        
        Returns:
            WeightedValidatorPlugin实例或None
        """
        if self._validator is None:
            try:
                from plugins.quality_validator_v1.plugin import QualityValidatorPlugin
                if self._context and hasattr(self._context, 'service_locator'):
                    self._validator = self._context.service_locator.get_service("quality_validator")
                if self._validator is None:
                    logger.debug("[QuickCreator] 评分器服务不可用")
            except Exception as e:
                logger.warning(f"[QuickCreator] 获取评分器失败: {e}")
        return self._validator
    
    def _get_session_manager(self) -> Optional[Any]:
        """
        延迟获取SESSION-STATE管理器（L1热记忆）
        
        Returns:
            SessionStateManager实例或None
        """
        if self._session_manager is None:
            try:
                from core.session_state import get_session_state_manager
                self._session_manager = get_session_state_manager()
                logger.debug("[QuickCreator] L1热记忆管理器初始化成功")
            except Exception as e:
                logger.warning(f"[QuickCreator] 获取L1热记忆管理器失败: {e}")
        return self._session_manager
    
    def _get_vector_store(self) -> Optional[Any]:
        """
        延迟获取向量存储（L2温记忆）
        
        Returns:
            NovelVectorStore实例或None
        """
        if self._vector_store is None:
            try:
                from infrastructure.vector_store import NovelVectorStore
                workspace_root = Path(__file__).parent.parent.parent
                self._vector_store = NovelVectorStore(
                    db_path=workspace_root / "data" / "vector_store"
                )
                logger.debug("[QuickCreator] L2温记忆向量存储初始化成功")
            except Exception as e:
                logger.warning(f"[QuickCreator] 获取L2温记忆失败: {e}")
        return self._vector_store
    
    def _get_git_notes_manager(self) -> Optional[Any]:
        """
        延迟获取Git-Notes管理器（L3冷记忆）
        
        Returns:
            GitNotesManager实例或None
        """
        if self._git_notes_manager is None:
            try:
                from core.git_notes_manager import get_git_notes_manager
                workspace_root = Path(__file__).parent.parent.parent
                self._git_notes_manager = get_git_notes_manager(workspace_root)
                logger.debug("[QuickCreator] L3冷记忆Git-Notes管理器初始化成功")
            except Exception as e:
                logger.warning(f"[QuickCreator] 获取L3冷记忆失败: {e}")
        return self._git_notes_manager
    
    def _evaluate_generation(self, result: Dict[str, Any], generation_type: str) -> float:
        """
        评估生成质量
        
        Args:
            result: 生成结果字典
            generation_type: 生成类型(worldview/outline/character/plot)
            
        Returns:
            总评分(0-1)
        """
        validator = self._get_validator()
        if validator is None:
            logger.debug("[QuickCreator] 评分器不可用，返回默认评分0.8")
            return 0.8
        
        try:
            # 构建验证请求
            content = result.get("content", "")
            if not content and isinstance(result, dict):
                # 尝试从字典中提取内容
                content = json.dumps(result, ensure_ascii=False)
            
            # 调用评分器
            validation_result = validator.validate_chapter(
                content=content,
                metadata={
                    "generation_type": generation_type,
                    "word_count": len(content)
                }
            )
            
            score = getattr(validation_result, 'total_score', 0.8)
            logger.info(f"[QuickCreator] {generation_type}生成评分: {score:.2f}")
            return score
            
        except Exception as e:
            logger.warning(f"[QuickCreator] 评分失败: {e}，返回默认评分0.8")
            return 0.8
    
    def _record_to_l1(self, generation_type: str, result: Dict[str, Any], score: float):
        """
        记录生成结果到L1热记忆
        
        Args:
            generation_type: 生成类型
            result: 生成结果
            score: 评分
        """
        session_manager = self._get_session_manager()
        if session_manager is None:
            return
        
        try:
            # 设置活跃任务
            session_manager.set_active_task(
                function=f"快捷创作-{generation_type}",
                file="",
                operation=f"生成{generation_type}内容",
                task_id=f"quick-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            
            # WAL协议：AI调用前写入
            session_manager.write_before_ai_call({
                "generation_type": generation_type,
                "score": score,
                "timestamp": datetime.now().isoformat()
            })
            
            # 记录评分
            session_manager.record_score(score)
            
            logger.debug(f"[QuickCreator] L1热记忆记录完成: {generation_type}")
            
        except Exception as e:
            logger.warning(f"[QuickCreator] L1热记忆记录失败: {e}")
    
    def _save_to_l2(self, result: Dict[str, Any], generation_type: str):
        """
        保存生成结果到L2温记忆（向量存储）
        
        Args:
            result: 生成结果
            generation_type: 生成类型
        """
        vector_store = self._get_vector_store()
        if vector_store is None:
            return
        
        try:
            content = result.get("content", "")
            if not content:
                content = json.dumps(result, ensure_ascii=False)
            
            # 根据类型选择存储方式
            if generation_type == "worldview":
                vector_store.add_knowledge(
                    knowledge_id=f"worldview-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    category="worldview",
                    domain="generated",
                    title=result.get("world_name", result.get("title", "世界观设定")),
                    content=content,
                    keywords=result.get("keywords", [])
                )
            elif generation_type == "character":
                vector_store.add_chapter(
                    chapter_id=f"character-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    content=content,
                    metadata={
                        "type": "character_profile",
                        "name": result.get("name", "未命名"),
                        "score": result.get("quality_score", 0.8)
                    }
                )
            
            logger.debug(f"[QuickCreator] L2温记忆存储完成: {generation_type}")
            
        except Exception as e:
            logger.warning(f"[QuickCreator] L2温记忆存储失败: {e}")
    
    def _record_to_l3(self, generation_type: str, result: Dict[str, Any], 
                       score: float, retry_count: int):
        """
        记录生成决策到L3冷记忆（Git-Notes）
        
        Args:
            generation_type: 生成类型
            result: 生成结果
            score: 评分
            retry_count: 重试次数
        """
        git_notes = self._get_git_notes_manager()
        if git_notes is None:
            return
        
        try:
            if score >= self.HIGH_QUALITY_THRESHOLD:
                # 高质量生成记录为里程碑
                git_notes.record_milestone(
                    title=f"高质量{generation_type}生成",
                    content=f"生成类型: {generation_type}, 评分: {score:.2f}, 重试次数: {retry_count}"
                )
            elif retry_count >= self.MAX_RETRY_COUNT:
                # 多次重试记录为经验教训
                git_notes.record_lesson(
                    title=f"{generation_type}生成多次重试",
                    content=f"生成类型: {generation_type}, 最终评分: {score:.2f}, 建议: 检查参考文本质量"
                )
            
            logger.debug(f"[QuickCreator] L3冷记忆记录完成: {generation_type}")
            
        except Exception as e:
            logger.warning(f"[QuickCreator] L3冷记忆记录失败: {e}")
    
    def _check_l4_trigger(self, generation_type: str) -> bool:
        """
        检查是否触发L4档案更新
        
        触发条件：连续3次评分≥0.9
        
        Args:
            generation_type: 生成类型
            
        Returns:
            是否触发L4更新
        """
        if generation_type not in self._score_history:
            self._score_history[generation_type] = []
        
        recent_scores = self._score_history[generation_type][-3:]
        return len(recent_scores) >= 3 and all(s >= self.HIGH_QUALITY_THRESHOLD for s in recent_scores)
    
    def _update_l4_memory(self, generation_type: str, result: Dict[str, Any]):
        """
        更新L4档案（MEMORY.md）
        
        注意：慎用，只在重要发现时更新
        
        Args:
            generation_type: 生成类型
            result: 生成结果
        """
        try:
            memory_path = Path(__file__).parent.parent.parent / "Memory-Novel Writing Assistant-Agent Pro" / "MEMORY.md"
            
            if not memory_path.exists():
                return
            
            # 追加模式更新
            with open(memory_path, 'a', encoding='utf-8') as f:
                f.write(f"\n## {generation_type}生成模式发现\n")
                f.write(f"- 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write(f"- 连续3次评分≥0.9\n")
                f.write(f"- 关键要素: {self._extract_key_elements(result)}\n")
            
            logger.info(f"[QuickCreator] L4档案更新完成: {generation_type}")
            
        except Exception as e:
            logger.warning(f"[QuickCreator] L4档案更新失败: {e}")
    
    def _extract_key_elements(self, result: Dict[str, Any]) -> str:
        """提取关键要素"""
        elements = []
        if "world_name" in result:
            elements.append(f"世界名: {result['world_name']}")
        if "name" in result:
            elements.append(f"角色名: {result['name']}")
        if "keywords" in result:
            elements.append(f"关键词: {', '.join(result['keywords'][:3])}")
        return " | ".join(elements) if elements else "无"
    
    def generate_with_claw(self, request: QuickCreationRequest) -> QuickCreationResult:
        """
        带Claw化增强的生成方法
        
        集成评分机制和四层记忆
        
        Args:
            request: 快捷创作请求
            
        Returns:
            快捷创作结果
        """
        generation_type = request.target if request.target != "all" else "all"
        
        # 1. 执行生成
        result = self.generate_all(request)
        
        if not result.success:
            return result
        
        # 2. 评分评估
        score = self._evaluate_generation(
            {"content": str(result.__dict__)},
            generation_type
        )
        
        # 3. 低分重试机制
        retry_count = 0
        while score < self.QUALITY_THRESHOLD and retry_count < self.MAX_RETRY_COUNT:
            # 重新生成
            result = self.generate_all(request)
            if not result.success:
                break
            
            score = self._evaluate_generation(
                {"content": str(result.__dict__)},
                generation_type
            )
            retry_count += 1
            logger.info(f"[QuickCreator] 重试{retry_count}/{self.MAX_RETRY_COUNT}, 评分: {score:.2f}")
        
        # 4. 记录评分历史
        if generation_type not in self._score_history:
            self._score_history[generation_type] = []
        self._score_history[generation_type].append(score)
        
        # 5. 四层记忆集成
        self._record_to_l1(generation_type, result.__dict__, score)
        self._save_to_l2(result.__dict__, generation_type)
        self._record_to_l3(generation_type, result.__dict__, score, retry_count)
        
        # 6. L4档案（仅在触发条件满足时）
        if self._check_l4_trigger(generation_type):
            self._update_l4_memory(generation_type, result.__dict__)
        
        # 7. 添加评分元数据
        result.quality_score = score
        result.retry_count = retry_count
        
        return result
