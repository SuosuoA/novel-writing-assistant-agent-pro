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

# 动态导入专家模块（V1.49.6修复：先注册models，再加载依赖它的模块）
def _import_expert_modules():
    """动态导入专家模块，确保依赖顺序正确"""
    import importlib.util
    
    # 获取当前插件目录
    plugin_dir = Path(__file__).parent
    
    # 需要导入的模块列表（按依赖顺序）
    modules_to_import = [
        # 第一步：导入基础模块（无依赖）
        ('models', ['ExpertEvaluation', 'OptimizationSuggestion', 'ExpertConfig']),
        ('skill_integration', ['get_skill_manager']),
        # 第二步：导入依赖models的模块
        ('validator', ['ExpertValidator']),
        ('optimizer', ['ExpertOptimizer']),
        ('memory', ['ExpertMemory']),
        ('local_model', ['LocalModelAssistant']),
    ]
    
    imported = {}
    
    for module_name, classes in modules_to_import:
        module_path = plugin_dir / f"{module_name}.py"
        if module_path.exists():
            try:
                # 使用统一的模块ID（方便其他模块导入）
                module_id = f"expert_novel_v1_{module_name}"
                
                # 如果模块已加载，直接使用
                if module_id in sys.modules:
                    module = sys.modules[module_id]
                else:
                    # 加载模块
                    spec = importlib.util.spec_from_file_location(
                        module_id,
                        module_path
                    )
                    module = importlib.util.module_from_spec(spec)
                    
                    # 注册到sys.modules（关键：让其他模块可以导入）
                    sys.modules[module_id] = module
                    sys.modules[f"plugins.expert-novel-v1.{module_name}"] = module
                    
                    spec.loader.exec_module(module)
                
                # 提取所需的类
                for cls_name in classes:
                    if hasattr(module, cls_name):
                        imported[cls_name] = getattr(module, cls_name)
                    else:
                        print(f"[专家插件警告] 模块 {module_name} 中未找到类 {cls_name}")
                        
            except Exception as e:
                print(f"[专家插件错误] 导入模块 {module_name} 失败: {e}")
                import traceback
                traceback.print_exc()
    
    return imported

# 执行导入
_expert_modules = _import_expert_modules()
ExpertEvaluation = _expert_modules.get('ExpertEvaluation')
OptimizationSuggestion = _expert_modules.get('OptimizationSuggestion')
ExpertConfig = _expert_modules.get('ExpertConfig')
ExpertValidator = _expert_modules.get('ExpertValidator')
ExpertOptimizer = _expert_modules.get('ExpertOptimizer')
ExpertMemory = _expert_modules.get('ExpertMemory')
LocalModelAssistant = _expert_modules.get('LocalModelAssistant')
get_skill_manager = _expert_modules.get('get_skill_manager')

logger = logging.getLogger(__name__)


