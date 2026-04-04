"""
逆向反馈分析器核心实现

V1.1版本
创建日期: 2026-03-24
修订日期: 2026-03-24

特性:
- 继承ReverseFeedbackPlugin接口
- 集成AnalyzerPlugin能力（大纲解析、人设提取、世界观解析）
- 接入LLM进行深度语义比对
- 缓存机制避免重复AI调用
- 集成全局CacheManager（V1.1新增）
"""

import hashlib
import json
import logging
import os
import pickle
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4
import concurrent.futures
import re

# 尝试导入全局缓存管理器
try:
    from core.cache_manager import get_cache_manager, generate_cache_key
    GLOBAL_CACHE_AVAILABLE = True
except ImportError:
    GLOBAL_CACHE_AVAILABLE = False

# OpenAI异常类型（P1-2修复）
try:
    from openai import (
        APIError,
        AuthenticationError,
        RateLimitError,
        APIConnectionError,
    )
except ImportError:
    # 如果openai未安装，使用自定义异常作为后备
    APIError = Exception
    AuthenticationError = Exception
    RateLimitError = Exception
    APIConnectionError = Exception

# jieba分词（P1-5修复）
try:
    import jieba
    import jieba.posseg as pseg
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

from core.plugin_interface import (
    AnalyzerPlugin,
    ConsistencyIssue,
    ConsistencyIssueType,
    ConsistencyReport,
    ConsistencySeverity,
    PluginContext,
    PluginMetadata,
    PluginState,
    PluginType,
)


# ============================================================================
# 自定义异常类型（P1-2修复）
# ============================================================================


class LLMError(Exception):
    """LLM调用基础异常"""
    pass


class LLMTimeoutError(LLMError):
    """LLM调用超时异常"""
    pass


class LLMConnectionError(LLMError):
    """LLM连接异常"""
    pass


class LLMAuthenticationError(LLMError):
    """LLM认证异常"""
    pass


class LLMRateLimitError(LLMError):
    """LLM速率限制异常"""
    pass


class LLMResponseError(LLMError):
    """LLM响应异常"""
    pass


class JSONParseError(Exception):
    """JSON解析异常"""
    pass

logger = logging.getLogger(__name__)

# ============================================================================
# 日志级别使用规范（P2-1修复）
# ============================================================================
# DEBUG   : 详细调试信息（内部状态、流程追踪）
# INFO    : 正常运行事件（初始化、关闭、关键操作完成）
# WARNING : 可恢复的异常情况（降级、后备方案）
# ERROR   : 错误但不影响整体运行（操作失败、异常捕获）
# CRITICAL: 严重错误（系统崩溃、不可恢复错误）
# ============================================================================


# ============================================================================
# 缓存管理
# ============================================================================


@dataclass
class CacheEntry:
    """缓存条目"""

    result: Dict[str, Any]
    created_at: float
    ttl_seconds: float
    hit_count: int = 0


