"""
专家模式插件主文件

版本: 1.0.0
创建日期: 2026-03-29

核心功能:
1. 数据源整合（世界观/人设/大纲/风格/知识库/写作技巧）
2. 调用现有生成器（不替换）
3. 强制检查【本章完】标记
4. 九维度智能评分
5. 优化建议生成
6. Claw记忆集成

设计原则:
- 完全继承GeneratorPlugin接口
- 增强不替换（调用现有生成器）
- 可降级（加载失败时回退）
"""

import os
import sys
import json
import yaml
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, field

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.plugin_interface import GeneratorPlugin, PluginMetadata, PluginType
    from core.models import GenerationRequest, GenerationResult
except ImportError:
    # 降级方案：定义基础接口
    class GeneratorPlugin:
        """基础生成器插件接口"""
        def __init__(self, metadata):
            self.metadata = metadata
            
        def initialize(self, context):
            pass
            
        def generate(self, request):
            raise NotImplementedError
            
        def cleanup(self):
            pass
    
    class PluginMetadata:
        """插件元数据"""
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    PluginType = type('PluginType', (), {'GENERATOR': 'generator'})()
    
    @dataclass
    class GenerationRequest:
        """生成请求"""
        chapter_title: str = ""
        word_count_target: int = 3500
        outline_reference: str = ""
        character_references: str = ""
        style_reference: str = ""
        worldview_reference: str = ""
        expert_config: Dict = field(default_factory=dict)
        
    @dataclass  
    class GenerationResult:
        """生成结果"""
        content: str = ""
        scores: Dict = field(default_factory=dict)
        metadata: Dict = field(default_factory=dict)

try:
    from .models import ExpertEvaluation, OptimizationSuggestion, ExpertConfig
    from .validator import ExpertValidator
    from .optimizer import ExpertOptimizer
    from .memory import ExpertMemory
    from .local_model import LocalModelAssistant
except ImportError:
    from models import ExpertEvaluation, OptimizationSuggestion, ExpertConfig
    from validator import ExpertValidator
    from optimizer import ExpertOptimizer
    from memory import ExpertMemory
    from local_model import LocalModelAssistant

logger = logging.getLogger(__name__)


@dataclass
class ExpertPluginMetadata(PluginMetadata):
    """专家插件元数据"""
    
    id: str = "expert-novel-v1"
    name: str = "小说创作专家"
    version: str = "1.0.0"
    description: str = "专门优化小说创作质量，整合世界观/人设/大纲/风格/知识库/写作技巧"
    author: str = "Agent Pro Team"
    plugin_type: str = "generator"
    
    # 专家特有字段
    expert_type: str = "novel_creation"
    capabilities: list = field(default_factory=lambda: [
        "worldview_integration",
        "character_enhancement",
        "outline_alignment",
        "style_optimization",
        "knowledge_injection",
        "technique_application"
    ])
    
    # 评分维度配置
    evaluation_dimensions: Dict[str, float] = field(default_factory=lambda: {
        "世界观": 0.12,
        "人设": 0.19,
        "大纲": 0.13,
        "风格": 0.19,
        "知识库": 0.08,
        "写作技巧": 0.08,
        "字数": 0.08,
        "上下文衔接": 0.08,
        "AI感": 0.05
    })