@dataclass
class ExpertPluginMetadata(PluginMetadata):
    """专家插件元数据"""
    
    id: str = "expert-novel-v1"
    name: str = "小说创作专家"
    version: str = "1.0.0"
    description: str = "专门优化小说创作质量，整合世界观/人设/大纲/风格/知识库/写作技巧"
    author: str = "Agent Pro Team"
    plugin_type: PluginType = PluginType.GENERATOR  # V1.49.6修复：使用枚举而非字符串
    
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
        
        # V1.49.19修复：EventBus引用
        self._event_bus = None
        
        # 配置
        self._config = None
        self._load_config()
        
        # 专家配置
        self.expert_config = {
            "enable_memory": True,
            "enable_local_model": True,
            # V10.0修复(P1-2)：阈值从0.8降至0.75
            # 原因（V9.3诊断）：旧评分体系理论上限仅~0.76，0.8永远无法达标
            # V10.0已重写风格/人设评分算法后，理论上限提升至~0.83
            # 但保留0.75以提供合理容差，避免因个别维度波动导致空转
            "quality_threshold": 0.75,
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
        
        # V1.49.19修复：获取EventBus
        if hasattr(context, 'event_bus'):
            self._event_bus = context.event_bus
        else:
            # 尝试从ServiceLocator获取
            try:
                from core.service_locator import ServiceLocator
                self._event_bus = ServiceLocator.get("event_bus")
            except Exception as e:
                logger.warning(f"无法获取EventBus: {e}")
                self._event_bus = None
        
        # 延迟加载依赖插件
        self._load_dependencies()
        
        # 初始化组件
        self._init_components()
        
        self._initialized = True
        logger.info("专家插件初始化完成")
    
    def _load_dependencies(self):
        """加载依赖插件
        
        V1.49.27修复：
        - 先加载novel-generator-v3的依赖插件（context-builder-v1, iterative-generator-v2）
        - 然后加载novel-generator-v3
        """
        if self._plugin_registry is None:
            logger.warning("插件注册表不可用，跳过依赖加载")
            return
        
        # V1.49.27修复：先加载novel-generator-v3的依赖插件
        novel_gen_dependencies = ["context-builder-v1", "iterative-generator-v2", "quality-validator-v1"]
        for dep_id in novel_gen_dependencies:
            try:
                dep_plugin = self._plugin_registry.get_plugin(dep_id)
                if not dep_plugin:
                    logger.info(f"加载依赖插件的依赖: {dep_id}...")
                    success, error = self._plugin_registry.load_plugin_runtime(dep_id)
                    if success:
                        self._plugin_registry.activate(dep_id)
                        logger.info(f"依赖插件 {dep_id} 加载并激活成功")
                    else:
                        logger.warning(f"依赖插件 {dep_id} 加载失败: {error}")
            except Exception as e:
                logger.warning(f"加载依赖插件 {dep_id} 失败: {e}")
        
        # 尝试加载novel-generator-v3
        try:
            self._novel_generator = self._plugin_registry.get_plugin("novel-generator-v3")
            if self._novel_generator:
                logger.info("依赖插件 novel-generator-v3 加载成功")
            else:
                # V1.49.23修复：尝试动态加载
                logger.info("依赖插件 novel-generator-v3 未激活，尝试动态加载...")
                
                # 检查插件是否已注册但未激活
                plugin_info = self._plugin_registry.get_plugin_info("novel-generator-v3")
                if plugin_info:
                    # 插件已注册，尝试激活
                    if self._plugin_registry.activate("novel-generator-v3"):
                        self._novel_generator = self._plugin_registry.get_plugin("novel-generator-v3")
                        if self._novel_generator:
                            logger.info("依赖插件 novel-generator-v3 激活成功")
                        else:
                            # 激活成功但获取实例失败，检查插件实例
                            logger.warning(f"依赖插件 novel-generator-v3 激活成功但实例为空，状态: {plugin_info.state}")
                    else:
                        # 激活失败，检查当前状态
                        logger.warning(f"依赖插件 novel-generator-v3 激活失败，当前状态: {plugin_info.state}")
                        # 如果已经是ACTIVE状态，直接获取
                        if plugin_info.state == "active":
                            self._novel_generator = self._plugin_registry.get_plugin("novel-generator-v3")
                            if self._novel_generator:
                                logger.info("依赖插件 novel-generator-v3 已是ACTIVE状态，获取成功")
                else:
                    # 插件未注册，尝试运行时加载
                    success, error = self._plugin_registry.load_plugin_runtime("novel-generator-v3")
                    if success:
                        # V1.49.24修复：加载成功后需要激活
                        if self._plugin_registry.activate("novel-generator-v3"):
                            self._novel_generator = self._plugin_registry.get_plugin("novel-generator-v3")
                            logger.info("依赖插件 novel-generator-v3 运行时加载并激活成功")
                        else:
                            # 激活失败，尝试直接获取（可能已经是ACTIVE状态）
                            self._novel_generator = self._plugin_registry.get_plugin("novel-generator-v3")
                            if self._novel_generator:
                                logger.info("依赖插件 novel-generator-v3 已处于可用状态")
                            else:
                                logger.warning("依赖插件 novel-generator-v3 激活失败")
                    else:
                        logger.warning(f"依赖插件 novel-generator-v3 运行时加载失败: {error}")
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
    
    def generate(self, request) -> 'GenerationResult':
        """
        生成小说内容（专家增强版） - 完整7步迭代循环
        
        V1.49.36核心重构：实现完整迭代优化循环（对标iterative-generator-v2的generate_with_iteration）
        
        设计流程：
          Step 1: 数据打包（世界观/风格/大纲/人物/知识库/技巧/上下文/字数要求/【本章完】标记）
          Step 2: 发送API请求 → 接收文章
          Step 3: 九维度评分（总分+各维度分+切实可行的修改方案）
          Step 4-5: 不达标 → 带反馈再次请求（循环，≤max_iterations次）
          Step 6: 达标输出成果（或达到迭代上限时输出最佳结果）
          Step 7: 总结经验输入Claw化记忆(mem9)，用于自我优化
        
        兼容性：
        - 返回标准GenerationResult（V2.0合规）
        - GUI只负责显示，所有业务逻辑在插件层
        - 与iterative-generator-v2的generate_with_iteration()架构对齐
        
        Args:
            request: 生成请求（含worldview_config/character_profiles/outline/style_profile等属性）
            
        Returns:
            GenerationResult: 含validation_scores(九维度)、metadata(优化建议)等
        """
        # V6.1修复：优先从title获取章节名（GUI通过GenerationRequest.title传递"第X章"）
        chapter_title = getattr(request, 'chapter_title', None) or getattr(request, 'title', None) or '未知章节'
        quality_threshold = self.expert_config.get("quality_threshold", 0.75)
        max_iterations = self.expert_config.get("max_iterations", 5)
        
        logger.info(f"[专家模式] ========== 开始7步迭代生成流程 ==========")
        logger.info(f"[专家模式] 章节: {chapter_title}, 阈值: {quality_threshold}, 最大迭代: {max_iterations}")
        
        # 发布开始事件
        self._publish_event("generation.started", {
            "chapter": chapter_title,
            "mode": "expert"
        })
        
        # P0修复：从请求中获取专家配置，覆盖默认值
        if hasattr(request, 'expert_config') and request.expert_config:
            self.expert_config.update(request.expert_config)
            quality_threshold = self.expert_config.get("quality_threshold", 0.75)
            max_iterations = self.expert_config.get("max_iterations", 5)
            # V6.1修复：确保max_iterations不超过合理上限（防止UI与实际不一致）
            # 同时检查request上是否有独立的max_iterations字段（优先使用GUI设置值）
            if hasattr(request, 'max_iterations') and request.max_iterations:
                gui_max_iter = request.max_iterations
                if gui_max_iter != max_iterations:
                    logger.warning(f"[专家模式] ⚠️ 迭代次数不一致: GUI={gui_max_iter}, expert_config={max_iterations}, 使用GUI值")
                    max_iterations = gui_max_iter
                    self.expert_config["max_iterations"] = max_iterations
            logger.info(f"专家配置已更新: threshold={quality_threshold}, max_iter={max_iterations}")
        
        # ===== Step 1: 打包数据（数据源整合）=====
        self._publish_event("pipeline.stage_started", {"stage": "Step1-数据打包整合", "progress": 0.05})
        
        enhanced_request = self._enhance_request(request)
        
        # 注入高级写作技巧指导（V1.5.0 TechniqueMonitor集成）
        technique_guidance = self._inject_technique_guidance(enhanced_request)
        if technique_guidance:
            enhanced_request.technique_guidance = technique_guidance
        
        # 记录数据整合状态供调试
        data_status = (
            f"世界观={'Y' if getattr(enhanced_request,'worldview_data',None) else 'N'} "
            f"人物={len(getattr(enhanced_request,'character_data',[])) or 0} "
            f"大纲={'Y' if getattr(enhanced_request,'outline_data',None) else 'N'} "
            f"风格={'Y' if getattr(enhanced_request,'style_data',None) else 'N'} "
            f"知识库={'Y' if getattr(enhanced_request,'knowledge_base',None) else 'N'} "
            f"技巧={'Y' if getattr(enhanced_request,'writing_techniques',None) else 'N'} "
            f"上下文={len(getattr(enhanced_request,'previous_chapters',[])) or 0}章"
        )
        logger.info(f"[专家模式][Step1] 数据打包完成: {data_status}")
        
        # 初始化迭代变量
        best_content = ""
        best_evaluation = None
        best_score = -1.0
        iteration_history = []
        last_feedback = ""
        target_words = getattr(request, 'word_count_target', None) or getattr(request, 'word_count', None) or 1400
        
        # ===== 迭代循环（Step 2~5）=====
        for iteration in range(max_iterations):
            iter_num = iteration + 1
            iter_progress = 0.1 + (0.75 * (iteration + 1) / max_iterations)
            
            logger.info(f"[专家模式] --- 第{iter_num}/{max_iterations}轮迭代开始 ---")
            self._publish_event("pipeline.stage_started", {
                "stage": f"Step2-第{iter_num}轮生成",
                "progress": iter_progress
            })
            
            # ===== Step 2: 发送API请求 → 接收文章 =====
            try:
                # 如果不是第一轮，将上轮反馈注入请求用于优化
                if iteration > 0 and last_feedback:
                    # V7.0关键修复：反馈必须注入到request.outline（V3实际读取的属性），
                    # 而非outline_data（V3不读此属性），否则反馈永远不生效！
                    original_outline = getattr(enhanced_request, 'outline', '') or ''
                    enhanced_request.outline = original_outline + "\n\n【上轮优化反馈】\n" + last_feedback
                    
                    # 同步更新outline_data（供专家自身评分使用）
                    current_outline_data = getattr(enhanced_request, 'outline_data', None)
                    if isinstance(current_outline_data, dict):
                        current_outline_data['content'] = current_outline_data.get('content', '') + "\n\n" + last_feedback
                    # 同步更新chapter_outline（如果存在）
                    if hasattr(enhanced_request, 'chapter_outline') and enhanced_request.chapter_outline:
                        enhanced_request.chapter_outline += "\n\n" + last_feedback
                    
                    # 设置独立属性供底层生成器直接读取
                    enhanced_request.optimization_feedback = last_feedback
                    logger.info(f"[专家模式][第{iter_num}轮] 已注入优化反馈到request.outline({len(last_feedback)}字符)")
                
                base_result = self._call_base_generator(enhanced_request)
                
                if base_result is None:
                    logger.error(f"[专家模式][第{iter_num}轮] 基础生成器返回空结果")
                    if iteration == 0:
                        self._publish_event("generation.failed", {"error": "基础生成器返回空结果"})
                        return self._create_empty_result()
                    logger.warning(f"[专家模式][第{iter_num}轮] 非首轮失败，使用上一轮最佳结果继续")
                    break
                
                content = self._extract_content(base_result)
                
                # V10.0修复(P0-1)：字数后处理智能裁剪（第三道防线）
                # 根因：DeepSeek模型完全无视prompt中的字数约束，持续超标50-100%
                # 策略：在返回给评分器之前，智能截取到目标范围内
                # 裁剪规则：
                #   1. 超标≤30%：不裁剪（prompt约束+迭代反馈应能解决，避免过度干预）
                #   2. 超标30-80%：智能截断到最后一个完整句子
                #   3. 超标>80%：强制截断到目标字数附近（找最近句号）
                # 截断保护：绝不破坏【本章完】标记
                content = self._smart_trim_word_count(content, target_words)
                
                # API错误检测（V1.49.35保留）
                error_info = None
                if hasattr(base_result, 'error') and base_result.error:
                    error_info = base_result.error
                elif isinstance(base_result, dict) and base_result.get('error'):
                    error_info = base_result.get('error')
                
                if not content or (content.strip() == '' and error_info):
                    logger.error(f"[专家模式][第{iter_num}轮] 生成失败: {error_info}")
                    if iteration == 0:
                        self._publish_event("generation.failed", {"error": f"生成失败: {error_info}"})
                        return self._create_empty_result()
                    break
                
                # 极短内容警告（不中断流程）
                if len(content.strip()) < 10:
                    logger.warning(f"[专家模式][第{iter_num}轮] 内容过短({len(content)}字符)")
                    
            except Exception as e:
                logger.error(f"[专家模式][第{iter_num}轮] 生成异常: {e}")
                if iteration == 0:
                    self._publish_event("generation.failed", {"error": str(e)})
                    return self._create_empty_result()
                break
            
            logger.info(f"[专家模式][Step2] 第{iter_num}轮收到内容: {len(content)}字符")
            
            # ===== Step 3: 九维度评分 =====
            self._publish_event("pipeline.stage_started", {
                "stage": f"Step3-第{iter_num}轮评分",
                "progress": iter_progress + 0.05
            })
            
            expert_evaluation = self._evaluate_expert(content, enhanced_request)
            current_score = expert_evaluation.total_score
            
            # V9.0修复：【本章完】不再自动补充！
            # 设计原则：用户加【本章完】就是为了验证返回内容是真实完整的。
            # 自动补充违背初衷，使评分假高、用户无法判断真实质量。
            # 现在改为：缺标记 → 记录为不完整，该轮次不能作为达标结果，
            # 但仍然参与评分迭代（让反馈推动模型自己学会生成标记）。
            has_chapter_end = '【本章完】' in content or '[本章完]' in content or '（本章完）' in content
            
            if not has_chapter_end:
                logger.warning(f"[专家模式][第{iter_num}轮] 缺少【本章完】标记，内容可能不完整")
                # 不再自动补充！保留原始内容让评分反映真实质量
                # 标记本轮为"标记缺失"状态
            
            # 记录本轮结果
            iteration_history.append({
                "iteration": iter_num,
                "score": current_score,
                "has_chapter_end": has_chapter_end,
                "word_count": len(content),
            })
            
            # 输出评分详情到日志
            logger.info(f"[专家模式][Step3] 第{iter_num}轮评分: 总分={current_score:.3f}(阈值:{quality_threshold})")
            
            # 更新最佳结果
            if current_score > best_score:
                best_score = current_score
                best_content = content
                best_evaluation = expert_evaluation
            
            # ===== Step 4-5: 达标判断 / 不达标则构建反馈准备重试 =====
            # V9.0达标条件：总分 >= 阈值 且 有【本章完】标记（不再降级补充）
            # 缺少【本章完】标记的轮次永远不达标，必须让模型自己生成
            is_passing = (current_score >= quality_threshold) and has_chapter_end
            
            if is_passing:
                logger.info(f"[专家模式][SUCCESS] 第{iter_num}轮达标！分数={current_score:.3f}>={quality_threshold}")
                best_content = content
                best_evaluation = expert_evaluation
                break
            
            # 不达标 → 构建反馈，准备下一轮迭代
            logger.info(
                f"[专家模式][CONTINUE] 第{iter_num}轮未达标: "
                f"分数={current_score:.3f}<{quality_threshold}, "
                f"{'缺【本章完】' if '【本章完】' not in content else '有【本章完】'}"
            )
            
            # 生成优化建议（作为下一轮迭代的反馈）
            optimization = self._generate_optimization(expert_evaluation)
            
            # 构建结构化反馈文本（注入到下次请求）
            # V9.1修复(P2-3)：传入content和request以计算字数差值
            last_feedback = self._build_iteration_feedback(
                iter_num, current_score, expert_evaluation, optimization,
                quality_threshold, content=content, request=enhanced_request
            )
            
            logger.debug(f"[专家模式][FEEDBACK] 反馈长度: {len(last_feedback)}字符")
        
        # ===== 迭代结束 =====
        total_iters = len(iteration_history)
        final_is_passing = best_score >= quality_threshold
        
        logger.info(
            f"[专家模式][FINAL] 迭代结束: 共{total_iters}轮, "
            f"最佳分数={best_score:.3f}, 达标={'YES' if final_is_passing else 'NO(达上限)'}"
        )
        
        self._publish_event("pipeline.stage_started", {"stage": "Step6-输出成果", "progress": 0.9})
        
        # ===== Step 6: 输出最终成果 =====
        if best_evaluation is None:
            logger.error("[专家模式] 所有轮次均无有效评估，返回空结果")
            return self._create_empty_result()
        
        # 构建最终结果
        result = self._create_result(best_content, best_evaluation)
        
        # 将迭代统计信息附加到metadata
        if hasattr(result, 'metadata'):
            result.metadata.update({
                "total_iterations": total_iters,
                "is_passing": final_is_passing,
                "best_score": best_score,
                "quality_threshold": quality_threshold,
                "iteration_scores": [h["score"] for h in iteration_history],
            })
        
        # ===== Step 7: 总结经验输入Claw化记忆 =====
        self._publish_event("pipeline.stage_started", {"stage": "Step7-经验沉淀", "progress": 0.95})
        
        optimization_for_memory = None
        if not final_is_passing and total_iters > 0:
            # 即使未达标也存储优化建议供参考
            optimization_for_memory = self._generate_optimization(best_evaluation)
        
        try:
            self._store_to_memory(best_evaluation, optimization_for_memory, request)
            logger.info("[专家模式][Step7] 经验已沉淀到Claw记忆")
        except Exception as e:
            logger.warning(f"[专家模式][Step7] 记忆存储跳过: {e}")
        
        # 发布完成事件
        self._publish_event("generation.completed", {
            "chapter": chapter_title,
            "chapter_number": getattr(request, 'chapter_number', None),  # V8.0修复：传递章节号供GUI显示
            "score": best_score,
            "status": "成功" if final_is_passing else f"未达标(上限{max_iterations}轮)",
            "iterations": total_iters,
            "total_words": len(best_content) if best_content else 0,  # V7.0修复：monitor面板依赖此字段
            "content": best_content if best_content else "",  # V8.0:完整内容（不再截断）
        })
        
        logger.info(f"[专家模式] ========== 流程结束: 分数={best_score:.3f}, 迭代={total_iters}轮 ==========")
        
        return result
    
    def _enhance_request(self, request):
        """
        增强请求（整合数据源）
        
        这是专家模式的核心增强点:
        将世界观、人设、大纲、风格、知识库、写作技巧整合到请求中
        
        V1.49.35修复：双重数据来源兼容
        - 来源A（旧版）：_reference后缀属性（文件路径），调用_load_*方法从磁盘加载
        - 来源B（新版，GUI实际传递）：直接数据属性（dict/list），直接使用
          worldview_config / character_profiles / outline / style_profile
        """
        # 创建增强请求（不修改原始请求）
        enhanced = request
        
        try:
            # ===== 世界观数据 =====
            # 优先级：直接数据 > 文件路径引用
            worldview_data = getattr(request, 'worldview_config', None) or getattr(request, 'worldview_reference', None)
            if worldview_data and isinstance(worldview_data, dict):
                # GUI已加工好的字典数据，直接使用
                enhanced.worldview_data = worldview_data
            elif worldview_data and isinstance(worldview_data, str):
                # 旧版：文件路径，从磁盘加载
                enhanced.worldview_data = self._load_worldview(worldview_data)
            
            # ===== 人物数据（V6.2修复：只保留章节相关人物；V6.3修复：字典→列表正确转换）=====
            char_data = getattr(request, 'character_profiles', None) or getattr(request, 'character_references', None)
            if char_data and isinstance(char_data, list):
                # 已经是列表格式，直接使用
                enhanced.character_data = char_data
            elif char_data and isinstance(char_data, dict):
                # V6.3修复：字典格式{name: profile} → 列表格式[profile_with_name]
                # GenerationDataService._format_characters返回{name: char_dict}格式
                # validator期望[{name: "张三", ...}, {name: "李四", ...}]格式
                char_list = []
                for char_name, char_profile in char_data.items():
                    if isinstance(char_profile, dict):
                        # 确保name字段存在于profile中
                        if 'name' not in char_profile:
                            char_profile['name'] = char_name
                        char_list.append(char_profile)
                    else:
                        # 非字典值，包装为最小人物记录
                        char_list.append({'name': char_name, 'value': char_profile})
                enhanced.character_data = char_list
                logger.info(f"[专家模式] 人物数据格式转换: dict({len(char_data)}人) → list({len(char_list)}人)")
            elif char_data and isinstance(char_data, str):
                enhanced.character_data = self._load_characters(char_data)
            
            # V6.2修复：过滤人物，只保留当前章节相关的人物
            if hasattr(enhanced, 'character_data') and enhanced.character_data and len(enhanced.character_data) > 1:
                # 获取章节大纲文本用于匹配人物名
                chapter_outline_text = getattr(request, 'chapter_outline', None) or ''
                outline_content = getattr(enhanced, 'outline_data', None)
                if isinstance(outline_content, dict):
                    chapter_outline_text = chapter_outline_text or outline_content.get('content', '')
                
                if chapter_outline_text:
                    filtered_characters = []
                    for char in enhanced.character_data:
                        # 获取人物名字（支持多种数据结构）
                        char_name = ''
                        if isinstance(char, dict):
                            char_name = char.get('name', '') or char.get('姓名', '') or char.get('角色名', '')
                        elif hasattr(char, 'name'):
                            char_name = char.name
                        elif hasattr(char, '姓名'):
                            char_name = char.姓名
                        
                        # 如果人物名字出现在章节大纲中，则保留
                        if char_name and char_name in chapter_outline_text:
                            filtered_characters.append(char)
                    
                    # 至少保留1个人物（如果过滤后为空则保留全部）
                    if filtered_characters:
                        enhanced.character_data = filtered_characters
                        logger.info(f"[专家模式] 人设过滤: {len(enhanced.character_data)}个人物(原始{len(filtered_characters)}+其他)")
            
            # ===== 大纲数据（V6.2修复：优先使用章节大纲chapter_outline而非完整大纲）=====
            # 优先使用chapter_outline（单章），其次用outline（完整）
            chapter_outline = getattr(request, 'chapter_outline', None)
            outline_data = getattr(request, 'outline', None) or getattr(request, 'outline_reference', None)
            
            if chapter_outline:
                # GUI已设置章节大纲，直接使用（这是最精确的）
                enhanced.outline_data = {"content": chapter_outline}
            elif outline_data:
                if isinstance(outline_data, dict):
                    enhanced.outline_data = outline_data
                elif isinstance(outline_data, str):
                    # 判断是JSON字符串还是文件路径
                    if outline_data.startswith('{') or os.path.exists(outline_data):
                        if os.path.exists(outline_data):
                            enhanced.outline_data = self._load_outline(outline_data)
                        else:
                            enhanced.outline_data = {"content": outline_data}
                    else:
                        enhanced.outline_data = {"content": outline_data}
            
            # 额外检查 chapter_outline（GUI设置的章节大纲）
            if not getattr(enhanced, 'outline_data', None) or not enhanced.outline_data:
                chapter_outline = getattr(request, 'chapter_outline', None)
                if chapter_outline:
                    enhanced.outline_data = {"content": chapter_outline}
            
            # ===== 风格数据 =====
            style_data = getattr(request, 'style_profile', None) or getattr(request, 'style_reference', None)
            if style_data and isinstance(style_data, dict):
                enhanced.style_data = style_data
            elif style_data and isinstance(style_data, str):
                enhanced.style_data = self._load_style(style_data)
            
            # ===== 知识库和写作技巧（V6.2修复：支持用户选择过滤）=====
            # 从request中获取用户选择的分类，传入加载方法
            selected_kb_cats = getattr(request, 'knowledge_categories', None)
            enhanced.knowledge_base = self._load_knowledge_base(selected_categories=selected_kb_cats)
            
            selected_tech_areas = getattr(request, 'writing_techniques', None)
            # writing_techniques可能是字符串（如"narrative,description"），需转为列表
            if isinstance(selected_tech_areas, str):
                selected_tech_areas = [t.strip() for t in selected_tech_areas.split(',') if t.strip()]
            enhanced.writing_techniques = self._load_writing_techniques(selected_techniques=selected_tech_areas)
            
            # ===== 前文上下文 =====
            prev_chapters = getattr(request, 'previous_chapter_text', None) or getattr(request, 'previous_chapters', None)
            if prev_chapters:
                enhanced.previous_chapters = prev_chapters if isinstance(prev_chapters, list) else [prev_chapters]
            
            # ===== 【V1.49.36】历史经验回读（Claw化核心：越用越聪明）=====
            # 从ExpertMemory中检索历史评分和优化建议，注入到请求中
            # 这样每次生成都会基于之前的经验进行改进
            if self._expert_memory:
                try:
                    chapter_id = getattr(request, 'chapter_title', '') or getattr(request, 'title', '')
                    # 检索该章节的历史评分（如果有）
                    prev_eval = self._expert_memory.retrieve_evaluation(chapter_id)
                    if prev_eval:
                        enhanced.historical_evaluation = prev_eval
                        logger.info(f"[专家模式] 已加载历史评分: {chapter_id}, 总分={getattr(prev_eval,'total_score','?')}")
                    
                    # 获取全局常见问题及解决方案
                    common_issues = getattr(request, 'title', '小说生成')
                    similar_solutions = self._expert_memory.retrieve_similar_issues(common_issues, top_k=3)
                    if similar_solutions:
                        enhanced.historical_solutions = similar_solutions
                        logger.info(f"[专家模式] 已加载{len(similar_solutions)}条历史优化方案")
                except Exception as e:
                    logger.debug(f"[专家模式] 历史经验回读跳过: {e}")
            
            # 目标字数
            word_target = getattr(request, 'word_count', None) or getattr(request, 'word_count_target', None)
            if word_target:
                enhanced.word_count_target = word_target
            
            logger.info(f"[专家模式] 数据整合完成: "
                       f"世界观={'✓' if hasattr(enhanced,'worldview_data') and enhanced.worldview_data else '✗'} "
                       f"人物={len(getattr(enhanced,'character_data',[])) or '✗'} "
                       f"大纲={'✓' if hasattr(enhanced,'outline_data') and enhanced.outline_data else '✗'} "
                       f"风格={'✓' if hasattr(enhanced,'style_data') and enhanced.style_data else '✗'} "
                       f"知识库={'✓' if hasattr(enhanced,'knowledge_base') and enhanced.knowledge_base else '✗'}")
        except Exception as e:
            logger.warning(f"数据源整合失败: {e}")
        
        return enhanced
    
    def _inject_technique_guidance(self, request) -> str:
        """
        注入高级写作技巧指导到生成流程（V1.5.0新增）
        
        基于TechniqueMonitorSkill的检测结果，生成针对本章节的
        高级写作技巧应用指导文本，注入prompt中引导LLM运用特定技巧。
        
        核心逻辑：
        1. 如果有前文内容（迭代生成场景），分析已用技巧，推荐新技巧
        2. 如果是首次生成（无前文），基于章节大纲推荐适合的技巧
        3. 返回格式化的指导文本（追加到系统prompt末尾）
        
        Returns:
            str: 技巧指导文本（空字符串表示不注入）
        """
        if get_skill_manager is None:
            return ""
        
        try:
            sm = get_skill_manager()
            
            # 获取前文内容（如果有）
            previous_chapters = getattr(request, 'previous_chapters', [])
            recent_content = ""
            if previous_chapters:
                # 取最近一章的内容用于分析
                recent_text = previous_chapters[-1]
                if isinstance(recent_text, dict):
                    recent_content = recent_text.get('content', '')
                elif isinstance(recent_text, str):
                    recent_content = recent_text
            
            # 构建上下文
            context = {
                'worldview': getattr(request, 'worldview_data', {}),
                'characters': getattr(request, 'character_data', []),
                'outline': getattr(request, 'outline_data', {}),
            }
            
            # 调用SkillManager获取技巧指导
            guidance = sm.get_technique_guidance(recent_content, context)
            
            return guidance or ""
            
        except Exception as e:
            logger.warning(f"技巧指导注入失败，跳过: {e}")
            return ""
    
    def _call_base_generator(self, request):
        """
        调用AI生成（V8.0重构：直接API调用，消除双重嵌套循环）
        
        V8.0关键修复：
        - 旧版：expert → novel-generator-v3 → iterative-generator-v2(内层5轮循环) = 双重嵌套
        - 新版：expert直接调用AI API，仅外层循环生效（5轮=5次API调用，而非25次）
        
        专家模式是默认模式的增强替代品（非包装），应自行完成：
        1. 构建完整提示词（数据源整合在Step1已完成）
        2. 直接调用AI API获取文章
        3. 由generate()的外层循环负责评分和迭代
        
        Returns:
            GenerationResult或dict（与_extract_content兼容）
        """
        try:
            # V1.49.36：将历史经验信息注入到请求
            hist_eval = getattr(request, 'historical_evaluation', None)
            hist_solutions = getattr(request, 'historical_solutions', None)
            
            if hist_eval or hist_solutions:
                experience_hint = self._build_experience_prompt(hist_eval, hist_solutions)
                current_outline = getattr(request, 'outline', '') or ''
                if current_outline:
                    request.outline = current_outline + "\n\n" + experience_hint
                    logger.debug(f"[专家模式] 已将历史经验注入到request.outline({len(experience_hint)}字符)")
                if hasattr(request, 'outline_data') and isinstance(request.outline_data, dict):
                    original_outline_content = request.outline_data.get('content', '')
                    request.outline_data['content'] = original_outline_content + "\n\n" + experience_hint
                elif hasattr(request, 'chapter_outline') and request.chapter_outline:
                    request.chapter_outline += "\n\n" + experience_hint
            
            # V8.0核心：直接构建提示词并调用AI API（不再经过novel-generator-v3）
            content = self._direct_generate(request)
            
            if content:
                # 返回与_extract_content兼容的dict格式
                return {"content": content}
            else:
                return None
                
        except Exception as e:
            logger.error(f"基础生成器调用失败: {e}")
            return None
    
    def _direct_generate(self, request) -> str:
        """
        直接调用AI API生成内容（V8.0新增）
        
        与iterative-generator-v2的_send_request_to_model()逻辑对齐：
        - 使用相同的system prompt（人物设定优先、大纲执行等）
        - 使用相同的token计算公式
        - 通过AIServiceManager统一调用
        """
        from core.ai_service_manager import get_ai_service_manager
        from core.ai_provider import GenerationConfig, AIProviderError
        
        # 构建完整提示词（基于增强后的请求数据）
        prompt = self._build_expert_prompt(request)
        
        # V9.0修复：字数目标传播——兼容GUI传递的多种属性名
        # GUI通过GenerationRequest的word_count属性传入用户设置的字数
        target_words = getattr(request, 'word_count_target', None) or getattr(request, 'word_count', None) or 3500
        logger.info(f"[专家模式][DirectAPI] 目标字数: {target_words}（来源: {'word_count_target' if hasattr(request,'word_count_target') else 'word_count' if hasattr(request,'word_count') else '默认'}）")
        
        # V10.0修复(P0)：字数控制三管齐下策略
        # 教训总结（V9.2+V9.3迭代6轮数据）：
        #   ① V9.2: max_tokens=1800截断 → 【本章完】丢失 ✗
        #   ② V9.3: max_tokens放宽到3.5倍(8000) → 字数失控50-100% ✗
        #   ③ 根因：DeepSeek-reasoner完全无视prompt中的字数指令
        #
        # V10.0策略（三层防线）：
        #   第1层：max_tokens收紧到2.2倍（给AI刚好够写完的空间，不浪费也不截断）
        #   第2层：prompt中注入更激进的字数约束（V9.3基础上强化）
        #   第3层（新增）：后处理智能裁剪——如果仍超标>30%，在返回前智能截取到目标范围
        #       裁剪位置：找最后一个完整句子结尾（句号/！？/【），避免断在半句话中间
        #
        # 系数设计依据：中文1字≈1.5-2token（含标点），
        #   目标1500字→需3000token输出空间，加上system prompt开销(~500token)，
        #   总共需要~3500token。系数2.2×1500=3300，足够但不过量。
        base_tokens = int(target_words * 2)      # 基础：每字2token（含标点+思考）
        max_tokens = int(base_tokens * 1.1)      # 总系数2.2倍（2×1.1），收紧！
        max_tokens = max(max_tokens, 800)        # 最小800 token（短章节也需要空间）
        max_tokens = min(max_tokens, 5000)       # 上限5000 token（防止极端长章节溢出）
        
        config = GenerationConfig(
            temperature=0.7,
            max_tokens=max_tokens,
            timeout=120
        )
        
        # 构建强化system prompt（与iterative-generator-v2一致）
        target_wc = getattr(request, 'word_count_target', None) or getattr(request, 'word_count', None) or 3500
        system_prompt = f"""你是一位经验丰富的小说创作专家,必须严格遵守以下核心原则:

【核心原则】
1. **人物设定不可违背**: 
   - 人物的性格、外貌、背景、行为模式必须严格遵循设定
   - 人物的对话风格、语言习惯必须与设定一致
   - 人物之间的关系必须符合设定
   - 严禁擅自改变人物设定或添加不符合设定的行为

2. **大纲严格执行**: 
   - 必须完整执行章节大纲的所有要点
   - 不得遗漏关键情节

3. **风格保持一致**: 
   - 在遵守设定的前提下,保持与提供风格样本相同的叙事风格

【人物设定优先级】
- 人物设定 > 风格模仿
- 设定准确性 > 文学修辞
- 人物一致性 > 情节戏剧性

【创作检查清单】
在创作每一句话前，请确认：
✓ 人物的对话是否符合理设定的说话方式？
✓ 人物的行为是否符合设定的性格特征？
✓ 人物的决策是否符合设定的行为模式？
✓ 人物之间的互动是否符合设定的人物关系？
✓ 世界观元素是否准确无误？

【输出要求 - 强制执行】
🔴 **字数硬约束：目标{target_wc}字（±10%范围：{int(target_wc*0.9)}-{int(target_wc*1.1)}字）**
   → 写作前先规划段落分配，确保总字数落在范围内
   → 绝对不能超出上限！写到接近上限时立刻收尾，不要展开新情节
   → 字数不足时扩展细节描写而非压缩；但绝不允许超标！
🔴 **结尾硬约束：必须在文章最后三个字写上【本章完】，缺一不可！**
   → 这是系统自动检测项，缺失则判定为生成失败
   → 写完正文后务必最后加上这四个字符
- 人物言行必须100%符合设定
- 确保内容是完整的：有开头、有发展、有收尾，不能在句子中间截断"""
        
        # 调用AI服务
        ai_manager = get_ai_service_manager()
        result = ai_manager.generate_text(
            prompt=prompt,
            config=config,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        )
        
        if not result.success:
            raise AIProviderError(f"AI生成失败: {result.error}")
        
        content = result.text
        logger.info(f"[专家模式][DirectAPI] 生成成功，内容长度: {len(content)} 字符")
        return content
    
    def _build_expert_prompt(self, request) -> str:
        """
        构建专家模式完整提示词（V8.0新增）
        
        整合所有数据源为单一prompt文本：
        - 章节标题和大纲
        - 世界观、人设、风格数据
        - 知识库和写作技巧
        - 前文上下文
        - 字数要求和【本章完】标记
        """
        parts = []
        
        # 章节标题
        chapter_title = getattr(request, 'title', '') or getattr(request, 'chapter_title', '') or '未知章节'
        parts.append(f"请创作小说章节：{chapter_title}")
        parts.append("")
        
        # 大纲（核心参考——优先使用chapter_outline，其次outline）
        outline_text = getattr(request, 'chapter_outline', None) or getattr(request, 'outline', None)
        if outline_text:
            parts.append(f"【章节大纲】\n{outline_text}")
            parts.append("")
        
        # 世界观
        worldview_data = getattr(request, 'worldview_data', None)
        if worldview_data and isinstance(worldview_data, dict):
            worldview_str = json.dumps(worldview_data, ensure_ascii=False)[:1500]
            parts.append(f"【世界观设定】\n{worldview_str}")
            parts.append("")
        
        # 人设
        character_data = getattr(request, 'character_data', None)
        if character_data and isinstance(character_data, list):
            parts.append("【人物设定】")
            for char in character_data[:5]:
                if isinstance(char, dict):
                    name = char.get('name', char.get('姓名', '未知'))
                    role = char.get('role', char.get('角色', ''))
                    personality = char.get('personality', char.get('性格', ''))
                    desc = f"- {name}"
                    if role:
                        desc += f"（{role}）"
                    if personality:
                        # 截取前100字符避免过长
                        personality_str = str(personality)[:100] if len(str(personality)) > 100 else str(personality)
                        desc += f": {personality_str}"
                    parts.append(desc)
            parts.append("")
        
        # 风格
        style_data = getattr(request, 'style_data', None)
        if style_data and isinstance(style_data, dict):
            style_str = json.dumps(style_data, ensure_ascii=False)[:800]
            parts.append(f"【写作风格】\n{style_str}")
            parts.append("")
        
        # 知识库——智能筛选并注入实际知识内容（V9.0修复：不再只传分类名）
        # 设计原则：只上传与章节大纲明显相关的知识词条，非全量上传
        # LLM看到的是具体知识点内容（定义/描述/示例），而非空洞的分类名
        knowledge_base = getattr(request, 'knowledge_base', None)
        if knowledge_base and isinstance(knowledge_base, dict):
            kb_items = self._extract_relevant_knowledge(knowledge_base, outline_text)
            if kb_items:
                parts.append(f"【知识库参考（{len(kb_items)}条相关词条）】请在创作时自然融入以下知识点（不是直接引用，而是运用其中的概念、设定和描写方法）：")
                for item_info in kb_items[:12]:  # 最多12条，避免prompt过长
                    parts.append(f"  ● {item_info['title']}：{item_info['content'][:200]}")
                parts.append("")
        
        # 写作技巧——注入真实技巧定义和方法（V9.0修复：不再是空壳分类名）
        # 设计原则：根据UI选择真实应用！应用=在写作中使用对应技巧方法
        # 不是在正文中出现"使用了XX技巧"，而是让文本体现出该技巧的写作特征
        techniques = getattr(request, 'writing_techniques', None)
        if techniques and isinstance(techniques, dict):
            tech_guidance = self._format_technique_guidance_for_prompt(techniques)
            if tech_guidance:
                parts.append(f"【写作技巧要求】请运用以下写作技巧进行创作：")
                parts.append(tech_guidance)
                parts.append("")
        
        # 前文上下文
        prev_chapters = getattr(request, 'previous_chapters', None)
        if prev_chapters and isinstance(prev_chapters, list):
            # 只取最近一章的前500字符作为上下文衔接
            last_chapter = prev_chapters[-1]
            last_text = ""
            if isinstance(last_chapter, dict):
                last_text = last_chapter.get('content', '')[-500:]
            elif isinstance(last_chapter, str):
                last_text = last_chapter[-500:]
            if last_text:
                parts.append(f"【前文衔接（上一章末尾）】\n{last_text}")
                parts.append("")
        
        # 目标字数和强制要求
        target_words = getattr(request, 'word_count_target', 3500) or 3500
        parts.extend([
            "【重要要求】",
            f"🔴 1. 字数硬约束：{target_words}字（±10%，即{int(target_words*0.9)}-{int(target_words*1.1)}字）",
            f"   写作前请规划好：开头约{int(target_words*0.2)}字 + 发展约{int(target_words*0.5)}字 + 收尾约{int(target_words*0.3)}字",
            "   超出上限是严重错误！宁可少写也不要多写！",
            "🔴 2. 结尾硬约束：文章最后三个字必须是【本章完】，否则系统判定为失败！",
            "   写完正文后务必检查：最后三个字是否为【本章完】？",
            "3. 严格遵守人物设定和世界观设定",
            "",
            "⚠️ 再次强调（最重要）：",
            f"① 字数必须控制在{target_words}±10%范围内",
            "② 文章必须以【本章完】结尾（这是自动检测项！）"
        ])
        
        # 技巧指导（如果已注入）
        technique_guidance = getattr(request, 'technique_guidance', None)
        if technique_guidance:
            parts.append("")
            parts.append(f"【高级技巧指导】\n{technique_guidance}")
        
        # V9.3修复：在prompt最末尾追加终极约束（LLM对最后内容注意力最高）
        parts.append("")
        parts.append(f"【终极检查清单（写作完成后逐条确认）】")
        parts.append(f"☐ 字数是否在{target_words}±10%范围内？（当前目标{target_words}字）")
        parts.append("☐ 最后三个字是否为【本章完】？如不是，立即添加！")
        
        final_prompt = "\n".join(parts)
        logger.debug(f"[专家模式][Prompt] 完整提示词长度: {len(final_prompt)} 字符")
        
        return final_prompt
    
    def _build_experience_prompt(self, evaluation=None, solutions=None) -> str:
        """
        基于历史评估和优化方案构建经验提示文本
        
        V1.49.36新增：让LLM在首次生成时就参考历史经验，
        避免"每次从零开始"，实现真正的持续优化。
        
        V8.0增强：经验提示从泛化描述改为具体可操作指令，
        解决"Claw记忆存储但优化无效"的问题。
        
        Args:
            evaluation: 历史评估结果
            solutions: 历史相似问题的解决方案列表
            
        Returns:
            str: 经验提示文本（具体可操作格式）
        """
        parts = []
        parts.append("[历史生成经验] 以下是基于之前章节生成的改进要点，本次创作请务必参考：\n")
        
        if evaluation:
            score = getattr(evaluation, 'total_score', 0)
            dim_scores = getattr(evaluation, 'dimension_scores', {})
            
            # V8.0：按维度分数给出具体指令（而非泛化的"需避免"）
            if score and score < 0.8:
                parts.append(f"- 上次评分: {score:.2f} (未达标，以下维度需要重点改进)")
                
                # 找出最低分的3个维度并给出具体指令
                dim_instructions = {
                    "style": "- 风格问题：请增加句式长短变化(长/短句交替)，使用更多感官描写(视觉/听觉/触觉细节)",
                    "character": "- 人设问题：请为角色对话添加动作描写(如'她皱眉道''他笑着说')；确保对话风格符合角色性格",
                    "outline": "- 大纲问题：请对照大纲逐项检查关键情节点是否覆盖，不要遗漏重要情节转折",
                    "worldview": "- 世界观问题：请在描写中融入世界观的独特元素(地名/规则/文化符号)，不违反已设定规则",
                    "word_count": f"- 字数问题：上次字数未达标或超标，本次必须严格控制在目标字数的±10%范围内",
                    "knowledge": "- 知识库问题：请自然融入相关知识领域的术语和概念，让内容更专业可信",
                    "writing_technique": "- 技巧问题：请运用'展示而非告知'技巧(用动作/对话展示而非直接叙述);增加环境氛围描写",
                    "ai_feeling": "- AI感问题：减少模板化表达(避免'首先...其次...最后');增加口语化和个性化表达",
                    "context_coherence": "- 上下文问题：确保与前文的时空线和情感连贯，使用过渡词衔接段落"
                }
                
                # 按分数排序，输出最低的3个维度的指令
                low_dims = [(k, v) for k, v in dim_scores.items() if isinstance(v, (int, float)) and v < 0.75]
                low_dims.sort(key=lambda x: x[1])
                
                for dim_name, dim_score in low_dims[:3]:
                    instruction = dim_instructions.get(dim_name)
                    if instruction:
                        parts.append(instruction)
                
                # 正面激励：哪些做得好要继续保持
                good_dims = [k for k, v in dim_scores.items() if isinstance(v, (int, float)) and v >= 0.85]
                if good_dims:
                    dim_names_cn = {"style":"写作风格", "character":"人物塑造", "outline":"大纲执行", 
                                    "worldview":"世界观", "word数":"字数控制", "knowledge":"知识库运用",
                                    "writing_technique":"写作技巧", "ai_feeling":"自然度", "context_coherence":"上下文衔接"}
                    good_names = [dim_names_cn.get(k, k) for k in good_dims]
                    parts.append(f"- 表现良好(继续保持): {'、'.join(good_names)}")
        
        if solutions:
            parts.append("\n- 历史优化建议:")
            for sol in solutions[:3]:
                sol_data = sol.get('data', {})
                overall = sol_data.get('overall_suggestion', '')
                if overall:
                    parts.append(f"  参考: {overall[:100]}")
        
        return "\n".join(parts)
    
    def _extract_content(self, result) -> str:
        """从生成结果中提取内容"""
        if isinstance(result, dict):
            return result.get("content", "")
        elif hasattr(result, 'content'):
            return result.content
        else:
            return str(result) if result else ""
    
    def _evaluate_expert(self, content: str, request) -> ExpertEvaluation:
        """专家评分（V6.2：数据完整性校验——区分"用户未配置"和"数据流断裂"）"""
        if self._expert_validator is None:
            logger.warning("专家验证器未初始化，返回默认评分")
            return ExpertEvaluation(total_score=0.5)
        
        # ===== V6.2数据完整性校验 =====
        # 核心原则：
        # 1. 用户没配置（GUI原始属性为空）→ 中性分(0.85)，不扣分
        # 2. 数据流断裂（GUI有数据但plugin/validator收到空数据）→ 报错
        # 3. 第一章无上文 → 合法，中性分
        
        # 检查"增强后的请求"中各维度的数据是否存在
        worldview_data = getattr(request, 'worldview_data', None)
        character_data = getattr(request, 'character_data', None)
        outline_data = getattr(request, 'outline_data', None)
        style_data = getattr(request, 'style_data', None)
        knowledge_base = getattr(request, 'knowledge_base', None)
        writing_techniques = getattr(request, 'writing_techniques', None)
        previous_chapters = getattr(request, 'previous_chapters', None)
        target_words = getattr(request, 'word_count_target', 3500)
        
        # 同时检查"增强前的原始请求"——判断是用户没配置还是数据流断裂
        # 如果原始请求有数据但增强后丢失了，说明_enhance_request有bug
        has_original_worldview = bool(getattr(request, 'worldview_config', None) or getattr(request, 'worldview_reference', None))
        has_original_characters = bool(getattr(request, 'character_profiles', None) or getattr(request, 'character_references', None))
        has_original_outline = bool(getattr(request, 'outline', None) or getattr(request, 'outline_reference', None) or getattr(request, 'chapter_outline', None))
        has_original_style = bool(getattr(request, 'style_profile', None) or getattr(request, 'style_reference', None))
        
        # 数据流断裂检测：原始请求有数据 → 增强后应该也有数据
        flow_errors = []
        if has_original_worldview and not worldview_data:
            flow_errors.append(f"世界观(worldview_config有值→worldview_data为空)")
        if has_original_characters and not character_data:
            flow_errors.append(f"人物(character_profiles有值→character_data为空)")
        if has_original_outline and not outline_data:
            flow_errors.append(f"大纲(outline/chapter_outline有值→outline_data为空)")
        if has_original_style and not style_data:
            flow_errors.append(f"风格(style_profile有值→style_data为空)")
        
        if flow_errors:
            error_msg = "数据流断裂检测: " + "; ".join(flow_errors)
            logger.error(f"[专家模式] {error_msg}")
            logger.error(f"  请检查ExpertPlugin._enhance_request()的数据映射逻辑")
            raise ValueError(error_msg + "。请检查_enhance_request的数据映射。")
        
        # 构建上下文
        context = {
            "worldview": worldview_data or {},
            "characters": character_data or [],
            "outline": outline_data or {},
            "style_profile": style_data or {},
            "knowledge_base": knowledge_base or {},
            "techniques": writing_techniques or {},
            "previous_chapters": previous_chapters or [],
            "target_words": target_words
        }
        
        # 传递数据是否由用户配置的元信息，让validator区分"未配置"和"无数据"
        context["_data_source"] = {
            "worldview_is_user_provided": has_original_worldview,
            "characters_is_user_provided": has_original_characters,
            "outline_is_user_provided": has_original_outline,
            "style_is_user_provided": has_original_style,
            "knowledge_is_loaded": bool(knowledge_base),  # V6.2：知识库在plugin层加载
            "techniques_is_loaded": bool(writing_techniques),  # V6.2：技巧在plugin层加载
        }
        
        # V6.2诊断日志：记录传给validator的完整数据状态
        logger.info(
            f"[专家模式][数据流诊断] "
            f"世界观={'有数据' if worldview_data else '用户未配置'}, "
            f"人物={'有数据('+str(len(character_data) if character_data else 0)+'人)' if character_data else '用户未配置'}, "
            f"大纲={'有数据' if outline_data else '用户未配置'}, "
            f"风格={'有数据' if style_data else '用户未配置'}, "
            f"知识库={'已加载('+str(len(knowledge_base))+'分类)' if knowledge_base else '未加载'}, "
            f"技巧={'已加载('+str(len(writing_techniques))+'领域)' if writing_techniques else '未加载'}, "
            f"前文={'有('+str(len(previous_chapters))+'章)' if previous_chapters else '无'}"
        )
        
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
    
    def _publish_event(self, event_type: str, data: dict = None):
        """
        发布事件到EventBus（V1.49.19新增）
        
        用于更新Agent监控面板
        
        Args:
            event_type: 事件类型（如generation.started, pipeline.stage_started等）
            data: 事件数据
        """
        try:
            if self._event_bus:
                self._event_bus.publish(event_type, data or {})
                logger.debug(f"事件已发布: {event_type}")
        except Exception as e:
            logger.warning(f"事件发布失败: {e}")
    
    def _create_result(self, content: str, evaluation: ExpertEvaluation) -> 'GenerationResult':
        """创建结果（V2.0合规修订：返回GenerationResult而非裸dict）"""
        try:
            from core.models import GenerationResult, ValidationScores
            import uuid
            
            # 构建ValidationScores（将expert的维度评分映射到标准字段）
            validation_scores = self._build_validation_scores(evaluation)
            
            return GenerationResult(
                request_id=f"expert-{uuid.uuid4().hex[:8]}",
                content=content,
                word_count=len(content),
                iteration_count=1,
                validation_scores=validation_scores,
                metadata={
                    "expert_mode": True,
                    "expert_evaluation": evaluation.to_dict(),
                    "chapter_end_marker": "【本章完】" in content[-100:],
                }
            )
        except ImportError:
            # 降级：如果GenerationResult不可用，返回裸dict
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
                                          optimization: OptimizationSuggestion) -> 'GenerationResult':
        """创建带优化建议的结果（V2.0合规修订：返回GenerationResult而非裸dict）"""
        try:
            from core.models import GenerationResult, ValidationScores
            import uuid
            
            # 构建ValidationScores
            validation_scores = self._build_validation_scores(evaluation)
            
            # V3.0修订：优化建议在插件层统一格式化
            formatted_suggestions = self._format_optimization_suggestions(optimization.to_dict())
            
            return GenerationResult(
                request_id=f"expert-{uuid.uuid4().hex[:8]}",
                content=content,
                word_count=len(content),
                iteration_count=1,
                validation_scores=validation_scores,
                metadata={
                    "expert_mode": True,
                    "expert_evaluation": evaluation.to_dict(),
                    "optimization_suggestions": formatted_suggestions,
                    "needs_optimization": True,
                    "chapter_end_marker": "【本章完】" in content[-100:],
                }
            )
        except ImportError:
            # 降级：如果GenerationResult不可用，返回裸dict
            # V3.0修订：降级路径也格式化优化建议
            formatted_suggestions = self._format_optimization_suggestions(optimization.to_dict())
            return {
                "content": content,
                "scores": evaluation.dimension_scores,
                "total_score": evaluation.total_score,
                "expert_evaluation": evaluation.to_dict(),
                "optimization_suggestions": formatted_suggestions,
                "metadata": {
                    "expert_mode": True,
                    "needs_optimization": True,
                    "chapter_end_marker": "【本章完】" in content[-100:]
                }
            }
    
    def _create_empty_result(self) -> 'GenerationResult':
        """创建空结果（V2.0合规修订：返回GenerationResult而非裸dict）"""
        try:
            from core.models import GenerationResult
            import uuid
            return GenerationResult(
                request_id=f"expert-{uuid.uuid4().hex[:8]}",
                content="",
                word_count=0,
                iteration_count=0,
                error="生成失败"
            )
        except ImportError:
            # 降级：如果GenerationResult不可用，返回裸dict
            return {
                "content": "",
                "scores": {},
                "total_score": 0.0,
                "error": "生成失败"
            }
    
    def _build_iteration_feedback(self, iteration: int, score: float,
                                   evaluation: 'ExpertEvaluation',
                                   optimization: 'OptimizationSuggestion',
                                   quality_threshold: float = 0.8,
                                   content: str = None, request=None) -> str:
        """
        构建迭代反馈文本（注入到下一轮API请求中）
        
        V1.49.36新增：这是迭代循环的核心——将评分结果和修改建议
        转化为结构化的反馈提示，让LLM在下一轮生成时针对性改进。
        
        V7.0重构：反馈质量决定优化效果。旧版反馈太泛（"风格需改进"），
        新版给出具体可操作指令（"增加对话描写""使用更多短句变化"）。
        
        V9.0重构：输出真实维度分数明细，不再泛化。
        
        V9.1修复(P2-3)：新增content和request参数，用于计算并注入具体字数差值。
        
        Args:
            iteration: 当前迭代轮次
            score: 当前评分
            evaluation: 专家评估结果
            optimization: 优化建议
            quality_threshold: 质量阈值（V9.0新增，用于在反馈中显示目标差距）
            content: 当前轮生成的文本（V9.1新增，用于计算实际字数）
            request: 增强后的请求对象（V9.1新增，用于获取目标字数）
            
            
        Returns:
            str: 结构化反馈文本（中文，供Prompt使用）
        """
        parts = []
        
        # V9.0修复：输出真实评分数据（总分+各维度分+具体修改建议）
        # 旧版只发泛泛的"风格需改进"，新版发送具体分数让AI知道差多少
        parts.append(f"[第{iteration}轮优化反馈]")
        parts.append(f"当前总分: {score:.4f} / 目标阈值: {quality_threshold:.2f}")
        parts.append(f"差距: {(quality_threshold - score):.4f}")
        parts.append("")
        
        # V9.0核心改进：按严重程度排序的TOP3具体问题 + 可操作指令
        # 先输出全部维度真实分数（让AI了解全面情况）
        dim_display_names = {
            "worldview": "世界观", "character": "人设", "outline": "大纲",
            "style": "风格", "word_count": "字数", "knowledge": "知识库",
            "writing_technique": "写作技巧", "ai_feeling": "AI感", "context_coherence": "上下文"
        }
        
        if hasattr(evaluation, 'dimension_scores') and evaluation.dimension_scores:
            # V9.0：输出完整的九维度分数明细
            score_lines = []
            for dim_key, display_name in dim_display_names.items():
                dim_score = evaluation.dimension_scores.get(dim_key, 0.5)
                status = "✓" if dim_score >= 0.80 else ("△" if dim_score >= 0.70 else "✗")
                score_lines.append(f"  {status} {display_name}: {dim_score:.2f}")
            
            if score_lines:
                parts.append("[各维度评分详情]")
                parts.extend(score_lines)
                parts.append("")
        
        low_dims = []  # (name, score, instruction)
        if hasattr(evaluation, 'dimension_scores') and evaluation.dimension_scores:
            dim_instructions = {
                "style": ("写作风格", "风格匹配", 
                         "请增加句式长短变化(混用长/短句)，避免连续相似长度句子；增加感官描写(视觉/听觉/触觉)；用具体动作替代抽象叙述"),
                "character": ("人物塑造", "人设表现",
                            "请为角色对话添加动作描写(如'她皱眉道''他笑着说')；增加角色内心独白；确保对话风格符合角色性格设定"),
                "outline": ("大纲符合度", "情节推进",
                           "请确保覆盖大纲中的关键情节点；检查是否有情节遗漏或顺序偏差；保持节奏紧凑"),
                "worldview": ("世界观一致性", "世界观",
                            "请在描写中融入世界观的独特元素(如特定规则/地名/文化符号)；确保不违反已设定的规则"),
                "word_count": ("字数达标", "字数",
                           self._build_word_count_feedback(score, content, request)),
                "knowledge": ("知识库运用", "知识库",
                            "请自然融入相关知识点的关键术语和概念"),
                "writing_technique": ("写作技巧", "技巧应用",
                               "请运用'展示而非告知'技巧(用动作/对话展示而非直接叙述);增加环境氛围描写"),
                "ai_feeling": ("AI痕迹检测", "AI感",
                            "减少模板化表达;增加口语化和个性化表达;避免'首先...其次...最后'等AI式结构"),
                "context_coherence": ("上下文衔接", "上下文",
                              "检查开头是否承接上一章结尾的时间/地点/人物状态；如果上一章以对话结束，本章可用动作或环境描写自然过渡；使用时间词（次日/与此同时）或空间转换衔接段落；保持人物情绪状态的连续性"),
            }
            
            for dim_key, (category, name, instruction) in dim_instructions.items():
                dim_score = evaluation.dimension_scores.get(dim_key, 0.5)
                if dim_score < 0.70:
                    low_dims.append((name, dim_score, instruction))
                elif dim_score < 0.80:
                    low_dims.append((name, dim_score, f"{name}接近达标，继续保持"))
            
            # 按分数升序排列（最差的放前面，LLM优先处理）
            low_dims.sort(key=lambda x: x[1])
        
        # 输出TOP3最需要改进的问题（带具体操作指令）
        if low_dims:
            parts.append(f"[本轮重点改进项(TOP{min(3, len(low_dims))})]")
            for i, (name, sc, instruction) in enumerate(low_dims[:3]):
                parts.append(f"❌ {name}({sc:.0f}): {instruction}")
            parts.append("")
        
        # 正面激励（让LLM知道哪些做得好，保持不变）
        good_dims = []
        for dim_key, (category, name, _) in dim_instructions.items():
            dim_score = evaluation.dimension_scores.get(dim_key, 0.5)
            if dim_score >= 0.80:
                good_dims.append(name)
        if good_dims:
            parts.append(f"[✅ 表现良好的维度(请继续保持)]: {'、'.join(good_dims)}")
            parts.append("")
        
        # V9.2修复(P0)：强制追加【本章完】标记提醒
        # 根因分析：第5-6轮反馈文本膨胀后，system prompt中的结束标记指令被稀释
        # 模型注意力被大量优化反馈吸引，忽略了结尾要求
        # 解决方案：在每轮反馈的末尾（最显眼位置）强制重复此约束
        parts.append("[⚠️ 强制要求] 本次生成必须在文章最后三个字写上【本章完】，缺一不可！")
        
        # 如果有具体的优化建议（来自optimizer），附加
        if optimization:
            opt_parts = []
            if hasattr(optimization, 'overall_suggestion') and optimization.overall_suggestion:
                opt_parts.append(optimization.overall_suggestion)
            if hasattr(optimization, 'suggestions') and optimization.suggestions:
                opt_parts.extend([s for s in optimization.suggestions[:3] if s])
            if opt_parts:
                parts.append("[专家建议]")
                parts.extend(opt_parts)
                parts.append("")
        
        feedback = "\n".join(parts)
        logger.debug(f"[专家模式] 构建反馈完成: {len(feedback)}字符")
        return feedback

    def _build_word_count_feedback(self, score: float, content: str = None, request=None) -> str:
        """
        V9.1新增(P2-3)：生成包含具体差值数字的字数反馈指令
        
        旧版问题：字数反馈只说"偏少/超出"，AI不知道具体差多少
        新版：注入实际字数、目标字数、具体差值，让AI精确调整
        """
        if content is None or not content:
            return f"当前字数{'偏少' if score<0.6 else '超出'}，请{'扩展细节描写' if score<0.6 else '控制篇幅聚焦核心情节'}"
        
        actual = len(content.replace("\n", "").replace(" ", ""))
        target_words = getattr(request, 'word_count_target', None) or getattr(request, 'word_count', None) or 3500
        diff = target_words - actual
        ratio = actual / target_words if target_words > 0 else 1.0
        
        if score >= 0.95:
            return f"字数达标（当前{actual}字，目标{target_words}字），继续保持"
        elif ratio < 0.8:
            # 字数偏少：告诉AI还差多少
            return f"当前{actual}字（目标{target_words}字），还需约{abs(diff)}字。建议：扩展场景环境描写2-3句、增加人物心理活动、细化对话中的动作和神态描写"
        elif ratio > 1.10:
            # 超出上限
            return f"当前{actual}字（目标{target_words}字），超出约{abs(diff)}字。建议：精简过渡段落、删除重复表达、合并相似的描述句子"
        elif ratio < 0.95:
            # 略少
            return f"当前{actual}字（目标{target_words}字），略少约{abs(diff)}字。可增加1-2处细节描写或一段内心独白来补足"
        else:
            # 略超但可接受
            return f"当前{actual}字（目标{target_words}字），略微超出约{abs(diff)}字，基本可接受"

    def _smart_trim_word_count(self, content: str, target_words: int) -> str:
        """
        V10.0新增(P0-1)：智能字数裁剪——第三道防线
        
        当AI生成内容严重超标时(>30%)，在评分前进行智能截取，
        将内容裁剪到目标范围内，避免字数维度拖垮总分。
        
        裁剪策略：
          1. 轻度超标(<=30%)：不裁剪，留给迭代反馈解决
          2. 中度超标(30-80%)：找最后完整句子截断，保护【本章完】标记
          3. 重度超标(>80%)：强制找句号截断到目标附近
        
        截断位置选择优先级（从后往前搜索）：
          1. 【本章完】之前（保留结束标记）
          2. 句号/！/？/。（完整句子结尾）
          3. 段落边界\n
          4. 硬截到target_words * 1.1字符位置
        """
        if not content or target_words <= 0:
            return content
        
        clean_content = content.rstrip()
        actual = len(clean_content.replace("\n", "").replace(" ", ""))
        
        if actual <= 0:
            return content
        
        ratio = actual / target_words
        
        # 第1层：轻度超标或未超标→不处理
        if ratio <= 1.30:
            return content
        
        # 检查【本章完】标记
        has_marker = "【本章完】" in clean_content
        
        # 第2层：中度超标(30-80%) → 智能截断到最后一个完整句子
        if ratio <= 1.80:
            trimmed = self._find_last_complete_sentence(clean_content, target_words)
            if trimmed and len(trimmed.replace("\n", "").replace(" ", "")) <= int(target_words * 1.15):
                if "【本章完】" not in trimmed:
                    trimmed = trimmed.rstrip() + "\n【本章完】"
                logger.info(f"[V10.0字数裁剪] 中度超标({actual}/{target_words}={ratio:.1%}) → "
                           f"智能截断到{len(trimmed.replace(chr(10),'').replace(' ',''))}字")
                return trimmed
        
        # 第3层：重度超标(>80%) → 强制按目标字数截断
        logger.warning(f"[V10.0字数裁剪] 重度超标({actual}/{target_words}={ratio:.1%})，执行强制截断")
        
        search_start = min(len(clean_content), int(target_words * 1.15))
        search_end = max(int(target_words * 0.85), 200)
        
        best_pos = search_end
        
        for pos in range(search_start, search_end, -1):
            char = clean_content[pos]
            if char in "。！？":
                best_pos = pos + 1
                break
            if char == "\n" and (pos == len(clean_content) - 1 or clean_content[pos - 1] in "。！？"):
                best_pos = pos
                break
        
        trimmed = clean_content[:best_pos].rstrip()
        if "【本章完】" not in trimmed:
            trimmed += "\n【本章完】"
        
        logger.info(f"[V10.0字数裁剪] 强制截断 {actual}→"
                   f"{len(trimmed.replace(chr(10),'').replace(' ',''))}字 "
                   f"(目标{target_words}, 标记:{'✓' if '【本章完】' in trimmed else '✗'})")
        return trimmed

    def _find_last_complete_sentence(self, text: str, target_words: int) -> str | None:
        """在文本中找到最后一个完整的句子结尾位置进行截断"""
        max_len = min(len(text), int(target_words * 1.12))
        min_len = max(int(target_words * 0.85), 200)
        
        if max_len <= min_len:
            return None
        
        search_region = text[min_len:max_len]
        
        for i in range(len(search_region) - 1, -1, -1):
            char = search_region[i]
            if char in "。！？":
                cut_pos = min_len + i + 1
                result = text[:cut_pos].rstrip()
                return result if result else None
        return None

    def _clean_text(self, text: str) -> str:
        """清理文本中的特殊标记（用于字数统计）"""
        return text.replace("【本章完】", "").replace("\n", "").replace(" ", "")

    def _build_validation_scores(self, evaluation: ExpertEvaluation) -> 'ValidationScores':
        """将ExpertEvaluation的维度评分映射为标准ValidationScores对象
        
        V2.0合规修订：expert-novel-v1使用标准数据模型返回评分，
        GUI通过ValidationScores的get_score_breakdown()显示评分详情。
        """
        from core.models import ValidationScores
        
        ds = evaluation.dimension_scores  # dict: {dimension_name: score}
        
        return ValidationScores(
            worldview_score=ds.get('worldview', 0.0),
            character_score=ds.get('character', 0.0),
            outline_score=ds.get('outline', 0.0),
            style_score=ds.get('style', 0.0),
            knowledge_reference_score=ds.get('knowledge', ds.get('knowledge_reference', 0.0)),
            writing_technique_score=ds.get('writing_technique', 0.0),
            word_count_score=ds.get('word_count', 0.0),
            context_coherence_score=ds.get('context_coherence', ds.get('reverse_feedback', 0.0)),
            ai_feeling_score=ds.get('ai_feeling', ds.get('naturalness', 0.0)),
            total_score=evaluation.total_score,
            has_chapter_end=True,
        )
    
    def _format_optimization_suggestions(self, raw_suggestions) -> list:
        """格式化优化建议为统一列表格式（V3.0修订）
        
        GUI层不再负责格式解析，插件层输出统一格式。
        """
        if isinstance(raw_suggestions, list):
            return raw_suggestions
        if isinstance(raw_suggestions, dict):
            result = []
            overall = raw_suggestions.get("overall_suggestion", "")
            if overall:
                result.append(overall)
            for dim, suggestion in raw_suggestions.get("dimension_suggestions", {}).items():
                result.append(f"[{dim}] {suggestion}")
            return result
        if isinstance(raw_suggestions, str) and raw_suggestions:
            return [raw_suggestions]
        return []
    
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
    
    def _load_knowledge_base(self, selected_categories=None) -> Dict:
        """加载知识库数据（V6.2修复：完整加载3大类知识库——领域/题材/写作技巧）"""
        knowledge_path = PROJECT_ROOT / "data" / "knowledge"
        
        if not knowledge_path.exists():
            logger.warning(f"[专家模式] 知识库路径不存在: {knowledge_path}")
            return {}
        
        knowledge = {}
        total_items = 0
        
        try:
            # === 1. 领域知识库（domains/）===
            domains_path = knowledge_path / "domains"
            if domains_path.exists():
                for f in domains_path.glob("*_init.json"):
                    try:
                        with open(f, 'r', encoding='utf-8') as fp:
                            data = json.load(fp)
                            domain_name = f.stem.replace("_init", "")
                            knowledge[f"domain_{domain_name}"] = data
                            total_items += 1
                    except Exception as e:
                        logger.warning(f"加载领域知识{f.name}失败: {e}")
            
            # === 2. 题材知识库（各题材子目录）===
            # 获取题材列表（排除非题材目录）
            exclude_dirs = {"writing_technique", "domains"}
            for item in knowledge_path.iterdir():
                if item.is_dir() and item.name not in exclude_dirs:
                    init_file = item / f"{item.name}_init.json"
                    if init_file.exists():
                        try:
                            with open(init_file, 'r', encoding='utf-8') as fp:
                                data = json.load(fp)
                                knowledge[f"genre_{item.name}"] = data
                                total_items += 1
                        except Exception as e:
                            logger.warning(f"加载题材知识{item.name}失败: {e}")
            
            # === 3. 写作技巧知识库（writing_technique/）===
            # 如果用户指定了分类，只加载指定的；否则加载全部
            all_technique_categories = ["narrative", "description", "rhetoric", "structure", 
                                       "special_sentence", "advanced"]
            categories_to_load = selected_categories if selected_categories else all_technique_categories
            
            for category in categories_to_load:
                category_path = knowledge_path / "writing_technique" / category
                if category_path.exists():
                    items = []
                    for f in category_path.glob("*.json"):
                        with open(f, 'r', encoding='utf-8') as fp:
                            data = json.load(fp)
                            items.append(data)
                            total_items += 1
                    if items:
                        knowledge[f"technique_{category}"] = items
            
            logger.info(f"[专家模式] 知识库加载完成: {len(knowledge)}个分类, {total_items}个条目"
                       f"{'(过滤: ' + str(selected_categories) + ')' if selected_categories else '(全部)'}")
            
        except Exception as e:
            logger.warning(f"加载知识库失败: {e}")
        
        return knowledge
    
    def _load_writing_techniques(self, selected_techniques=None) -> Dict:
        """加载写作技巧（V7.0修复：兼容扁平JSON和子目录两种目录结构）"""
        techniques_path = PROJECT_ROOT / "data" / "knowledge" / "writing_technique"
        
        if not techniques_path.exists():
            logger.warning(f"[专家模式] 写作技巧路径不存在: {techniques_path}")
            return {}
        
        techniques = {}
        total_items = 0
        
        try:
            # 全部领域列表
            all_areas = ["narrative", "description", "rhetoric", "structure", 
                        "special_sentence", "advanced"]
            # 如果用户指定了技巧分类，只加载指定的；否则加载全部
            areas_to_load = selected_techniques if selected_techniques else all_areas
            
            for area in areas_to_load:
                # V7.0修复：优先检查扁平JSON文件（actual structure），其次检查子目录
                flat_file = techniques_path / f"{area}.json"
                area_path = techniques_path / area
                
                if flat_file.exists():
                    # 扁平JSON文件：writing_technique/advanced.json
                    try:
                        with open(flat_file, 'r', encoding='utf-8') as fp:
                            data = json.load(fp)
                            # data可能是列表或字典，统一处理
                            if isinstance(data, list):
                                techniques[area] = data
                                total_items += len(data)
                            elif isinstance(data, dict):
                                techniques[area] = data
                                total_items += 1
                    except Exception as e:
                        logger.warning(f"[专家模式] 加载写作技巧文件失败: {flat_file} - {e}")
                elif area_path.exists() and area_path.is_dir():
                    # 子目录结构：writing_technique/advanced/*.json
                    items = []
                    for f in area_path.glob("*.json"):
                        try:
                            with open(f, 'r', encoding='utf-8') as fp:
                                data = json.load(fp)
                                items.append(data)
                                total_items += 1
                        except Exception as e:
                            logger.warning(f"[专家模式] 加载写作技巧文件失败: {f} - {e}")
                    if items:
                        techniques[area] = items
            
            logger.info(f"[专家模式] 写作技巧加载完成: {len(techniques)}个领域, {total_items}个技巧"
                       f"{'(过滤: ' + str(selected_techniques) + ')' if selected_techniques else '(全部)'}")
            
        except Exception as e:
            logger.warning(f"加载写作技巧失败: {e}")
        
        return techniques
    
    def _extract_relevant_knowledge(self, knowledge_base: Dict, outline_text: str = "") -> list:
        """
        V9.0新增：智能筛选与章节大纲相关的知识词条
        
        设计原则：
        1. 不是全量上传所有知识库条目
        2. 基于章节大纲内容做关键词匹配，只选明显相关的词条
        3. 每个分类最多取3-5条最相关的
        4. 返回格式化的{title: content}列表供prompt使用
        
        Args:
            knowledge_base: 已加载的知识库字典 {domain_xxx: data, genre_yyy: data, ...}
            outline_text: 章节大纲文本，用于相关性匹配
            
        Returns:
            list: [{title: str, content: str}, ...] 相关知识词条列表
        """
        if not knowledge_base:
            return []
        
        # 提取大纲中的关键词用于匹配（中文分词简化版：取2-4字词）
        outline_keywords = set()
        if outline_text and len(outline_text) > 2:
            import re
            # 提取大纲中可能的关键词（地名、人名、事件、物品等）
            words = re.findall(r'[\u4e00-\u9fff]{2,4}', outline_text)
            outline_keywords = set(words[:30])  # 取前30个关键词
        
        relevant_items = []
        
        for category_key, data in knowledge_base.items():
            items_to_check = []
            
            if isinstance(data, dict):
                # 格式1：{_init.json加载的dict} → 可能包含knowledge_points或直接是知识点
                if 'knowledge_points' in data and isinstance(data['knowledge_points'], list):
                    items_to_check = data['knowledge_points']
                elif 'title' in data or 'content' in data:
                    items_to_check = [data]
                else:
                    # 整个dict作为背景信息，提取关键描述
                    title = category_key.replace('domain_', '').replace('genre_', '').replace('technique_', '')
                    desc = data.get('description', '') or data.get('desc', '') or json.dumps(data, ensure_ascii=False)[:300]
                    if desc:
                        items_to_check = [{'title': title, 'content': desc}]
            
            elif isinstance(data, list):
                # 格式2：writing_technique下的列表
                items_to_check = data
            
            if not items_to_check:
                continue
            
            # 对每个条目计算与大纲的相关性
            matched = []
            for item in items_to_check:
                if not isinstance(item, dict):
                    continue
                
                title = item.get('title', '') or item.get('name', '')
                content = item.get('content', '') or item.get('description', '') or item.get('definition', '') or ''
                keywords = item.get('keywords', [])
                
                # 合并title+content+keywords为匹配文本
                full_text = f"{title} {content} {' '.join(keywords)}" if keywords else f"{title} {content}"
                
                # 计算匹配度
                relevance_score = 0.0
                if outline_keywords:
                    matches = sum(1 for kw in outline_keywords if kw in full_text)
                    relevance_score = matches / max(len(outline_keywords), 1)
                
                # 有任何匹配 或 大纲为空时取每类前3条
                if relevance_score > 0 or not outline_keywords:
                    matched.append({
                        'title': title,
                        'content': content or full_text,
                        'relevance': relevance_score,
                        'category': category_key
                    })
            
            # 按相关性排序，每类最多取3-5条
            matched.sort(key=lambda x: x['relevance'], reverse=True)
            top_n = 5 if outline_keywords else 3  # 有大纲时多取几条
            relevant_items.extend(matched[:top_n])
        
        # 全局按相关性排序，最终去重（基于title前20字符）
        seen_titles = set()
        final_items = []
        for item in sorted(relevant_items, key=lambda x: x['relevance'], reverse=True):
            title_key = item['title'][:20]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                final_items.append(item)
        
        # V9.3修复(P0)：兜底机制——当关键词匹配全部失败时（final_items为空），
        # 返回知识库中每个分类的基础信息作为参考
        # 根因分析："第1章被退货99次的女人"的大纲关键词与通用知识库条目无交集，
        # 导致26个分类→0条相关词条，知识库维度永远得低分
        if not final_items and knowledge_base:
            logger.warning(f"[专家模式] 知识库关键词匹配全部失败({len(outline_keywords)}个大纲词)，启用兜底策略")
            for category_key, data in knowledge_base.items():
                items_to_fallback = []
                if isinstance(data, list):
                    items_to_fallback = data[:2]
                elif isinstance(data, dict):
                    # V9.3修复：兼容多种字段名（knowledge_items/knowledge_points）
                    for field_name in ['knowledge_items', 'knowledge_points']:
                        if field_name in data and isinstance(data[field_name], list) and data[field_name]:
                            items_to_fallback = data[field_name][:2]
                            break
                    # 如果列表字段为空或不存在，用整个dict的描述信息作为兜底
                    if not items_to_fallback:
                        items_to_fallback = [data]
                
                for item in items_to_fallback:
                    if isinstance(item, dict):
                        # V9.3修复：兼容多种字段名提取title和content
                        title = (item.get('title') or item.get('name') or 
                                item.get('domain_cn') or item.get('domain') or 
                                category_key.replace('domain_', '').replace('genre_', ''))
                        content = (item.get('content') or item.get('description') or 
                                  item.get('definition') or json.dumps(item, ensure_ascii=False)[:300])
                        # 兜底模式放宽条件：只要有任何可用的文本就加入（最多8条）
                        if (title or content) and len(final_items) < 8:
                            final_items.append({
                                'title': title or '通用参考',
                                'content': content,
                                'relevance': 0.01,  # 极低相关性标记
                                'category': category_key
                            })
        
        logger.info(f"[专家模式] 知识库智能筛选: {len(knowledge_base)}个分类 → {len(final_items)}条相关词条"
                   f"{'(兜底模式)' if not any(i.get('relevance',0) > 0 for i in final_items) and final_items else '(基于大纲关键词匹配)' }")
        return final_items
    
    def _format_technique_guidance_for_prompt(self, techniques: Dict) -> str:
        """
        V9.2修复(P0)：将写作技巧数据格式化为LLM可理解的使用指导
        
        V9.0版问题：仅检查title/definition/method/example四个固定字段，
        但实际JSON文件可能使用name/description/how_to_use/usage_example等不同字段名，
        导致所有tip因len<10被过滤掉，返回空字符串→整个技巧块被跳过！
        
        设计原则：
        1. 兼容多种字段名（title/name、definition/description等）
        2. 即使没有详细定义，也输出领域名称和条目列表作为引导
        3. 控制总长度在500字以内
        """
        guidance_parts = []
        
        # 领域→中文名称映射
        domain_names = {
            'narrative': '叙事技巧', 'description': '描写技巧',
            'rhetoric': '修辞手法', 'structure': '结构技巧',
            'special_sentence': '特殊句式', 'advanced': '高级叙事'
        }
        
        total_tips = 0
        
        for domain_key, items in techniques.items():
            clean_domain = domain_key.replace('technique_', '')
            domain_label = domain_names.get(clean_domain, clean_domain)
            
            if isinstance(items, list) and items:
                tech_tips = []
                for item in items[:4]:  # 每领域最多4个
                    if isinstance(item, dict):
                        # V9.2：兼容多种字段名
                        name = (item.get('title') or item.get('name') or 
                                item.get('技巧名称') or item.get('technique_name') or '')
                        definition = (item.get('definition') or item.get('description') or 
                                     item.get('desc') or item.get('内容') or 
                                     item.get('content') or '')
                        method = (item.get('method') or item.get('how_to_use') or 
                                  item.get('usage_method') or item.get('运用方法') or '')
                        example = (item.get('example') or item.get('usage_example') or 
                                   item.get('示例') or '')
                        keywords = item.get('keywords', [])
                        
                        tip = ""
                        if name:
                            tip += f"【{name}】"
                        if definition:
                            tip += f"{definition}"
                        if method:
                            tip += f"。运用方法：{method[:120]}"
                        if example:
                            tip += f"。示例参考：{example[:80]}"
                        # 如果上面都没匹配到但item有其他内容
                        if len(tip) < 10:
                            # 提取item中所有非空字符串字段作为备选
                            for v in item.values():
                                if isinstance(v, str) and len(v) > 5:
                                    tip = f"【{domain_label}】{v[:200]}"
                                    break
                        
                        if len(tip) >= 10:  # 有实质内容才保留
                            tech_tips.append(tip)
                
                if tech_tips:
                    guidance_parts.append(f"\n▶ {domain_label}领域：")
                    for tip in tech_tips:
                        guidance_parts.append(f"  · {tip}")
                    total_tips += len(tech_tips)
                    
            elif isinstance(items, dict):
                name = (items.get('title') or items.get('name') or domain_label)
                desc = (items.get('description') or items.get('content') or 
                        json.dumps(items, ensure_ascii=False)[:200])
                if desc:
                    guidance_parts.append(f"\n▶ {name}：{desc[:200]}")
                    total_tips += 1
        
        if not guidance_parts:
            logger.warning(f"[专家模式] 写作技巧格式化结果为空！数据结构: "
                         f"{list(techniques.keys()) if techniques else '空'}")
            return ""
        
        header = "请在创作时自然运用以下技巧的写作方法——不是在文中提到技巧名称，而是让文本体现出这些技巧的特征："
        result = header + "\n".join(guidance_parts)
        
        if len(result) > 600:
            result = result[:597] + "..."
        
        logger.info(f"[专家模式] 技巧指导格式化完成: {len(result)}字符, {total_tips}个技巧项")
        return result

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
                "default": 0.75,  # V10.1修复：默认值与GUI对齐
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