class AnalysisCache:
    """
    分析结果缓存

    避免对相同内容的重复AI调用
    
    支持内存缓存和可选的磁盘持久化
    """

    def __init__(self, max_size: int = 500, default_ttl: float = 3600, 
                 persist_path: Optional[str] = None):
        """
        初始化缓存

        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间（秒）
            persist_path: 缓存持久化路径（可选，P1-3修复）
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.Lock()
        self._persist_path = Path(persist_path) if persist_path else None
        
        # 如果指定了持久化路径，尝试加载已有缓存
        if self._persist_path:
            self.load_from_disk()

    def _generate_key(
        self,
        chapter_text: str,
        settings: Dict[str, Any],
        analysis_type: str = "consistency"
    ) -> str:
        """
        生成缓存键

        使用内容哈希避免存储大量文本
        """
        content = f"{analysis_type}:{chapter_text[:500]}:{json.dumps(settings, sort_keys=True, ensure_ascii=False)[:1000]}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get(
        self,
        chapter_text: str,
        settings: Dict[str, Any],
        analysis_type: str = "consistency"
    ) -> Optional[Dict[str, Any]]:
        """获取缓存结果"""
        key = self._generate_key(chapter_text, settings, analysis_type)

        with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]

            # 检查是否过期
            if time.time() - entry.created_at > entry.ttl_seconds:
                del self._cache[key]
                return None

            # 命中计数
            entry.hit_count += 1
            # 移到末尾（LRU）
            self._cache.move_to_end(key)

            return entry.result

    def set(
        self,
        chapter_text: str,
        settings: Dict[str, Any],
        result: Dict[str, Any],
        ttl: Optional[float] = None,
        analysis_type: str = "consistency"
    ) -> None:
        """设置缓存结果"""
        key = self._generate_key(chapter_text, settings, analysis_type)

        with self._lock:
            # 淘汰旧条目
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = CacheEntry(
                result=result,
                created_at=time.time(),
                ttl_seconds=ttl or self._default_ttl
            )

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total_hits = sum(e.hit_count for e in self._cache.values())
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "total_hits": total_hits,
            }

    # ========================================================================
    # 持久化方法（P1-3修复）
    # ========================================================================

    def save_to_disk(self, path: Optional[str] = None) -> bool:
        """
        将缓存保存到磁盘
        
        Args:
            path: 保存路径（可选，默认使用初始化时的路径）
            
        Returns:
            是否保存成功
        """
        save_path = Path(path) if path else self._persist_path
        if not save_path:
            logger.debug("未指定缓存持久化路径，跳过保存")
            return False
        
        try:
            # 确保目录存在
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            with self._lock:
                # 过滤过期条目
                current_time = time.time()
                valid_entries = {
                    k: v for k, v in self._cache.items()
                    if current_time - v.created_at <= v.ttl_seconds
                }
                
                # 序列化并保存
                cache_data = {
                    "version": "1.1.0",
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    "entries": {k: {"result": v.result, "created_at": v.created_at, 
                                    "ttl_seconds": v.ttl_seconds, "hit_count": v.hit_count}
                               for k, v in valid_entries.items()}
                }
                
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"缓存已保存到 {save_path}，共 {len(valid_entries)} 条")
                return True
                
        except (IOError, OSError) as e:
            logger.error(f"缓存保存失败: {e}")
            return False
        except Exception as e:
            logger.error(f"缓存序列化失败: {e}")
            return False

    def load_from_disk(self, path: Optional[str] = None) -> bool:
        """
        从磁盘加载缓存
        
        Args:
            path: 加载路径（可选，默认使用初始化时的路径）
            
        Returns:
            是否加载成功
        """
        load_path = Path(path) if path else self._persist_path
        if not load_path or not load_path.exists():
            logger.debug("缓存文件不存在或未指定路径，跳过加载")
            return False
        
        try:
            # 检查文件是否为空
            if load_path.stat().st_size == 0:
                logger.debug("缓存文件为空，跳过加载")
                return False
                
            with open(load_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 验证版本
            version = cache_data.get("version", "1.0.0")
            if version not in ["1.0.0", "1.1.0"]:
                logger.warning(f"不支持的缓存版本: {version}")
                return False
            
            current_time = time.time()
            loaded_count = 0
            expired_count = 0
            
            with self._lock:
                self._cache.clear()
                for k, v in cache_data.get("entries", {}).items():
                    # 检查是否过期
                    if current_time - v["created_at"] <= v["ttl_seconds"]:
                        self._cache[k] = CacheEntry(
                            result=v["result"],
                            created_at=v["created_at"],
                            ttl_seconds=v["ttl_seconds"],
                            hit_count=v.get("hit_count", 0)
                        )
                        loaded_count += 1
                    else:
                        expired_count += 1
            
            logger.info(f"从 {load_path} 加载缓存，有效 {loaded_count} 条，过期 {expired_count} 条")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"缓存文件JSON解析失败: {e}")
            return False
        except (IOError, OSError) as e:
            logger.error(f"缓存文件读取失败: {e}")
            return False
        except Exception as e:
            logger.error(f"缓存加载失败: {e}")
            return False


# ============================================================================
# LLM调用封装
# ============================================================================


class LLMAnalyzer:
    """
    LLM语义分析封装

    支持DeepSeek/OpenAI等模型
    """

    # 类常量（P2-2修复）
    DEFAULT_TIMEOUT = 60
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_MAX_TOKENS = 2000
    DEFAULT_TEMPERATURE = 0.7
    MAX_CHARACTERS_IN_PROMPT = 10
    MAX_CHAPTER_LENGTH = 2000
    MAX_OUTLINE_LENGTH = 1000
    MAX_WORLDVIEW_LENGTH = 1000

    def __init__(self, llm_client=None):
        """
        初始化LLM分析器

        Args:
            llm_client: LLM客户端实例（可选，后续可设置）
        """
        self._llm_client = llm_client
        self._timeout = self.DEFAULT_TIMEOUT
        self._max_retries = self.DEFAULT_MAX_RETRIES

    def set_llm_client(self, llm_client) -> None:
        """设置LLM客户端"""
        self._llm_client = llm_client

    def set_timeout(self, timeout: int) -> None:
        """设置超时时间"""
        self._timeout = timeout

    def analyze_consistency(
        self,
        chapter_text: str,
        outline: str,
        characters: List[Dict[str, Any]],
        worldview: str,
        chapter_id: str = ""
    ) -> Dict[str, Any]:
        """
        分析章节与设定的一致性

        Args:
            chapter_text: 章节文本
            outline: 大纲文本
            characters: 人物设定列表
            worldview: 世界观设定
            chapter_id: 章节ID

        Returns:
            分析结果字典
        """
        if not self._llm_client:
            logger.warning("LLM客户端未设置，使用规则检测")
            return self._rule_based_analysis(
                chapter_text, outline, characters, worldview, chapter_id
            )

        # 构建分析提示
        prompt = self._build_analysis_prompt(
            chapter_text, outline, characters, worldview, chapter_id
        )

        # 调用LLM（P1-2修复：区分异常类型）
        try:
            response = self._call_llm(prompt)
            return self._parse_llm_response(response, chapter_id)
        except LLMTimeoutError as e:
            logger.error(f"LLM调用超时: {e}")
            return self._rule_based_analysis(
                chapter_text, outline, characters, worldview, chapter_id
            )
        except LLMConnectionError as e:
            logger.error(f"LLM连接失败: {e}")
            return self._rule_based_analysis(
                chapter_text, outline, characters, worldview, chapter_id
            )
        except LLMAuthenticationError as e:
            logger.error(f"LLM认证失败: {e}")
            return self._rule_based_analysis(
                chapter_text, outline, characters, worldview, chapter_id
            )
        except LLMRateLimitError as e:
            logger.warning(f"LLM速率限制: {e}")
            return self._rule_based_analysis(
                chapter_text, outline, characters, worldview, chapter_id
            )
        except LLMResponseError as e:
            logger.error(f"LLM响应异常: {e}")
            return self._rule_based_analysis(
                chapter_text, outline, characters, worldview, chapter_id
            )
        except LLMError as e:
            logger.error(f"LLM调用失败: {e}")
            return self._rule_based_analysis(
                chapter_text, outline, characters, worldview, chapter_id
            )

    def _build_analysis_prompt(
        self,
        chapter_text: str,
        outline: str,
        characters: List[Dict[str, Any]],
        worldview: str,
        chapter_id: str
    ) -> str:
        """构建分析提示"""
        # 简化人物设定格式（使用类常量）
        char_summary = []
        for char in characters[:self.MAX_CHARACTERS_IN_PROMPT]:
            char_summary.append(
                f"- {char.get('name', '未知')}: "
                f"性格={char.get('personality', '未设定')}, "
                f"能力={char.get('ability', '未设定')}, "
                f"背景={char.get('background', '未设定')}"
            )

        prompt = f"""你是一个专业的小说一致性分析助手。请分析以下章节内容与项目设定的冲突。