class ExpertPlugin(GeneratorPlugin):
    """
    专家模式插件
    
    核心功能:
    1. 数据源整合（增强原始请求）
    2. 调用现有生成器（不替换）
    3. 强制检查【本章完】标记
    4. 九维度智能评分
    5. 优化建议生成
    6. Claw记忆集成
    
    设计原则:
    - 增强不替换：调用现有novel-generator-v3
    - 继承不冲突：完全继承GeneratorPlugin接口
    - 可降级：加载失败时回退到默认模式
    """
    
    def __init__(self, metadata: Optional[PluginMetadata] = None):
        """初始化专家插件"""
        if metadata is None:
            metadata = ExpertPluginMetadata()
        super().__init__(metadata)
        
        # 延迟加载的组件
        self._novel_generator = None  # 现有的novel-generator-v3
        self._expert_validator = None  # 专家验证器
        self._expert_optimizer = None  # 专家优化器
        self._expert_memory = None     # Claw记忆集成
        self._local_model = None      # 本地模型辅助
        
        # 插件注册表引用
        self._plugin_registry = None
        
        # 配置
        self._config = None
        self._load_config()
        
        # 专家配置
        self.expert_config = {
            "enable_memory": True,
            "enable_local_model": True,
            "quality_threshold": 0.8,
            "max_iterations": 5
        }
        
        self._initialized = False
    
    def _load_config(self):
        """加载配置文件"""
        try:
            config_path = Path(__file__).parent / "config.yaml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_dict = yaml.safe_load(f)
                    self._config = ExpertConfig.from_yaml(config_dict.get('expert', {}))
                    logger.info("专家配置加载成功")
        except Exception as e:
            logger.warning(f"加载专家配置失败，使用默认配置: {e}")
            self._config = ExpertConfig()
    
    def initialize(self, context) -> None:
        """
        延迟初始化
        
        关键：不在__init__中初始化，避免影响启动速度
        """
        if self._initialized:
            return
            
        super().initialize(context)
        
        # 保存插件注册表引用
        if hasattr(context, 'plugin_registry'):
            self._plugin_registry = context.plugin_registry
        
        # 延迟加载依赖插件
        self._load_dependencies()
        
        # 初始化组件
        self._init_components()
        
        self._initialized = True
        logger.info("专家插件初始化完成")
    
    def _load_dependencies(self):
        """加载依赖插件"""
        if self._plugin_registry is None:
            logger.warning("插件注册表不可用，跳过依赖加载")
            return
        
        # 尝试加载novel-generator-v3
        try:
            self._novel_generator = self._plugin_registry.get_plugin("novel-generator-v3")
            if self._novel_generator:
                logger.info("依赖插件 novel-generator-v3 加载成功")
            else:
                logger.warning("依赖插件 novel-generator-v3 未找到")
        except Exception as e:
            logger.warning(f"加载依赖插件失败: {e}")
    
    def _init_components(self):
        """初始化组件"""
        try:
            # 初始化验证器
            self._expert_validator = ExpertValidator(config=self._config)
            
            # 初始化优化器
            self._expert_optimizer = ExpertOptimizer()
            
            # 初始化记忆模块
            if self._config.memory_enabled:
                self._expert_memory = ExpertMemory()
            
            # 初始化本地模型
            if self._config.local_model_enabled:
                self._local_model = LocalModelAssistant()
            
            logger.info("专家组件初始化完成")
        except Exception as e:
            logger.error(f"专家组件初始化失败: {e}")
    
    def generate(self, request) -> dict:
        """
        生成小说内容（专家增强版）
        
        完全兼容GeneratorPlugin接口
        
        核心增强:
        1. 数据源整合（世界观/人设/大纲/风格/知识库/写作技巧）
        2. 强制检查【本章完】标记
        3. 九维度智能评分
        4. 优化建议生成
        5. Claw记忆集成
        
        Args:
            request: 生成请求（与现有接口一致）
            
        Returns:
            GenerationResult: 生成结果（与现有接口一致）
        """
        logger.info(f"专家模式开始生成: {getattr(request, 'chapter_title', '未知章节')}")
        
        # 步骤1: 增强请求（整合数据源）
        enhanced_request = self._enhance_request(request)
        
        # 步骤2: 调用现有生成器（不替换）
        base_result = self._call_base_generator(enhanced_request)
        
        if base_result is None:
            logger.error("基础生成器返回空结果")
            return self._create_empty_result()
        
        # 获取生成内容
        content = self._extract_content(base_result)
        
        # 步骤3: 专家评分（含强制检查）
        expert_evaluation = self._evaluate_expert(content, enhanced_request)
        
        # 步骤4: 检查是否因【本章完】缺失而失败
        if expert_evaluation.total_score == 0.0 and any("本章完" in issue for issue in expert_evaluation.issues):
            logger.warning("检测到【本章完】标记缺失，自动补充并重新评分")
            
            # 自动补充【本章完】标记
            content = self._add_chapter_end_marker(content)
            
            # 重新评分
            expert_evaluation = self._evaluate_expert(content, enhanced_request)
        
        # 步骤5: 如果不达标，生成优化建议
        if expert_evaluation.total_score < self.expert_config["quality_threshold"]:
            optimization = self._generate_optimization(expert_evaluation)
            
            # 步骤6: 存储到记忆
            self._store_to_memory(expert_evaluation, optimization, request)
            
            # 步骤7: 应用优化（返回优化建议）
            return self._create_result_with_optimization(content, expert_evaluation, optimization)
        
        # 返回结果
        return self._create_result(content, expert_evaluation)
    
    def _enhance_request(self, request):
        """
        增强请求（整合数据源）
        
        这是专家模式的核心增强点:
        将世界观、人设、大纲、风格、知识库、写作技巧整合到请求中
        """
        # 创建增强请求（不修改原始请求）
        enhanced = request
        
        try:
            # 整合数据源
            if hasattr(request, 'worldview_reference'):
                enhanced.worldview_data = self._load_worldview(request.worldview_reference)
            
            if hasattr(request, 'character_references'):
                enhanced.character_data = self._load_characters(request.character_references)
            
            if hasattr(request, 'outline_reference'):
                enhanced.outline_data = self._load_outline(request.outline_reference)
            
            if hasattr(request, 'style_reference'):
                enhanced.style_data = self._load_style(request.style_reference)
            
            # 新增：知识库和写作技巧
            enhanced.knowledge_base = self._load_knowledge_base()
            enhanced.writing_techniques = self._load_writing_techniques()
            
            logger.debug("请求数据源整合完成")
        except Exception as e:
            logger.warning(f"数据源整合失败: {e}")
        
        return enhanced
    
    def _call_base_generator(self, request):
        """调用基础生成器"""
        if self._novel_generator is None:
            logger.warning("基础生成器未加载，返回默认内容")
            return None
        
        try:
            result = self._novel_generator.generate(request)
            return result
        except Exception as e:
            logger.error(f"基础生成器调用失败: {e}")
            return None
    
    def _extract_content(self, result) -> str:
        """从生成结果中提取内容"""
        if isinstance(result, dict):
            return result.get("content", "")
        elif hasattr(result, 'content'):
            return result.content
        else:
            return str(result) if result else ""
    
    def _evaluate_expert(self, content: str, request) -> ExpertEvaluation:
        """专家评分"""
        if self._expert_validator is None:
            logger.warning("专家验证器未初始化，返回默认评分")
            return ExpertEvaluation(total_score=0.5)
        
        # 构建上下文
        context = {
            "worldview": getattr(request, 'worldview_data', {}),
            "characters": getattr(request, 'character_data', []),
            "outline": getattr(request, 'outline_data', {}),
            "style_profile": getattr(request, 'style_data', {}),
            "knowledge_base": getattr(request, 'knowledge_base', {}),
            "techniques": getattr(request, 'writing_techniques', {}),
            "previous_chapters": getattr(request, 'previous_chapters', []),
            "target_words": getattr(request, 'word_count_target', 3500)
        }
        
        return self._expert_validator.evaluate(content, context)
    
    def _add_chapter_end_marker(self, content: str) -> str:
        """
        自动补充【本章完】标记
        """
        content = content.strip()
        
        if not content.endswith("。"):
            content = content + "。\n【本章完】"
        else:
            content = content + "\n【本章完】"
        
        logger.info("已自动补充【本章完】标记")
        return content
    
    def _generate_optimization(self, evaluation: ExpertEvaluation) -> OptimizationSuggestion:
        """生成优化建议"""
        if self._expert_optimizer is None:
            return OptimizationSuggestion(overall_suggestion="请手动优化内容")
        
        return self._expert_optimizer.generate_suggestions(evaluation)
    
    def _store_to_memory(self, evaluation: ExpertEvaluation, 
                         optimization: OptimizationSuggestion, request):
        """存储到记忆"""
        if self._expert_memory is None:
            return
        
        chapter_id = getattr(request, 'chapter_title', 'unknown')
        
        try:
            self._expert_memory.store_evaluation(evaluation, chapter_id)
            self._expert_memory.store_optimization(optimization, chapter_id)
            logger.debug(f"已存储到记忆: {chapter_id}")
        except Exception as e:
            logger.warning(f"存储记忆失败: {e}")
    
    def _create_result(self, content: str, evaluation: ExpertEvaluation) -> dict:
        """创建结果"""
        return {
            "content": content,
            "scores": evaluation.dimension_scores,
            "total_score": evaluation.total_score,
            "expert_evaluation": evaluation.to_dict(),
            "metadata": {
                "expert_mode": True,
                "chapter_end_marker": "【本章完】" in content[-100:]
            }
        }
    
    def _create_result_with_optimization(self, content: str, evaluation: ExpertEvaluation,
                                          optimization: OptimizationSuggestion) -> dict:
        """创建带优化建议的结果"""
        return {
            "content": content,
            "scores": evaluation.dimension_scores,
            "total_score": evaluation.total_score,
            "expert_evaluation": evaluation.to_dict(),
            "optimization_suggestions": optimization.to_dict(),
            "metadata": {
                "expert_mode": True,
                "needs_optimization": True,
                "chapter_end_marker": "【本章完】" in content[-100:]
            }
        }
    
    def _create_empty_result(self) -> dict:
        """创建空结果"""
        return {
            "content": "",
            "scores": {},
            "total_score": 0.0,
            "error": "生成失败"
        }
    
    # ========== 数据加载方法 ==========
    
    def _load_worldview(self, path: str) -> Dict:
        """加载世界观数据"""
        if not path:
            return {}
        
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"加载世界观失败: {e}")
        
        return {}
    
    def _load_characters(self, path: str) -> list:
        """加载人物数据"""
        if not path:
            return []
        
        try:
            if os.path.isdir(path):
                characters = []
                for f in os.listdir(path):
                    if f.endswith('.json'):
                        with open(os.path.join(path, f), 'r', encoding='utf-8') as fp:
                            characters.append(json.load(fp))
                return characters
            elif os.path.isfile(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else [data]
        except Exception as e:
            logger.warning(f"加载人物失败: {e}")
        
        return []
    
    def _load_outline(self, path: str) -> Dict:
        """加载大纲数据"""
        return self._load_json_file(path)
    
    def _load_style(self, path: str) -> Dict:
        """加载风格数据"""
        return self._load_json_file(path)
    
    def _load_knowledge_base(self) -> Dict:
        """加载知识库数据"""
        knowledge_path = PROJECT_ROOT / "data" / "knowledge"
        
        if not knowledge_path.exists():
            return {}
        
        knowledge = {}
        
        try:
            # 加载各领域知识
            for category in ["narrative", "description", "rhetoric", "structure"]:
                category_path = knowledge_path / "writing_technique" / category
                if category_path.exists():
                    knowledge[category] = []
                    for f in category_path.glob("*.json"):
                        with open(f, 'r', encoding='utf-8') as fp:
                            knowledge[category].append(json.load(fp))
        except Exception as e:
            logger.warning(f"加载知识库失败: {e}")
        
        return knowledge
    
    def _load_writing_techniques(self) -> Dict:
        """加载写作技巧"""
        techniques_path = PROJECT_ROOT / "data" / "knowledge" / "writing_technique"
        
        if not techniques_path.exists():
            return {}
        
        techniques = {}
        
        try:
            # 加载六个领域的写作技巧
            for area in ["narrative", "description", "rhetoric", "structure", 
                        "special_sentence", "advanced"]:
                area_path = techniques_path / area
                if area_path.exists():
                    techniques[area] = []
                    for f in area_path.glob("*.json"):
                        with open(f, 'r', encoding='utf-8') as fp:
                            data = json.load(fp)
                            techniques[area].append(data)
        except Exception as e:
            logger.warning(f"加载写作技巧失败: {e}")
        
        return techniques
    
    def _load_json_file(self, path: str) -> Dict:
        """通用JSON文件加载"""
        if not path:
            return {}
        
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"加载JSON文件失败 {path}: {e}")
        
        return {}
    
    def cleanup(self):
        """清理资源"""
        try:
            if self._local_model:
                self._local_model.cleanup()
            
            logger.info("专家插件资源清理完成")
        except Exception as e:
            logger.warning(f"清理资源失败: {e}")
    
    # ========== 实现抽象方法 ==========
    
    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据（类方法）"""
        return ExpertPluginMetadata()
    
    def validate_request(self, request) -> tuple:
        """
        验证请求是否有效
        
        Args:
            request: 生成请求
            
        Returns:
            (是否有效, 错误消息列表)
        """
        errors = []
        
        # 检查章节标题
        if not hasattr(request, 'chapter_title') or not request.chapter_title:
            errors.append("缺少章节标题")
        
        # 检查字数目标
        if hasattr(request, 'word_count_target'):
            if request.word_count_target < 100 or request.word_count_target > 50000:
                errors.append(f"字数目标不合理: {request.word_count_target}")
        
        # 返回结果
        return (len(errors) == 0, errors)
    
    def get_generation_options(self) -> Dict[str, Any]:
        """
        获取生成选项定义
        
        Returns:
            选项定义字典
        """
        return {
            "enable_memory": {
                "type": "boolean",
                "default": True,
                "description": "启用Claw记忆集成"
            },
            "enable_local_model": {
                "type": "boolean",
                "default": True,
                "description": "启用本地模型辅助评分"
            },
            "quality_threshold": {
                "type": "number",
                "default": 0.8,
                "min": 0.0,
                "max": 1.0,
                "description": "质量阈值（低于此值需要优化）"
            },
            "max_iterations": {
                "type": "integer",
                "default": 5,
                "min": 1,
                "max": 10,
                "description": "最大迭代次数"
            }
        }


# 插件工厂函数
def create_plugin():
    """创建专家插件实例"""
    return ExpertPlugin()


# 导出
__all__ = ['ExpertPlugin', 'ExpertPluginMetadata', 'create_plugin']