## 章节ID
{chapter_id or '未指定'}

## 章节内容（摘要前{self.MAX_CHAPTER_LENGTH}字）
{chapter_text[:self.MAX_CHAPTER_LENGTH]}

## 大纲设定
{outline[:self.MAX_OUTLINE_LENGTH] if outline else '未提供'}

## 人物设定
{chr(10).join(char_summary) if char_summary else '未提供'}

## 世界观设定
{worldview[:self.MAX_WORLDVIEW_LENGTH] if worldview else '未提供'}

## 分析要求
请仔细对比章节内容与设定，识别以下类型的冲突：
1. **人物冲突**：角色行为、能力、性格与设定不符
2. **大纲冲突**：情节发展与大纲规划矛盾
3. **世界观冲突**：场景、规则、设定与世界观数据不符

## 输出格式（JSON）
请以JSON格式输出，包含以下字段：
```json
{{
  "issues": [
    {{
      "issue_type": "character|outline|worldview",
      "severity": "low|medium|high",
      "element_name": "冲突元素名称",
      "description": "冲突描述",
      "suggested_fix": "建议修正方案",
      "original_content": "原始设定内容",
      "confidence": 0.8
    }}
  ],
  "summary": "分析摘要"
}}
```

如果未发现冲突，返回空issues数组并说明"未发现明显冲突"。
"""
        return prompt

    def _call_llm(self, prompt: str) -> str:
        """调用LLM模型（带超时控制和异常区分）
        
        Args:
            prompt: 分析提示词
            
        Returns:
            LLM响应文本
            
        Raises:
            LLMTimeoutError: 超时错误
            LLMConnectionError: 连接错误
            LLMAuthenticationError: 认证错误
            LLMRateLimitError: 速率限制错误
            LLMResponseError: 响应错误
            RuntimeError: 不支持的客户端类型
        """
        # 支持不同客户端接口
        if hasattr(self._llm_client, 'call'):
            call_func = self._llm_client.call
        elif hasattr(self._llm_client, 'generate'):
            call_func = self._llm_client.generate
        else:
            raise RuntimeError("不支持的LLM客户端类型，需要实现call()或generate()方法")
        
        # 使用线程池实现超时控制
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(call_func, prompt)
            try:
                return future.result(timeout=self._timeout)
            except concurrent.futures.TimeoutError:
                future.cancel()
                raise LLMTimeoutError(f"LLM调用超时（{self._timeout}秒）")
            except ConnectionError as e:
                raise LLMConnectionError(f"LLM连接失败: {e}")
            except APIConnectionError as e:
                raise LLMConnectionError(f"LLM连接失败: {e}")
            except AuthenticationError as e:
                raise LLMAuthenticationError(f"LLM认证失败: {e}")
            except RateLimitError as e:
                raise LLMRateLimitError(f"LLM速率限制: {e}")
            except APIError as e:
                raise LLMResponseError(f"LLM API错误: {e}")

    def _parse_llm_response(self, response: str, chapter_id: str) -> Dict[str, Any]:
        """解析LLM响应（P1-2修复：区分JSON解析异常）"""
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                # 添加章节引用
                for issue in result.get("issues", []):
                    issue["chapter_reference"] = chapter_id
                return result
        except json.JSONDecodeError as e:
            logger.warning(f"LLM响应JSON解析失败: {e}")
            raise JSONParseError(f"JSON解析失败: {e}")

        # 解析失败，返回空结果
        return {
            "issues": [],
            "summary": "LLM响应解析失败，请检查输出格式"
        }

    def _rule_based_analysis(
        self,
        chapter_text: str,
        outline: str,
        characters: List[Dict[str, Any]],
        worldview: str,
        chapter_id: str
    ) -> Dict[str, Any]:
        """
        基于规则的分析（LLM不可用时的降级方案）
        
        P1-5修复：使用jieba分词增强人名识别
        """
        issues = []

        # 1. 人物检测（P1-5修复：jieba增强）
        char_names = [char.get("name", "") for char in characters if char.get("name")]
        
        if JIEBA_AVAILABLE:
            # 使用jieba进行命名实体识别
            words = pseg.cut(chapter_text)
            # 提取人名标记（nr）
            detected_names = {word.word for word in words if word.flag == 'nr'}
            
            # 合并设定中的人名和检测到的人名
            all_names = set(char_names) | detected_names
            
            # 检测未在设定中出现的人物
            unknown_names = detected_names - set(char_names)
            if unknown_names:
                issues.append({
                    "issue_type": "character",
                    "severity": "medium",
                    "element_name": "未知角色",
                    "description": f"检测到章节中出现未在设定中的角色：{', '.join(list(unknown_names)[:5])}",
                    "suggested_fix": "建议将这些角色添加到人物设定中",
                    "original_content": "无",
                    "chapter_reference": chapter_id,
                    "confidence": 0.7
                })
        else:
            # 降级到简单字符串匹配
            all_names = set(char_names)
            logger.debug("jieba未安装，使用简单字符串匹配")

        # 2. 人物能力与性格检测
        for char in characters:
            name = char.get("name", "")
            if not name:
                continue

            # 检测角色是否出现
            if name in chapter_text or (JIEBA_AVAILABLE and name in all_names):
                # 检测能力关键词
                ability = char.get("ability", "")
                if ability and ability not in chapter_text:
                    # 角色出现但能力未提及（低优先级提示）
                    issues.append({
                        "issue_type": "character",
                        "severity": "low",
                        "element_name": name,
                        "description": f"角色'{name}'在章节中出现，但其核心能力'{ability}'未体现",
                        "suggested_fix": f"考虑在相关情节中体现角色的'{ability}'能力",
                        "original_content": f"能力：{ability}",
                        "chapter_reference": chapter_id,
                        "confidence": 0.6
                    })

                # P1-5修复：使用jieba分析性格关键词
                personality = char.get("personality", "")
                if personality and JIEBA_AVAILABLE:
                    # 提取性格关键词
                    personality_keywords = set(jieba.cut(personality))
                    # 章节中的性格相关描述
                    chapter_keywords = self._extract_keywords(chapter_text)
                    # 检测性格关键词覆盖率
                    overlap = personality_keywords & chapter_keywords
                    if len(personality_keywords) > 0 and len(overlap) / len(personality_keywords) < 0.3:
                        issues.append({
                            "issue_type": "character",
                            "severity": "low",
                            "element_name": name,
                            "description": f"角色'{name}'的性格特征'{personality}'在章节中体现不足",
                            "suggested_fix": f"建议通过行为描写体现角色的'{personality}'性格",
                            "original_content": f"性格：{personality}",
                            "chapter_reference": chapter_id,
                            "confidence": 0.5
                        })

        # 3. 大纲关键词检测
        if outline:
            # 提取大纲中的关键事件
            outline_keywords = self._extract_keywords(outline)
            chapter_keywords = self._extract_keywords(chapter_text)

            # 检测大纲关键事件是否体现
            missing_keywords = outline_keywords - chapter_keywords
            if missing_keywords and len(missing_keywords) > 3:
                issues.append({
                    "issue_type": "outline",
                    "severity": "medium",
                    "element_name": "大纲关键元素",
                    "description": f"章节内容缺少大纲中的关键元素：{', '.join(list(missing_keywords)[:5])}",
                    "suggested_fix": "检查章节是否遗漏大纲规划的关键情节",
                    "original_content": outline[:200],
                    "chapter_reference": chapter_id,
                    "confidence": 0.5
                })

        return {
            "issues": issues,
            "summary": f"规则检测完成，发现{len(issues)}个潜在问题"
        }

    def _extract_keywords(self, text: str) -> set:
        """提取关键词（简化版本）"""
        # 简单的关键词提取：提取2-4字词
        import re
        words = set()
        # 提取中文词组
        for match in re.finditer(r'[\u4e00-\u9fa5]{2,4}', text):
            word = match.group()
            # 排除常见停用词
            if word not in ['这是', '那是', '不是', '没有', '一个', '这个', '那个', '他的', '她的']:
                words.add(word)
        return words


# ============================================================================
# 插件主类
# ============================================================================


class ReverseFeedbackAnalyzer(AnalyzerPlugin):
    """
    逆向反馈分析器

    分析已生成章节与项目设定的一致性，检测冲突并生成修正建议。
    """

    def __init__(self):
        """初始化插件"""
        metadata = PluginMetadata(
            id="reverse-feedback-analyzer",
            name="逆向反馈分析器",
            version="1.0.0",
            description="分析章节与设定的一致性，检测冲突并生成修正建议",
            author="AI工程师",
            plugin_type=PluginType.ANALYZER,
            priority=100,
            permissions=["llm.call", "project.read", "cache.readwrite"]
        )
        super().__init__(metadata)

        # 内部组件
        self._cache: Optional[AnalysisCache] = None
        self._llm_analyzer: Optional[LLMAnalyzer] = None

        # V5模块引用（用于调用现有分析能力）
        self._outline_parser = None
        self._character_manager = None
        self._worldview_parser = None

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id="reverse-feedback-analyzer",
            name="逆向反馈分析器",
            version="1.0.0",
            description="分析章节与设定的一致性，检测冲突并生成修正建议",
            author="AI工程师",
            plugin_type=PluginType.ANALYZER,
            priority=100,
            permissions=["llm.call", "project.read", "cache.readwrite"]
        )

    def initialize(self, context: PluginContext) -> bool:
        """
        初始化插件

        Args:
            context: 插件上下文

        Returns:
            是否初始化成功
        """
        try:
            # 调用父类初始化
            success = super().initialize(context)
            if not success:
                return False

            # 初始化缓存（P1-3修复：支持持久化）
            config = context.config_manager.get_plugin_config("reverse-feedback-analyzer")
            cache_size = config.get("max_cache_size", 500)
            cache_ttl = config.get("cache_ttl_seconds", 3600)
            
            # 获取缓存持久化路径
            cache_persist_path = config.get("cache_persist_path")
            if cache_persist_path:
                # 如果是相对路径，基于项目根目录
                if not os.path.isabs(cache_persist_path):
                    cache_persist_path = os.path.join(
                        context.project_root if hasattr(context, 'project_root') else os.getcwd(),
                        cache_persist_path
                    )
            
            self._cache = AnalysisCache(
                max_size=cache_size, 
                default_ttl=cache_ttl,
                persist_path=cache_persist_path
            )

            # 初始化LLM分析器
            self._llm_analyzer = LLMAnalyzer()
            llm_timeout = config.get("llm_timeout_seconds", 60)
            self._llm_analyzer.set_timeout(llm_timeout)

            # 尝试获取V5模块引用
            self._init_v5_modules(context)

            # 尝试获取LLM客户端
            self._init_llm_client(context)

            self._state = PluginState.ACTIVE
            logger.info("逆向反馈分析器初始化完成")
            return True

        except Exception as e:
            logger.error(f"逆向反馈分析器初始化失败: {e}")
            self._state = PluginState.ERROR
            return False

    def _init_v5_modules(self, context: PluginContext) -> None:
        """初始化V5模块引用"""
        v5_modules = context.v5_modules if hasattr(context, 'v5_modules') else {}

        # 获取大纲解析器
        if "outline_parser" in v5_modules:
            self._outline_parser = v5_modules["outline_parser"]
        else:
            # 尝试动态导入
            try:
                from scripts.outline_parser_v3 import OutlineParserV3
                self._outline_parser = OutlineParserV3()
                logger.info("动态加载大纲解析器成功")
            except ImportError:
                logger.warning("无法加载大纲解析器")

        # 获取人物管理器
        if "character_manager" in v5_modules:
            self._character_manager = v5_modules["character_manager"]
        else:
            try:
                from scripts.enhanced_character_manager import EnhancedCharacterManager
                self._character_manager = EnhancedCharacterManager()
                logger.info("动态加载人物管理器成功")
            except ImportError:
                logger.warning("无法加载人物管理器")

        # 获取世界观解析器（从插件系统）
        if "worldview_parser" in v5_modules:
            self._worldview_parser = v5_modules["worldview_parser"]
        else:
            try:
                # 使用插件系统加载世界观解析器
                from plugins.worldview-parser-v1.plugin import WorldviewParserPlugin
                self._worldview_parser = WorldviewParserPlugin()
                logger.info("动态加载世界观解析器成功")
            except ImportError:
                logger.warning("无法加载世界观解析器")

    def _init_llm_client(self, context: PluginContext) -> None:
        """初始化LLM客户端"""
        # 尝试从ServiceLocator获取
        try:
            service_locator = context.service_locator
            if hasattr(service_locator, 'get'):
                llm_client = service_locator.get("llm_client")
                if llm_client:
                    self._llm_analyzer.set_llm_client(llm_client)
                    logger.info("从ServiceLocator获取LLM客户端成功")
                    return
        except Exception as e:
            logger.debug(f"从ServiceLocator获取LLM客户端失败: {e}")

        # 尝试从ConfigManager获取配置并创建
        try:
            config = context.config_manager
            api_key = config.get("llm.api_key")
            api_base = config.get("llm.api_base", "https://api.deepseek.com")

            if api_key:
                from openai import OpenAI
                client = OpenAI(api_key=api_key, base_url=api_base)

                # 包装为简单接口（带超时支持）
                class SimpleLLMClient:
                    def __init__(self, client, model="deepseek-chat", timeout=60):
                        self._client = client
                        self._model = model
                        self._timeout = timeout

                    def call(self, prompt: str) -> str:
                        response = self._client.chat.completions.create(
                            model=self._model,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.7,
                            max_tokens=2000,
                            timeout=self._timeout  # 添加超时控制
                        )
                        return response.choices[0].message.content

                self._llm_analyzer.set_llm_client(SimpleLLMClient(client))
                logger.info("创建LLM客户端成功")
        except Exception as e:
            logger.warning(f"创建LLM客户端失败: {e}，将使用规则检测模式")

    def shutdown(self) -> bool:
        """关闭插件（P1-3修复：保存缓存）"""
        if self._cache:
            # 尝试保存缓存到磁盘
            self._cache.save_to_disk()
            self._cache.clear()
        self._state = PluginState.UNLOADED
        logger.info("逆向反馈分析器已关闭")
        return True

    # ========================================================================
    # AnalyzerPlugin 接口实现
    # ========================================================================

    def analyze(
        self,
        content: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        分析内容（通用接口）

        Args:
            content: 待分析内容（章节文本）
            options: 分析选项
                - settings: 项目设定字典
                - chapter_id: 章节ID

        Returns:
            分析结果
        """
        options = options or {}
        settings = options.get("settings", {})
        chapter_id = options.get("chapter_id", "")

        report = self.analyze_chapter_vs_settings(
            chapter_text=content,
            current_settings=settings,
            chapter_id=chapter_id
        )

        return report.to_dict()

    def get_supported_formats(self) -> List[str]:
        """支持的输入格式"""
        return ["txt", "md", "json"]

    def get_analysis_types(self) -> List[str]:
        """支持的分析类型"""
        return [
            "consistency_check",
            "conflict_detection",
            "setting_validation",
            "character_consistency",
            "worldview_consistency",
        ]

    # ========================================================================
    # ReverseFeedbackPlugin 接口实现
    # ========================================================================

    def analyze_chapter_vs_settings(
        self,
        chapter_text: str,
        current_settings: Dict[str, Any],
        chapter_id: str = "",
    ) -> ConsistencyReport:
        """
        分析章节内容与当前设定的冲突

        Args:
            chapter_text: 章节文本内容
            current_settings: 当前项目设定
            chapter_id: 章节ID或标题

        Returns:
            ConsistencyReport: 包含冲突列表的报告
        """
        # 创建报告
        report = ConsistencyReport(
            project_name=current_settings.get("project_name", "未命名项目"),
            chapters_analyzed=1
        )

        if not chapter_text or not chapter_text.strip():
            report.summary = "章节内容为空，跳过分析"
            return report

        # 检查缓存（优先使用全局缓存管理器）
        cached_result = None
        if GLOBAL_CACHE_AVAILABLE:
            cache_manager = get_cache_manager()
            cache_key = generate_cache_key(chapter_text[:500], current_settings)
            cached_result = cache_manager.get("analysis", cache_key)
        
        if cached_result is None:
            # 回退到本地缓存
            cached_result = self._cache.get(chapter_text, current_settings)
        
        if cached_result:
            logger.debug("使用缓存的分析结果")
            for issue_data in cached_result.get("issues", []):
                report.add_issue(ConsistencyIssue.from_dict(issue_data))
            report.summary = cached_result.get("summary", "来自缓存")
            return report

        # 提取设定数据
        outline = current_settings.get("outline", "")
        characters = current_settings.get("characters", [])
        worldview = current_settings.get("worldview", "")

        # 使用V5模块增强分析（可选）
        enhanced_settings = self._enhance_settings_with_v5(
            chapter_text, outline, characters, worldview
        )
        if enhanced_settings:
            outline = enhanced_settings.get("outline", outline)
            characters = enhanced_settings.get("characters", characters)
            worldview = enhanced_settings.get("worldview", worldview)

        # 调用LLM分析
        result = self._llm_analyzer.analyze_consistency(
            chapter_text=chapter_text,
            outline=outline,
            characters=characters,
            worldview=worldview,
            chapter_id=chapter_id
        )

        # 构建冲突列表
        for issue_data in result.get("issues", []):
            issue = ConsistencyIssue(
                issue_type=ConsistencyIssueType(issue_data.get("issue_type", "outline")),
                severity=ConsistencySeverity(issue_data.get("severity", "medium")),
                element_name=issue_data.get("element_name", ""),
                description=issue_data.get("description", ""),
                suggested_fix=issue_data.get("suggested_fix", ""),
                original_content=issue_data.get("original_content", ""),
                chapter_reference=chapter_id,
                confidence=issue_data.get("confidence", 0.8)
            )
            report.add_issue(issue)

        report.summary = result.get(
            "summary",
            f"发现{len(report.issues)}个冲突项"
        )

        # 缓存结果（优先使用全局缓存管理器）
        report_dict = report.to_dict()
        if GLOBAL_CACHE_AVAILABLE:
            cache_manager = get_cache_manager()
            cache_key = generate_cache_key(chapter_text[:500], current_settings)
            cache_manager.set("analysis", cache_key, report_dict)
        # 同时存储到本地缓存作为备份
        self._cache.set(chapter_text, current_settings, report_dict)

        return report

    def analyze_project(
        self,
        project_data: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> ConsistencyReport:
        """
        分析整个项目的一致性

        Args:
            project_data: 完整项目数据
            options: 分析选项

        Returns:
            ConsistencyReport: 综合分析报告
        """
        options = options or {}

        # 创建综合报告
        report = ConsistencyReport(
            project_name=project_data.get("project_name", "未命名项目")
        )

        # 提取设定
        settings = {
            "outline": project_data.get("outline", ""),
            "characters": project_data.get("characters", []),
            "worldview": project_data.get("worldview", ""),
        }

        # 分析所有章节
        chapters = project_data.get("chapters", [])
        for chapter in chapters:
            chapter_id = chapter.get("id", chapter.get("title", ""))
            chapter_text = chapter.get("content", "")

            if not chapter_text:
                continue

            # 分析单个章节
            chapter_report = self.analyze_chapter_vs_settings(
                chapter_text=chapter_text,
                current_settings=settings,
                chapter_id=chapter_id
            )

            # 合并冲突项
            for issue in chapter_report.issues:
                report.add_issue(issue)

        report.chapters_analyzed = len(chapters)
        report.summary = self._generate_project_summary(report, len(chapters))

        return report

    def generate_corrections(
        self,
        report: ConsistencyReport,
        current_settings: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        根据冲突报告生成修正后的设定

        Args:
            report: 一致性分析报告
            current_settings: 当前项目设定
            options: 修正选项

        Returns:
            修正后的设定字典
        """
        options = options or {}
        auto_fix_low = options.get("auto_fix_low", True)
        preserve_original = options.get("preserve_original", True)

        result = {
            "updated_outline": current_settings.get("outline", ""),
            "updated_characters": current_settings.get("characters", []),
            "updated_worldview": current_settings.get("worldview", ""),
            "suggestions": [],
            "backup": None
        }

        # 保留原始设定备份
        if preserve_original:
            result["backup"] = {
                "outline": current_settings.get("outline", ""),
                "characters": current_settings.get("characters", []),
                "worldview": current_settings.get("worldview", ""),
                "backup_time": datetime.now(timezone.utc).isoformat()
            }

        # 按类型分组冲突
        outline_issues = []
        character_issues = []
        worldview_issues = []

        for issue in report.issues:
            if issue.severity == ConsistencySeverity.LOW and not auto_fix_low:
                continue

            if issue.issue_type == ConsistencyIssueType.OUTLINE:
                outline_issues.append(issue)
            elif issue.issue_type == ConsistencyIssueType.CHARACTER:
                character_issues.append(issue)
            else:
                worldview_issues.append(issue)

        # 生成建议
        if outline_issues:
            result["suggestions"].append(
                f"大纲冲突：建议修正{len(outline_issues)}处，"
                f"高优先级{sum(1 for i in outline_issues if i.severity == ConsistencySeverity.HIGH)}处"
            )

        if character_issues:
            result["suggestions"].append(
                f"人物设定冲突：建议修正{len(character_issues)}处，"
                f"高优先级{sum(1 for i in character_issues if i.severity == ConsistencySeverity.HIGH)}处"
            )
            # 更新人物设定
            result["updated_characters"] = self._update_characters(
                current_settings.get("characters", []),
                character_issues
            )

        if worldview_issues:
            result["suggestions"].append(
                f"世界观冲突：建议修正{len(worldview_issues)}处"
            )

        return result

    def _enhance_settings_with_v5(
        self,
        chapter_text: str,
        outline: str,
        characters: List[Dict[str, Any]],
        worldview: str
    ) -> Optional[Dict[str, Any]]:
        """使用V5模块增强设定提取"""
        result = {}

        # 使用大纲解析器增强大纲信息
        if self._outline_parser and outline:
            try:
                parsed_outline = self._outline_parser.parse(outline)
                if parsed_outline:
                    result["outline"] = self._format_parsed_outline(parsed_outline)
            except Exception as e:
                logger.debug(f"大纲解析增强失败: {e}")

        # 使用人物管理器增强人物信息
        if self._character_manager and characters:
            try:
                # 提取章节中的人物特征
                enhanced_chars = self._enhance_characters_from_chapter(
                    chapter_text, characters
                )
                if enhanced_chars:
                    result["characters"] = enhanced_chars
            except Exception as e:
                logger.debug(f"人物信息增强失败: {e}")

        return result if result else None

    def _format_parsed_outline(self, parsed: Any) -> str:
        """格式化解析后的大纲"""
        if isinstance(parsed, dict):
            # 简单格式化
            parts = []
            if "main_plot" in parsed:
                parts.append(f"主线: {parsed['main_plot']}")
            if "chapters" in parsed:
                for i, chap in enumerate(parsed["chapters"][:5]):
                    parts.append(f"第{i+1}章: {chap.get('title', '未命名')}")
            return "\n".join(parts)
        return str(parsed)

    def _enhance_characters_from_chapter(
        self,
        chapter_text: str,
        characters: List[Dict[str, Any]]
    ) -> Optional[List[Dict[str, Any]]]:
        """从章节中增强人物信息"""
        enhanced = []

        for char in characters:
            name = char.get("name", "")
            if not name or name not in chapter_text:
                continue

            # 复制原始设定
            enhanced_char = char.copy()

            # 检测章节中的行为模式（简化版本）
            # 这里可以扩展更复杂的NLP分析
            enhanced.append(enhanced_char)

        return enhanced if enhanced else None

    def _update_characters(
        self,
        characters: List[Dict[str, Any]],
        issues: List[ConsistencyIssue]
    ) -> List[Dict[str, Any]]:
        """更新人物设定"""
        updated = [c.copy() for c in characters]

        for issue in issues:
            element_name = issue.element_name
            # 找到对应人物
            for char in updated:
                if char.get("name") == element_name:
                    # 根据建议更新（简化版本）
                    if issue.suggested_fix:
                        # 将建议添加到备注
                        notes = char.get("notes", "")
                        char["notes"] = f"{notes}\n[自动修正建议]: {issue.suggested_fix}".strip()

        return updated

    def _generate_project_summary(
        self,
        report: ConsistencyReport,
        total_chapters: int
    ) -> str:
        """生成项目分析摘要"""
        high = report.high_priority_count
        medium = report.medium_priority_count
        low = report.low_priority_count

        if high > 0:
            return f"分析{total_chapters}章，发现{len(report.issues)}个冲突，其中{high}个高优先级需立即修正"
        elif medium > 0:
            return f"分析{total_chapters}章，发现{len(report.issues)}个冲突，{medium}个中等优先级建议处理"
        elif low > 0:
            return f"分析{total_chapters}章，发现{len(report.issues)}个轻微问题"
        else:
            return f"分析{total_chapters}章，未发现明显冲突"

    # ========================================================================
    # 工具方法
    # ========================================================================

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        if self._cache:
            return self._cache.get_stats()
        return {"size": 0, "max_size": 0, "total_hits": 0}

    def clear_cache(self) -> None:
        """清空缓存"""
        if self._cache:
            self._cache.clear()
            logger.info("逆向反馈分析器缓存已清空")
