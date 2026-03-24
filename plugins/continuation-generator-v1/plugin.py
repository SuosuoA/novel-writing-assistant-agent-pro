#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
续写生成器插件 V1.2 - 智能小说续写功能

核心功能：
1. 基于起始文本智能续写
2. 支持5种续写方向（自然/特定/情感/动作/对话）
3. 上下文智能感知（自动读取大纲/人设/世界观/前文）
4. 流式生成支持
5. 多版本生成与选择最佳

V1.1新增（2026-03-24）：
- ProjectContextManager: 项目上下文管理器
- 自动读取项目设定（大纲/人设/世界观）
- 章节选择时自动加载前文概要，避免重复

V1.2新增（2026-03-24）：
- LLM调用超时保护机制（concurrent.futures强制超时）
- 自定义异常类型（LLMError/TimeoutError/AuthError/ConnectionError）
- 缓存持久化机制（save_to_disk/load_from_disk）
- 增强人物设定解析（支持JSON/YAML格式）
- 智能章节概要生成（关键词提取+句子选择）
- 魔法数字提取为类常量

设计依据：
- 经验文档/9.5.1设计续写插件接口说明✅️.md
- core/plugin_interface.py ContinuationPlugin接口

创建日期: 2026-03-24
作者: AI工程师
更新日期: 2026-03-24
更新作者: 高级开发工程师
"""

import logging
import time
import uuid
import json
import os
import re
import yaml
import hashlib
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Generator, Tuple
from datetime import datetime
from dataclasses import dataclass, field


# ============================================================================
# 自定义异常类型（P0-2修复）
# ============================================================================

class LLMError(Exception):
    """LLM调用基础异常"""
    pass


class LLMTimeoutError(LLMError):
    """LLM调用超时异常"""
    pass


class LLMAuthenticationError(LLMError):
    """LLM认证异常（API Key无效或过期）"""
    pass


class LLMConnectionError(LLMError):
    """LLM连接异常（网络问题）"""
    pass


class LLMRateLimitError(LLMError):
    """LLM速率限制异常"""
    pass

# 导入核心接口
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.plugin_interface import (
    ContinuationPlugin,
    PluginMetadata,
    PluginType,
    PluginContext,
)
from core.models import (
    ContinuationRequest,
    ContinuationResult,
    ContinuationMetadata,
    ContinuationDirection,
    GenerationRequest,
    GenerationResult,
)


# ============================================================================
# 项目上下文管理器
# ============================================================================

@dataclass
class ProjectContext:
    """项目上下文数据结构"""
    project_path: str = ""
    outline: str = ""
    characters: List[Dict[str, Any]] = field(default_factory=list)
    worldview: str = ""
    style_profile: Dict[str, Any] = field(default_factory=dict)
    recent_chapters: List[str] = field(default_factory=list)
    chapter_summaries: Dict[str, str] = field(default_factory=dict)  # 章节ID -> 概要
    current_chapter_id: Optional[str] = None
    last_updated: Optional[datetime] = None


class ProjectContextManager:
    """
    项目上下文管理器
    
    负责自动读取和管理项目的设定数据（大纲、人设、世界观），
    以及章节内容的前文概要。
    
    数据来源优先级：
    1. 直接传入的数据（最高优先级）
    2. 项目管理器接口（_project_manager）
    3. 文件系统扫描（最低优先级）
    
    V1.2新增：
    - 缓存持久化机制（save_to_disk/load_from_disk）
    - 增强人物设定解析（支持JSON/YAML）
    - 智能章节概要生成
    """
    
    def __init__(self, project_path: Optional[str] = None):
        """
        初始化上下文管理器
        
        参数:
            project_path: 项目根目录路径
        """
        self._project_path = project_path
        self._project_manager: Optional[Any] = None
        self._context_cache: Optional[ProjectContext] = None
        self._logger: Optional[logging.Logger] = None
        
        # V1.2新增：缓存文件路径
        self._cache_file: Optional[Path] = None
        if project_path:
            self._cache_file = Path(project_path) / ".continuation_cache" / "context_cache.json"
        
        # 设定文件路径（相对项目根目录）
        self._outline_patterns = ["大纲", "outline", "章节大纲"]
        self._character_patterns = ["人物设定", "characters", "人物"]
        self._worldview_patterns = ["世界观", "worldview", "设定"]
        self._chapters_patterns = ["章节", "chapters", "正文"]
    
    def set_project_path(self, path: str):
        """设置项目路径"""
        self._project_path = path
        self._context_cache = None  # 清除缓存
        # V1.2新增：更新缓存文件路径
        self._cache_file = Path(path) / ".continuation_cache" / "context_cache.json" if path else None
    
    def set_project_manager(self, manager: Any):
        """设置项目管理器"""
        self._project_manager = manager
        self._context_cache = None  # 清除缓存
    
    def set_logger(self, logger: logging.Logger):
        """设置日志器"""
        self._logger = logger
    
    # =========================================================================
    # V1.2新增：缓存持久化机制
    # =========================================================================
    
    def save_cache_to_disk(self) -> bool:
        """
        将上下文缓存保存到磁盘
        
        返回:
            是否保存成功
        """
        if not self._context_cache or not self._cache_file:
            return False
        
        try:
            # 确保目录存在
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 序列化上下文
            cache_data = {
                "project_path": self._context_cache.project_path,
                "outline": self._context_cache.outline,
                "characters": self._context_cache.characters,
                "worldview": self._context_cache.worldview,
                "style_profile": self._context_cache.style_profile,
                "last_updated": self._context_cache.last_updated.isoformat() if self._context_cache.last_updated else None,
                "version": "1.2"
            }
            
            # 写入文件
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            if self._logger:
                self._logger.debug(f"[ContextManager] 缓存已保存到: {self._cache_file}")
            
            return True
            
        except Exception as e:
            if self._logger:
                self._logger.warning(f"[ContextManager] 保存缓存失败: {e}")
            return False
    
    def load_cache_from_disk(self) -> Optional[ProjectContext]:
        """
        从磁盘加载上下文缓存
        
        返回:
            加载的上下文，如果失败则返回None
        """
        if not self._cache_file or not self._cache_file.exists():
            return None
        
        try:
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 验证版本
            if cache_data.get("version") != "1.2":
                if self._logger:
                    self._logger.debug("[ContextManager] 缓存版本不匹配，跳过加载")
                return None
            
            # 验证项目路径
            if cache_data.get("project_path") != self._project_path:
                if self._logger:
                    self._logger.debug("[ContextManager] 项目路径不匹配，跳过加载")
                return None
            
            # 重建上下文对象
            context = ProjectContext(
                project_path=cache_data.get("project_path", ""),
                outline=cache_data.get("outline", ""),
                characters=cache_data.get("characters", []),
                worldview=cache_data.get("worldview", ""),
                style_profile=cache_data.get("style_profile", {}),
                last_updated=datetime.fromisoformat(cache_data["last_updated"]) if cache_data.get("last_updated") else None
            )
            
            self._context_cache = context
            
            if self._logger:
                self._logger.debug(f"[ContextManager] 缓存已从磁盘加载")
            
            return context
            
        except Exception as e:
            if self._logger:
                self._logger.warning(f"[ContextManager] 加载缓存失败: {e}")
            return None
    
    def clear_cache(self):
        """清除内存缓存和磁盘缓存"""
        self._context_cache = None
        
        if self._cache_file and self._cache_file.exists():
            try:
                self._cache_file.unlink()
                if self._logger:
                    self._logger.debug("[ContextManager] 磁盘缓存已清除")
            except Exception as e:
                if self._logger:
                    self._logger.warning(f"[ContextManager] 清除磁盘缓存失败: {e}")
    
    def get_full_context(
        self,
        chapter_id: Optional[str] = None,
        include_recent_chapters: int = 5,
        force_refresh: bool = False
    ) -> ProjectContext:
        """
        获取完整的项目上下文
        
        Args:
            chapter_id: 当前章节ID（用于获取前文概要）
            include_recent_chapters: 包含的最近章节数
            force_refresh: 是否强制刷新缓存
            
        Returns:
            ProjectContext: 完整的项目上下文
        """
        # 检查缓存
        if not force_refresh and self._context_cache and not chapter_id:
            return self._context_cache
        
        context = ProjectContext(project_path=self._project_path or "")
        
        # 1. 获取大纲
        context.outline = self._get_outline()
        
        # 2. 获取人物设定
        context.characters = self._get_characters()
        
        # 3. 获取世界观
        context.worldview = self._get_worldview()
        
        # 4. 获取风格档案
        context.style_profile = self._get_style_profile()
        
        # 5. 获取最近章节
        if include_recent_chapters > 0:
            context.recent_chapters = self._get_recent_chapters(include_recent_chapters)
        
        # 6. 获取章节概要（用于续写）
        if chapter_id:
            context.chapter_summaries = self._get_chapter_summaries_before(chapter_id)
            context.current_chapter_id = chapter_id
        
        context.last_updated = datetime.now()
        
        # 缓存（不含特定章节的上下文）
        if not chapter_id:
            self._context_cache = context
        
        if self._logger:
            self._logger.info(
                f"[ContextManager] 上下文加载完成: "
                f"大纲={len(context.outline)}字符, "
                f"人物={len(context.characters)}个, "
                f"世界观={len(context.worldview)}字符"
            )
        
        return context
    
    def _get_outline(self) -> str:
        """获取大纲内容"""
        # 优先从项目管理器获取
        if self._project_manager:
            try:
                if hasattr(self._project_manager, 'get_outline'):
                    outline = self._project_manager.get_outline()
                    if outline:
                        return outline
            except Exception as e:
                if self._logger:
                    self._logger.warning(f"[ContextManager] 从项目管理器获取大纲失败: {e}")
        
        # 从文件系统扫描
        if self._project_path:
            outline = self._read_from_patterns(self._outline_patterns)
            if outline:
                return outline
        
        return ""
    
    def _get_characters(self) -> List[Dict[str, Any]]:
        """获取人物设定"""
        characters = []
        
        # 优先从项目管理器获取
        if self._project_manager:
            try:
                if hasattr(self._project_manager, 'get_characters'):
                    chars = self._project_manager.get_characters()
                    if chars:
                        if isinstance(chars, list):
                            characters = chars
                        elif isinstance(chars, dict):
                            # 转换字典格式为列表
                            for name, info in chars.items():
                                characters.append({
                                    "name": name,
                                    **info
                                })
                        elif isinstance(chars, str):
                            # 文本格式，尝试解析
                            characters = self._parse_characters_from_text(chars)
            except Exception as e:
                if self._logger:
                    self._logger.warning(f"[ContextManager] 从项目管理器获取人物设定失败: {e}")
        
        # 从文件系统扫描
        if not characters and self._project_path:
            char_text = self._read_from_patterns(self._character_patterns)
            if char_text:
                characters = self._parse_characters_from_text(char_text)
        
        return characters
    
    def _get_worldview(self) -> str:
        """获取世界观设定"""
        # 优先从项目管理器获取
        if self._project_manager:
            try:
                if hasattr(self._project_manager, 'get_worldview'):
                    worldview = self._project_manager.get_worldview()
                    if worldview:
                        return worldview
            except Exception as e:
                if self._logger:
                    self._logger.warning(f"[ContextManager] 从项目管理器获取世界观失败: {e}")
        
        # 从文件系统扫描
        if self._project_path:
            worldview = self._read_from_patterns(self._worldview_patterns)
            if worldview:
                return worldview
        
        return ""
    
    def _get_style_profile(self) -> Dict[str, Any]:
        """获取风格档案"""
        style_profile = {}
        
        # 优先从项目管理器获取
        if self._project_manager:
            try:
                if hasattr(self._project_manager, 'get_style_profile'):
                    style = self._project_manager.get_style_profile()
                    if style:
                        style_profile = style if isinstance(style, dict) else {}
            except Exception as e:
                if self._logger:
                    self._logger.warning(f"[ContextManager] 从项目管理器获取风格档案失败: {e}")
        
        return style_profile
    
    def _get_recent_chapters(self, count: int) -> List[str]:
        """获取最近的章节内容"""
        chapters = []
        
        # 优先从项目管理器获取
        if self._project_manager:
            try:
                if hasattr(self._project_manager, 'get_recent_chapters'):
                    chapters = self._project_manager.get_recent_chapters(count)
                elif hasattr(self._project_manager, 'list_chapters'):
                    chapter_list = self._project_manager.list_chapters()
                    if chapter_list:
                        # 获取最近的章节
                        for chapter_info in chapter_list[-count:]:
                            if isinstance(chapter_info, dict):
                                title = chapter_info.get('title', '')
                            else:
                                title = str(chapter_info)
                            
                            if hasattr(self._project_manager, 'get_chapter_content'):
                                content = self._project_manager.get_chapter_content(title)
                                if content:
                                    chapters.append(content)
            except Exception as e:
                if self._logger:
                    self._logger.warning(f"[ContextManager] 获取最近章节失败: {e}")
        
        # 从文件系统扫描
        if not chapters and self._project_path:
            chapters = self._scan_chapter_files(count)
        
        return chapters
    
    def _get_chapter_summaries_before(self, chapter_id: str) -> Dict[str, str]:
        """
        获取指定章节之前的所有章节概要
        
        用于续写时避免重复已发生的内容。
        
        Args:
            chapter_id: 当前章节ID
            
        Returns:
            章节ID到概要的映射
        """
        summaries = {}
        
        # 从项目管理器获取章节列表
        if self._project_manager:
            try:
                if hasattr(self._project_manager, 'list_chapters'):
                    chapter_list = self._project_manager.list_chapters()
                    if chapter_list:
                        # 找到当前章节的位置
                        current_index = -1
                        for i, chapter in enumerate(chapter_list):
                            cid = chapter.get('id', '') if isinstance(chapter, dict) else str(chapter)
                            if cid == chapter_id:
                                current_index = i
                                break
                        
                        # 获取之前的章节概要
                        if current_index > 0:
                            for chapter in chapter_list[:current_index]:
                                cid = chapter.get('id', '') if isinstance(chapter, dict) else str(chapter)
                                title = chapter.get('title', '') if isinstance(chapter, dict) else str(chapter)
                                
                                # 获取章节内容并生成概要
                                if hasattr(self._project_manager, 'get_chapter_content'):
                                    content = self._project_manager.get_chapter_content(title)
                                    if content:
                                        # 生成概要（取前500字）
                                        summary = self._generate_chapter_summary(content)
                                        summaries[cid] = summary
            except Exception as e:
                if self._logger:
                    self._logger.warning(f"[ContextManager] 获取章节概要失败: {e}")
        
        return summaries
    
    def _generate_chapter_summary(self, content: str, max_length: int = 500) -> str:
        """
        生成章节概要（V1.2增强版）
        
        使用关键词提取和句子选择算法生成智能概要，
        而非简单截断。
        
        参数:
            content: 章节内容
            max_length: 最大长度
            
        返回:
            章节概要
        """
        if not content:
            return ""
        
        # 如果内容很短，直接返回
        if len(content) <= max_length:
            return content
        
        # V1.2智能概要生成算法
        # 1. 提取关键句子（包含人物、动作、转折的句子）
        key_sentences = self._extract_key_sentences(content)
        
        # 2. 如果提取到关键句子，组合成概要
        if key_sentences:
            summary = "。".join(key_sentences[:5])  # 最多5个关键句
            if len(summary) <= max_length:
                return summary + "..."
        
        # 3. 降级方案：取前max_length字符，在句号处截断
        summary = content[:max_length]
        last_period = summary.rfind('。')
        if last_period > max_length // 2:
            summary = summary[:last_period + 1]
        
        return summary + "..."
    
    def _extract_key_sentences(self, content: str) -> List[str]:
        """
        提取关键句子（V1.2新增）
        
        识别包含重要信息的句子：
        - 人物名称
        - 关键动作动词
        - 转折词
        - 情感词汇
        
        参数:
            content: 章节内容
            
        返回:
            关键句子列表
        """
        sentences = [s.strip() for s in content.split('。') if s.strip()]
        key_sentences = []
        
        # 关键词列表
        action_verbs = ['说', '走', '跑', '看', '想', '问', '答', '笑', '哭', '喊', '叫', '拿', '放', '打', '杀', '救', '跑', '追', '逃']
        transition_words = ['但是', '然而', '可是', '不过', '却', '竟然', '忽然', '突然', '终于', '原来']
        emotion_words = ['愤怒', '悲伤', '高兴', '恐惧', '惊讶', '失望', '感动', '痛苦', '快乐', '焦虑']
        
        for sentence in sentences:
            score = 0
            
            # 检测动作动词
            if any(verb in sentence for verb in action_verbs):
                score += 2
            
            # 检测转折词
            if any(word in sentence for word in transition_words):
                score += 3
            
            # 检测情感词汇
            if any(word in sentence for word in emotion_words):
                score += 2
            
            # 检测对话（引号）
            if '"' in sentence or '"' in sentence or '「' in sentence:
                score += 2
            
            # 句子长度适中（20-100字）
            if 20 <= len(sentence) <= 100:
                score += 1
            
            # 阈值判断
            if score >= 3:
                key_sentences.append(sentence)
        
        return key_sentences
    
    def _read_from_patterns(self, patterns: List[str]) -> str:
        """
        根据模式从文件系统读取设定内容
        
        Args:
            patterns: 文件名模式列表
            
        Returns:
            读取到的内容
        """
        if not self._project_path:
            return ""
        
        project_path = Path(self._project_path)
        
        for pattern in patterns:
            # 尝试多种文件扩展名
            for ext in ['.txt', '.md', '.yaml', '.json', '']:
                # 尝试直接匹配
                file_path = project_path / f"{pattern}{ext}"
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding='utf-8')
                        if content:
                            return content
                    except Exception as e:
                        if self._logger:
                            self._logger.warning(f"[ContextManager] 读取文件失败: {file_path}: {e}")
                
                # 尝试在子目录中查找
                for subdir in ['', '设定', '大纲', '人物', '世界观', 'data']:
                    if subdir:
                        file_path = project_path / subdir / f"{pattern}{ext}"
                    else:
                        file_path = project_path / f"{pattern}{ext}"
                    
                    if file_path.exists():
                        try:
                            content = file_path.read_text(encoding='utf-8')
                            if content:
                                return content
                        except Exception as e:
                            if self._logger:
                                self._logger.warning(f"[ContextManager] 读取文件失败: {file_path}: {e}")
        
        return ""
    
    def _parse_characters_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        从文本解析人物设定（V1.2增强版）
        
        支持多种格式：
        1. JSON格式：[{\"name\": \"xxx\", \"role\": \"xxx\", ...}]
        2. YAML格式：- name: xxx\\n  role: xxx
        3. 文本格式1：姓名：xxx，角色：xxx，性格：xxx
        4. 文本格式2：- 姓名 | 角色 | 性格
        
        参数:
            text: 人物设定文本
            
        返回:
            人物列表
        """
        if not text or not text.strip():
            return []
        
        text = text.strip()
        characters = []
        
        # V1.2新增：尝试JSON解析
        if text.startswith('[') and text.endswith(']'):
            try:
                chars = json.loads(text)
                if isinstance(chars, list):
                    for char in chars:
                        if isinstance(char, dict) and char.get('name'):
                            characters.append(char)
                    if characters:
                        return characters
            except json.JSONDecodeError:
                pass  # 降级到其他格式
        
        # V1.2新增：尝试YAML解析
        if text.startswith('- ') or text.startswith('-\n'):
            try:
                chars = yaml.safe_load(text)
                if isinstance(chars, list):
                    for char in chars:
                        if isinstance(char, dict) and char.get('name'):
                            characters.append(char)
                    if characters:
                        return characters
            except yaml.YAMLError:
                pass  # 降级到其他格式
        
        # 原有文本解析逻辑（保留兼容性）
        lines = text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            char_info = {}
            
            # 尝试解析 "姓名：xxx，角色：xxx" 格式
            if '：' in line or ':' in line:
                parts = re.split(r'[，,]', line)
                for part in parts:
                    if '：' in part or ':' in part:
                        key, value = re.split(r'[：:]', part, 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if '姓名' in key or '名字' in key or 'name' in key.lower():
                            char_info['name'] = value
                        elif '角色' in key or '身份' in key or 'role' in key.lower():
                            char_info['role'] = value
                        elif '性格' in key or '特点' in key or 'trait' in key.lower():
                            char_info['traits'] = [t.strip() for t in value.split('、')]
            
            # 尝试解析 "- 姓名 | 角色" 格式
            elif '|' in line:
                parts = [p.strip() for p in line.lstrip('-').split('|')]
                if parts:
                    char_info['name'] = parts[0]
                    if len(parts) > 1:
                        char_info['role'] = parts[1]
                    if len(parts) > 2:
                        char_info['traits'] = [parts[2]]
            
            # 简单姓名提取
            else:
                char_info['name'] = line.lstrip('-').strip()
            
            if char_info.get('name'):
                characters.append(char_info)
        
        return characters
    
    def _scan_chapter_files(self, count: int) -> List[str]:
        """
        扫描章节文件
        
        Args:
            count: 要获取的章节数
            
        Returns:
            章节内容列表
        """
        if not self._project_path:
            return []
        
        chapters = []
        project_path = Path(self._project_path)
        
        # 查找章节目录
        chapter_dirs = []
        for pattern in self._chapters_patterns:
            chapter_dir = project_path / pattern
            if chapter_dir.exists() and chapter_dir.is_dir():
                chapter_dirs.append(chapter_dir)
        
        # 如果没有专门的章节目录，在根目录查找
        if not chapter_dirs:
            chapter_dirs = [project_path]
        
        # 收集章节文件
        chapter_files = []
        for chapter_dir in chapter_dirs:
            for ext in ['.txt', '.md']:
                chapter_files.extend(chapter_dir.glob(f"**/*第*章*{ext}"))
                chapter_files.extend(chapter_dir.glob(f"**/chapter_*{ext}"))
        
        # 按修改时间排序，取最新的
        chapter_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        for file_path in chapter_files[:count]:
            try:
                content = file_path.read_text(encoding='utf-8')
                if content:
                    chapters.append(content)
            except Exception as e:
                if self._logger:
                    self._logger.warning(f"[ContextManager] 读取章节文件失败: {file_path}: {e}")
        
        return chapters
    
    def get_chapter_context_for_continuation(
        self,
        chapter_id: str,
        include_settings: bool = True
    ) -> Dict[str, Any]:
        """
        获取用于续写的章节上下文
        
        当用户选择已生成章节作为起始文本时，自动加载该章节之前
        的剧情概要，避免续写时重复已发生的内容。
        
        Args:
            chapter_id: 章节ID
            include_settings: 是否包含项目设定
            
        Returns:
            上下文字典，包含：
            - outline: 大纲
            - characters: 人物设定
            - worldview: 世界观
            - style_profile: 风格档案
            - previous_plot_summary: 前文概要
        """
        context = self.get_full_context(
            chapter_id=chapter_id,
            include_recent_chapters=0,
            force_refresh=not include_settings
        )
        
        # 生成前文概要
        previous_plot_summary = ""
        if context.chapter_summaries:
            summary_parts = []
            for cid, summary in context.chapter_summaries.items():
                summary_parts.append(f"【{cid}】\n{summary}")
            previous_plot_summary = "\n\n".join(summary_parts)
        
        return {
            "outline": context.outline if include_settings else "",
            "characters": context.characters if include_settings else [],
            "worldview": context.worldview if include_settings else "",
            "style_profile": context.style_profile if include_settings else {},
            "previous_plot_summary": previous_plot_summary
        }


class ContinuationGeneratorPlugin(ContinuationPlugin):
    """
    续写生成器插件
    
    继承自 ContinuationPlugin，实现智能续写功能。
    
    核心能力：
    1. generate_continuation - 单次续写生成
    2. generate_multiple_versions - 多版本生成
    3. stream_continuation - 流式续写生成
    4. select_best_version - 选择最佳版本
    
    V1.2修复：
    - LLM调用超时保护机制
    - 自定义异常类型
    - 魔法数字提取为类常量
    """
    
    # =========================================================================
    # 类常量（P1-5修复：提取魔法数字）
    # =========================================================================
    
    DEFAULT_TIMEOUT = 120           # 默认超时时间（秒）
    MAX_TOKENS_LIMIT = 4096         # 最大token限制
    MAX_VERSIONS = 5                # 最大版本数
    MAX_RETRIES = 3                 # 最大重试次数
    DEFAULT_TEMPERATURE = 0.8       # 默认温度
    MIN_TOKENS = 500                # 最小token数
    TOKEN_RATIO = 1.5               # 中文字符/token比例
    MAX_HISTORY_SIZE = 50           # 最大历史记录数
    HISTORY_KEEP_SIZE = 30          # 保留历史记录数
    MAX_KEY_SENTENCES = 5           # 概要最大关键句数
    SUMMARY_MAX_LENGTH = 500        # 概要最大长度
    
    def __init__(self):
        """初始化续写生成器插件"""
        metadata = PluginMetadata(
            id="continuation-generator-v1",  # P1-6修复：统一ID
            name="续写生成器 V1",
            version="1.2.0",  # V1.2版本
            description="智能小说续写功能，支持多种续写方向和上下文智能感知",
            author="AI工程师",
            plugin_type=PluginType.GENERATOR,
            permissions=["llm.call", "cache.readwrite"]
        )
        super().__init__(metadata)
        
        # 配置参数
        self.default_model: str = "deepseek-chat"
        self.default_temperature: float = self.DEFAULT_TEMPERATURE
        self.max_retries: int = self.MAX_RETRIES
        
        # API客户端
        self._api_client: Optional[Any] = None
        
        # 日志器
        self._logger: Optional[logging.Logger] = None
        
        # 生成历史（用于调试）
        self._generation_history: List[Dict[str, Any]] = []
        
        # V1.1新增：项目上下文管理器
        self._context_manager: Optional[ProjectContextManager] = None
        
        # V1.2新增：超时时间
        self._timeout: int = self.DEFAULT_TIMEOUT
    
    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id="continuation-generator-v1",  # P1-6修复：统一ID
            name="续写生成器 V1",
            version="1.2.0",
            description="智能小说续写功能，支持多种续写方向和上下文智能感知",
            author="AI工程师",
            plugin_type=PluginType.GENERATOR,
            permissions=["llm.call", "cache.readwrite"]
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
            self._context = context
            self._logger = context.logger or logging.getLogger(__name__)
            
            # V1.1新增: 初始化上下文管理器
            self._context_manager = ProjectContextManager()
            self._context_manager.set_logger(self._logger)
            
            # 从服务定位器获取API客户端
            if hasattr(context, 'service_locator') and context.service_locator:
                try:
                    ai_service = context.service_locator.get("ai_service")
                    if ai_service:
                        self._api_client = ai_service
                        self._logger.info("[ContinuationGenerator] 从服务定位器获取AI服务成功")
                except Exception as e:
                    self._logger.warning(f"[ContinuationGenerator] 无法从服务定位器获取AI服务: {e}")
                
                # V1.1新增: 尝试获取项目管理器
                try:
                    project_manager = context.service_locator.get("project_manager")
                    if project_manager:
                        self._context_manager.set_project_manager(project_manager)
                        self._logger.info("[ContinuationGenerator] 从服务定位器获取项目管理器成功")
                except Exception as e:
                    self._logger.debug(f"[ContinuationGenerator] 无法从服务定位器获取项目管理器: {e}")
            
            # 从配置读取默认参数
            if hasattr(context, 'config_manager') and context.config_manager:
                try:
                    config = context.config_manager.get_config()
                    if isinstance(config, dict):
                        llm_config = config.get('llm', {})
                        self.default_model = llm_config.get('model', self.default_model)
                        self.default_temperature = llm_config.get('temperature', self.default_temperature)
                        
                        # V1.1新增: 从配置获取项目路径
                        save_path = config.get('save_path', '')
                        if save_path:
                            self._context_manager.set_project_path(save_path)
                except Exception as e:
                    self._logger.warning(f"[ContinuationGenerator] 读取配置失败: {e}")
            
            self._logger.info("[ContinuationGenerator] 续写生成器初始化完成 (V1.1 with ContextManager)")
            return True
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[ContinuationGenerator] 初始化失败: {e}")
            return False
    
    def set_api_client(self, api_client: Any):
        """
        设置API客户端
        
        Args:
            api_client: OpenAI兼容的API客户端实例
        """
        self._api_client = api_client
        if self._logger:
            self._logger.info("[ContinuationGenerator] API客户端已设置")
    
    def set_project_manager(self, project_manager: Any):
        """
        设置项目管理器
        
        Args:
            project_manager: 项目管理器实例
        """
        if self._context_manager:
            self._context_manager.set_project_manager(project_manager)
            if self._logger:
                self._logger.info("[ContinuationGenerator] 项目管理器已设置")
    
    def set_project_path(self, path: str):
        """
        设置项目路径
        
        Args:
            path: 项目根目录路径
        """
        if self._context_manager:
            self._context_manager.set_project_path(path)
            if self._logger:
                self._logger.info(f"[ContinuationGenerator] 项目路径已设置: {path}")
    
    def get_context_manager(self) -> Optional[ProjectContextManager]:
        """
        获取上下文管理器
        
        Returns:
            ProjectContextManager实例
        """
        return self._context_manager
    
    def auto_load_context(
        self,
        chapter_id: Optional[str] = None,
        include_recent_chapters: int = 5
    ) -> ProjectContext:
        """
        自动加载项目上下文
        
        从项目管理器或文件系统自动读取大纲、人设、世界观等设定，
        以及章节的前文概要。
        
        Args:
            chapter_id: 当前章节ID（可选，用于获取前文概要）
            include_recent_chapters: 包含的最近章节数
            
        Returns:
            ProjectContext: 项目上下文
        """
        if not self._context_manager:
            if self._logger:
                self._logger.warning("[ContinuationGenerator] 上下文管理器未初始化")
            return ProjectContext()
        
        return self._context_manager.get_full_context(
            chapter_id=chapter_id,
            include_recent_chapters=include_recent_chapters
        )
    
    def generate_continuation_with_auto_context(
        self,
        starting_text: str,
        word_count: int,
        direction: str = "natural",
        chapter_id: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> ContinuationResult:
        """
        带自动上下文加载的续写生成
        
        自动读取项目的设定（大纲、人设、世界观）和章节的前文概要，
        然后生成续写内容。
        
        Args:
            starting_text: 起始文本
            word_count: 目标字数
            direction: 续写方向
            chapter_id: 当前章节ID（用于获取前文概要）
            temperature: 生成温度
            **kwargs: 其他参数
            
        Returns:
            ContinuationResult: 续写结果
        """
        # 自动加载上下文
        context = self.auto_load_context(
            chapter_id=chapter_id,
            include_recent_chapters=5
        )
        
        # 构建请求
        request = ContinuationRequest(
            starting_text=starting_text,
            word_count=word_count,
            direction=direction,
            outline=context.outline or kwargs.get('outline'),
            characters=context.characters or kwargs.get('characters'),
            worldview=context.worldview or kwargs.get('worldview'),
            style_profile=context.style_profile or kwargs.get('style_profile'),
            previous_chapters=context.recent_chapters or kwargs.get('previous_chapters'),
            temperature=temperature or self.default_temperature,
            preserve_ending=kwargs.get('preserve_ending', False),
            direction_hint=kwargs.get('direction_hint')
        )
        
        # 添加前文概要到请求（如果有）
        if context.chapter_summaries:
            # 将前文概要添加到previous_chapters的开头
            summary_text = "\n\n".join([
                f"【{cid}概要】\n{summary}"
                for cid, summary in context.chapter_summaries.items()
            ])
            if summary_text:
                request.previous_chapters = [summary_text] + (request.previous_chapters or [])
        
        # 执行续写
        return self.generate_continuation(request)
    
    # =========================================================================
    # 核心方法：续写生成
    # =========================================================================
    
    def generate_continuation(
        self, 
        request: ContinuationRequest
    ) -> ContinuationResult:
        """
        执行续写 - 核心方法
        
        基于起始文本和上下文，生成续写内容。
        
        Args:
            request: 续写请求参数
            
        Returns:
            ContinuationResult: 续写结果
        """
        start_time = time.time()
        
        try:
            # 1. 构建Prompt
            prompt = self._build_continuation_prompt(request)
            
            # 2. 计算max_tokens
            max_tokens = self._calculate_max_tokens(request.word_count)
            
            # 3. 获取温度参数
            temperature = request.temperature if request.temperature else self.default_temperature
            
            # 4. 调用大模型API
            if self._logger:
                self._logger.info(f"[ContinuationGenerator] 开始续写 - 方向: {request.direction}, 字数: {request.word_count}")
            
            generated_text = self._call_llm_api(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            # 5. 后处理
            processed_text = self._post_process(generated_text, request)
            
            # 6. 计算元数据
            generation_time = time.time() - start_time
            word_count = len(processed_text)
            
            # 7. 构建结果
            metadata = ContinuationMetadata(
                model_name=self.default_model,
                provider=self._get_provider_name(),
                generation_time=generation_time,
                tokens_used=self._estimate_tokens(prompt, processed_text),
                iterations=1,
                coherence_score=self._estimate_coherence(request.starting_text, processed_text),
                style_match_score=0.8,  # 默认值，可通过验证器计算
                context_length=len(prompt),
                starting_text_length=len(request.starting_text),
                timestamp=datetime.now()
            )
            
            # 8. 生成建议
            suggestions = self._generate_suggestions(request, processed_text)
            
            # 记录历史
            self._record_generation(request, processed_text, metadata)
            
            return ContinuationResult(
                text=processed_text,
                word_count=word_count,
                metadata=metadata,
                success=True,
                error=None,
                suggestions=suggestions
            )
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[ContinuationGenerator] 续写失败: {e}")
            
            return ContinuationResult(
                text="",
                word_count=0,
                metadata=ContinuationMetadata(),
                success=False,
                error=str(e),
                suggestions=None
            )
    
    def generate_multiple_versions(
        self,
        request: ContinuationRequest,
        num_versions: int = 3,
        temperatures: Optional[List[float]] = None
    ) -> List[ContinuationResult]:
        """
        生成多个版本的续写
        
        用于"选择最佳版本"功能，生成多个不同风格的版本供用户选择。
        
        Args:
            request: 续写请求参数
            num_versions: 生成版本数量（默认3个）
            temperatures: 每个版本的温度参数（可选）
            
        Returns:
            List[ContinuationResult]: 多个续写结果
        """
        if self._logger:
            self._logger.info(f"[ContinuationGenerator] 开始生成{num_versions}个版本")
        
        # 默认温度分布：低/中/高
        if temperatures is None:
            if num_versions == 3:
                temperatures = [0.6, 0.8, 1.0]  # 保守/平衡/创意
            else:
                temperatures = [0.7 + i * 0.1 for i in range(num_versions)]
        
        results = []
        for i, temp in enumerate(temperatures[:num_versions]):
            # 创建新请求，修改温度
            version_request = ContinuationRequest(
                starting_text=request.starting_text,
                word_count=request.word_count,
                direction=request.direction,
                direction_hint=request.direction_hint,
                outline=request.outline,
                characters=request.characters,
                worldview=request.worldview,
                style_profile=request.style_profile,
                previous_chapters=request.previous_chapters,
                temperature=temp,
                preserve_ending=request.preserve_ending,
                request_id=f"{request.request_id or str(uuid.uuid4())}_v{i+1}"
            )
            
            # 生成
            result = self.generate_continuation(version_request)
            results.append(result)
            
            if self._logger:
                self._logger.info(f"[ContinuationGenerator] 版本{i+1}生成完成 - 字数: {result.word_count}, 温度: {temp}")
        
        return results
    
    def stream_continuation(
        self,
        request: ContinuationRequest,
        callback: Optional[Callable[[str], None]] = None
    ) -> Generator[str, None, ContinuationResult]:
        """
        流式续写生成
        
        支持实时输出，逐步返回生成内容。
        
        Args:
            request: 续写请求参数
            callback: 实时回调函数（可选）
            
        Yields:
            str: 生成的内容片段
            
        Returns:
            ContinuationResult: 最终结果
        """
        if not self._api_client:
            raise RuntimeError("API客户端未设置")
        
        start_time = time.time()
        full_text = ""
        
        try:
            # 构建Prompt
            prompt = self._build_continuation_prompt(request)
            max_tokens = self._calculate_max_tokens(request.word_count)
            
            # 构建系统提示词
            system_prompt = self._build_system_prompt(request)
            
            # 流式调用API
            response = self._api_client.chat.completions.create(
                model=self.default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=request.temperature or self.default_temperature,
                max_tokens=max_tokens,
                stream=True,
                timeout=self._timeout
            )
            
            # 流式输出
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_text += content
                    if callback:
                        callback(content)
                    yield content
            
            # 后处理
            processed_text = self._post_process(full_text, request)
            
            # 构建结果
            generation_time = time.time() - start_time
            metadata = ContinuationMetadata(
                model_name=self.default_model,
                provider=self._get_provider_name(),
                generation_time=generation_time,
                tokens_used=self._estimate_tokens(prompt, processed_text),
                iterations=1,
                coherence_score=self._estimate_coherence(request.starting_text, processed_text),
                style_match_score=0.8,
                context_length=len(prompt),
                starting_text_length=len(request.starting_text),
                timestamp=datetime.now()
            )
            
            return ContinuationResult(
                text=processed_text,
                word_count=len(processed_text),
                metadata=metadata,
                success=True,
                error=None,
                suggestions=self._generate_suggestions(request, processed_text)
            )
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[ContinuationGenerator] 流式续写失败: {e}")
            
            return ContinuationResult(
                text=full_text,
                word_count=len(full_text),
                metadata=ContinuationMetadata(),
                success=False,
                error=str(e),
                suggestions=None
            )
    
    def regenerate(
        self,
        request: ContinuationRequest,
        variation: str = "different"
    ) -> ContinuationResult:
        """
        重新生成（不同温度/top_p等参数）
        
        Args:
            request: 续写请求参数
            variation: 变化类型
                - "different": 使用不同温度
                - "creative": 创意模式（高温度）
                - "conservative": 保守模式（低温度）
                - "focused": 聚焦模式（低top_p）
            
        Returns:
            ContinuationResult: 新的续写结果
        """
        # 根据变化类型调整参数
        if variation == "creative":
            request.temperature = 1.0
        elif variation == "conservative":
            request.temperature = 0.5
        elif variation == "different":
            # 随机调整温度（0.6-1.2之间）
            import random
            request.temperature = 0.6 + random.random() * 0.6
        elif variation == "focused":
            request.temperature = 0.7
            # focused模式可以通过top_p控制（如果API支持）
        
        return self.generate_continuation(request)
    
    def select_best_version(
        self,
        versions: List[ContinuationResult],
        request: ContinuationRequest,
        criteria: Optional[Dict[str, float]] = None
    ) -> tuple[ContinuationResult, int, Dict[str, Any]]:
        """
        选择最佳版本
        
        通过多维度评估，从多个续写版本中选择最优版本。
        
        Args:
            versions: 多个续写结果列表
            request: 原始续写请求参数
            criteria: 评分权重配置（可选），默认：
                {
                    "coherence": 0.30,      # 连贯性权重
                    "style_match": 0.25,    # 风格匹配权重
                    "word_count": 0.20,     # 字数达标权重
                    "creativity": 0.15,     # 创意性权重
                    "readability": 0.10     # 可读性权重
                }
            
        Returns:
            tuple: (最佳版本结果, 版本索引, 评分详情)
        """
        if not versions:
            raise ValueError("版本列表不能为空")
        
        # 默认评分权重
        default_criteria = {
            "coherence": 0.30,
            "style_match": 0.25,
            "word_count": 0.20,
            "creativity": 0.15,
            "readability": 0.10
        }
        criteria = criteria or default_criteria
        
        # 评估每个版本
        scores_list = []
        for i, version in enumerate(versions):
            if not version.success:
                scores_list.append({
                    "index": i,
                    "total": 0.0,
                    "coherence": 0.0,
                    "style_match": 0.0,
                    "word_count": 0.0,
                    "creativity": 0.0,
                    "readability": 0.0,
                    "skipped": True,
                    "reason": version.error or "生成失败"
                })
                continue
            
            # 1. 连贯性评分（基于metadata中的值）
            coherence = version.metadata.coherence_score if version.metadata else 0.5
            
            # 2. 风格匹配评分
            style_match = version.metadata.style_match_score if version.metadata else 0.5
            
            # 3. 字数达标评分
            target_words = request.word_count
            actual_words = version.word_count
            if actual_words >= target_words * 0.9:
                word_score = 1.0
            elif actual_words >= target_words * 0.7:
                word_score = 0.8
            elif actual_words >= target_words * 0.5:
                word_score = 0.6
            else:
                word_score = max(0.3, actual_words / target_words)
            
            # 4. 创意性评分（基于文本多样性）
            creativity = self._evaluate_creativity(version.text)
            
            # 5. 可读性评分（基于句子长度和段落结构）
            readability = self._evaluate_readability(version.text)
            
            # 计算加权总分
            total = (
                coherence * criteria["coherence"] +
                style_match * criteria["style_match"] +
                word_score * criteria["word_count"] +
                creativity * criteria["creativity"] +
                readability * criteria["readability"]
            )
            
            scores_list.append({
                "index": i,
                "total": total,
                "coherence": coherence,
                "style_match": style_match,
                "word_count": word_score,
                "creativity": creativity,
                "readability": readability,
                "skipped": False
            })
        
        # 选择最高分版本
        valid_scores = [s for s in scores_list if not s.get("skipped")]
        if not valid_scores:
            # 所有版本都失败，返回第一个
            return versions[0], 0, {"scores": scores_list, "criteria": criteria, "reason": "所有版本都失败"}
        
        best_score = max(valid_scores, key=lambda x: x["total"])
        best_index = best_score["index"]
        
        # 记录日志
        if self._logger:
            self._logger.info(
                f"[ContinuationGenerator] 选择最佳版本: 版本{best_index+1}, "
                f"总分{best_score['total']:.2f}, "
                f"连贯性{best_score['coherence']:.2f}, "
                f"风格{best_score['style_match']:.2f}"
            )
        
        return versions[best_index], best_index, {
            "scores": scores_list,
            "best_index": best_index,
            "criteria": criteria
        }
    
    def _evaluate_creativity(self, text: str) -> float:
        """
        评估文本创意性
        
        基于词汇多样性、句式变化等指标。
        
        Args:
            text: 待评估文本
            
        Returns:
            创意性评分（0-1）
        """
        if not text:
            return 0.0
        
        # 1. 词汇多样性（去重词汇占比）
        import jieba
        words = list(jieba.cut(text))
        if not words:
            return 0.0
        
        unique_words = set(words)
        diversity = len(unique_words) / len(words) if words else 0
        
        # 2. 句式变化（不同长度句子的比例）
        sentences = [s.strip() for s in text.split('。') if s.strip()]
        if len(sentences) < 2:
            sentence_variety = 0.5
        else:
            lengths = [len(s) for s in sentences]
            avg_len = sum(lengths) / len(lengths)
            variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
            sentence_variety = min(1.0, variance / 100)  # 归一化
        
        # 3. 修辞检测（比喻、排比等）
        rhetoric_patterns = ['像', '如', '仿佛', '如同', '一般', '似的']
        has_rhetoric = any(p in text for p in rhetoric_patterns)
        rhetoric_score = 0.15 if has_rhetoric else 0
        
        # 综合评分
        score = min(1.0, diversity * 0.5 + sentence_variety * 0.35 + rhetoric_score)
        return score
    
    def _evaluate_readability(self, text: str) -> float:
        """
        评估文本可读性
        
        基于段落结构、标点使用等指标。
        
        Args:
            text: 待评估文本
            
        Returns:
            可读性评分（0-1）
        """
        if not text:
            return 0.0
        
        score = 0.5  # 基础分
        
        # 1. 段落结构
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        if len(paragraphs) >= 2:
            # 有合理分段
            score += 0.15
        elif len(paragraphs) == 1:
            # 无分段
            pass
        
        # 2. 标点使用
        punctuations = ['，', '。', '！', '？', '；', '：']
        punct_count = sum(text.count(p) for p in punctuations)
        char_count = len(text)
        
        # 合理的标点密度（约每15-20个字符一个标点）
        if char_count > 0:
            punct_ratio = punct_count / char_count
            if 0.04 <= punct_ratio <= 0.08:  # 理想区间
                score += 0.2
            elif 0.02 <= punct_ratio <= 0.1:  # 可接受区间
                score += 0.1
        
        # 3. 对话标记（有对话增加可读性）
        if '"' in text or '"' in text or '「' in text:
            score += 0.1
        
        # 4. 避免过长句子
        sentences = [s.strip() for s in text.split('。') if s.strip()]
        if sentences:
            avg_sentence_len = sum(len(s) for s in sentences) / len(sentences)
            if avg_sentence_len < 50:  # 平均句长适中
                score += 0.05
        
        return min(score, 1.0)
    
    def generate_and_select(
        self,
        request: ContinuationRequest,
        num_versions: int = 3,
        criteria: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        一站式生成并选择最佳版本
        
        集成了多版本生成和最佳选择功能。
        
        Args:
            request: 续写请求参数
            num_versions: 生成版本数量（默认3个）
            criteria: 评分权重配置（可选）
            
        Returns:
            包含所有版本和最佳版本的结果字典：
            {
                "best_version": ContinuationResult,
                "best_index": int,
                "all_versions": List[ContinuationResult],
                "scores": List[Dict],
                "criteria": Dict
            }
        """
        # 生成多个版本
        versions = self.generate_multiple_versions(request, num_versions)
        
        # 选择最佳版本
        best_version, best_index, score_details = self.select_best_version(
            versions, request, criteria
        )
        
        return {
            "best_version": best_version,
            "best_index": best_index,
            "all_versions": versions,
            "scores": score_details["scores"],
            "criteria": score_details["criteria"]
        }
    
    # =========================================================================
    # Prompt构建方法
    # =========================================================================
    
    def _build_continuation_prompt(self, request: ContinuationRequest) -> str:
        """
        构建续写Prompt
        
        根据方向和上下文，构建完整的续写提示词。
        
        Args:
            request: 续写请求参数
            
        Returns:
            完整的Prompt字符串
        """
        prompt_parts = []
        
        # 1. 上下文部分
        if request.outline:
            prompt_parts.append(f"【章节大纲】\n{request.outline}\n")
        
        if request.characters:
            prompt_parts.append("【人物设定】")
            for char in request.characters:
                name = char.get('name', '未知角色')
                traits = char.get('traits', [])
                role = char.get('role', '')
                prompt_parts.append(f"- {name}（{role}）：{'、'.join(traits) if traits else '无特殊设定'}")
            prompt_parts.append("")
        
        if request.worldview:
            prompt_parts.append(f"【世界观设定】\n{request.worldview}\n")
        
        if request.style_profile:
            style = request.style_profile
            if isinstance(style, dict):
                tone = style.get('tone', '')
                pacing = style.get('pacing', '')
                if tone or pacing:
                    prompt_parts.append(f"【写作风格】基调：{tone}，节奏：{pacing}\n")
        
        if request.previous_chapters:
            prompt_parts.append("【前文参考】")
            for i, chapter in enumerate(request.previous_chapters[-3:], 1):  # 最多3章
                preview = chapter[:500] + "..." if len(chapter) > 500 else chapter
                prompt_parts.append(f"第{i}章片段：{preview}\n")
        
        # 2. 续写方向指令
        direction_instruction = self._get_direction_instruction(request.direction, request.direction_hint)
        prompt_parts.append(direction_instruction)
        
        # 3. 起始文本
        prompt_parts.append(f"【起始文本】\n{request.starting_text}\n")
        
        # 4. 续写要求
        prompt_parts.append(f"""【续写要求】
1. 从起始文本自然衔接，保持语气和风格一致
2. 目标字数：约{request.word_count}字
3. 内容要充实，避免空洞描述
4. 注意情节推进和人物刻画
5. {"保持自然结尾，无需特殊标记" if request.preserve_ending else "如有需要可添加章节结束标记"}
""")
        
        # 5. 特殊方向提示
        if request.direction == ContinuationDirection.SPECIFIC.value and request.direction_hint:
            prompt_parts.append(f"【特别提示】\n{request.direction_hint}\n")
        
        return "\n".join(prompt_parts)
    
    def _build_system_prompt(self, request: ContinuationRequest) -> str:
        """
        构建系统提示词
        
        Args:
            request: 续写请求参数
            
        Returns:
            系统提示词
        """
        return """你是一位专业的小说续写专家，擅长根据已有文本进行自然流畅的续写。

核心能力：
1. 深入理解原文风格、人物性格和情节脉络
2. 保持续写内容与原文的高度一致性
3. 善于塑造生动的人物对话和场景描写
4. 注重情节推进和情感表达

写作原则：
1. 尊重原文设定：人物性格、世界观、情节发展必须与原文保持一致
2. 自然衔接：续写开头要与起始文本完美融合，不生硬
3. 风格统一：保持与原文相同的叙事风格和语言特点
4. 内容充实：避免空洞的描述，每句话都有存在价值
5. 情节合理：续写内容要符合逻辑，不能违背前文铺垫

特别注意：
- 人物对话要符合其性格特点和说话方式
- 场景描写要服务于情节，不能喧宾夺主
- 情感表达要真挚自然，避免刻意煽情"""
    
    def _get_direction_instruction(
        self, 
        direction: str, 
        direction_hint: Optional[str]
    ) -> str:
        """
        获取续写方向指令
        
        Args:
            direction: 续写方向
            direction_hint: 方向提示
            
        Returns:
            方向指令字符串
        """
        instructions = {
            ContinuationDirection.NATURAL.value: """【续写方向】自然续写
按照情节的自然发展进行续写，不刻意导向特定结果，让故事自然流淌。""",
            
            ContinuationDirection.SPECIFIC.value: """【续写方向】特定方向
根据指定的情节走向进行续写，确保故事向目标方向发展。""",
            
            ContinuationDirection.EMOTION.value: """【续写方向】情感导向
重点刻画人物的内心世界和情感变化，通过细腻的心理描写展现人物的情感波动。""",
            
            ContinuationDirection.ACTION.value: """【续写方向】动作导向
侧重场景和动作的描写，通过动态的场面刻画推动情节发展。""",
            
            ContinuationDirection.DIALOGUE.value: """【续写方向】对话导向
以人物对话为主，通过对话推进情节、展现人物性格、揭示信息。"""
        }
        
        instruction = instructions.get(direction, instructions[ContinuationDirection.NATURAL.value])
        
        if direction == ContinuationDirection.SPECIFIC.value and direction_hint:
            instruction += f"\n指定方向：{direction_hint}"
        
        return instruction
    
    # =========================================================================
    # API调用方法
    # =========================================================================
    
    def _call_llm_api(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        """
        调用大模型API（V1.2增强版）
        
        使用concurrent.futures实现强制超时保护，
        并细化异常类型。
        
        参数:
            prompt: 提示词
            max_tokens: 最大token数
            temperature: 温度参数
            
        返回:
            生成的文本
            
        异常:
            LLMTimeoutError: 调用超时
            LLMAuthenticationError: 认证失败
            LLMConnectionError: 连接失败
            LLMRateLimitError: 速率限制
            LLMError: 其他LLM错误
        """
        if not self._api_client:
            raise LLMError("API客户端未设置，请调用set_api_client()或通过服务定位器获取")
        
        # 构建系统提示词
        system_prompt = """你是一位专业的小说续写专家，擅长根据已有文本进行自然流畅的续写。

核心能力：
1. 深入理解原文风格、人物性格和情节脉络
2. 保持续写内容与原文的高度一致性
3. 善于塑造生动的人物对话和场景描写
4. 注重情节推进和情感表达"""
        
        # 重试机制
        last_error = None
        for attempt in range(self.max_retries):
            try:
                # V1.2修复：使用concurrent.futures实现强制超时
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        self._do_api_call,
                        system_prompt,
                        prompt,
                        max_tokens,
                        temperature
                    )
                    try:
                        content = future.result(timeout=self._timeout)
                        
                        if self._logger:
                            self._logger.debug(f"[ContinuationGenerator] API调用成功，返回{len(content)}字符")
                        
                        return content
                        
                    except concurrent.futures.TimeoutError:
                        future.cancel()
                        raise LLMTimeoutError(f"LLM调用超时（{self._timeout}秒）")
                
            except LLMTimeoutError:
                # 超时错误直接抛出，不重试
                raise
                
            except LLMAuthenticationError as e:
                # 认证错误直接抛出，不重试
                raise
                
            except LLMRateLimitError as e:
                # 速率限制，等待后重试
                last_error = e
                if self._logger:
                    self._logger.warning(f"[ContinuationGenerator] 速率限制(尝试{attempt+1}/{self.max_retries})")
                
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** (attempt + 1)  # 指数退避
                    time.sleep(wait_time)
                    continue
                raise
                
            except LLMConnectionError as e:
                # 连接错误，等待后重试
                last_error = e
                if self._logger:
                    self._logger.warning(f"[ContinuationGenerator] 连接失败(尝试{attempt+1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    time.sleep(1 * (attempt + 1))
                    continue
                raise
                
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                
                # V1.2修复：根据错误信息判断异常类型
                if self._logger:
                    self._logger.warning(f"[ContinuationGenerator] API调用失败(尝试{attempt+1}/{self.max_retries}): {e}")
                
                # 认证错误
                if 'auth' in error_msg or 'key' in error_msg or 'token' in error_msg or 'unauthorized' in error_msg or '401' in error_msg:
                    raise LLMAuthenticationError(f"API认证失败，请检查API Key: {e}")
                
                # 速率限制
                if 'rate' in error_msg or 'limit' in error_msg or '429' in error_msg:
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** (attempt + 1)
                        time.sleep(wait_time)
                        continue
                    raise LLMRateLimitError(f"API速率限制: {e}")
                
                # 连接错误
                if 'connect' in error_msg or 'network' in error_msg or 'timeout' in error_msg or 'dns' in error_msg:
                    if attempt < self.max_retries - 1:
                        time.sleep(1 * (attempt + 1))
                        continue
                    raise LLMConnectionError(f"API连接失败: {e}")
                
                # 最后一次尝试失败，抛出通用错误
                if attempt == self.max_retries - 1:
                    raise LLMError(f"API调用失败({self.max_retries}次重试后): {last_error}")
                
                # 短暂等待后重试
                time.sleep(1 * (attempt + 1))
        
        raise LLMError(f"API调用失败: {last_error}")
    
    def _do_api_call(
        self,
        system_prompt: str,
        prompt: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        """
        执行实际的API调用（内部方法）
        
        参数:
            system_prompt: 系统提示词
            prompt: 用户提示词
            max_tokens: 最大token数
            temperature: 温度参数
            
        返回:
            生成的文本
        """
        response = self._api_client.chat.completions.create(
            model=self.default_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self._timeout
        )
        
        return response.choices[0].message.content
    
    # =========================================================================
    # 辅助方法
    # =========================================================================
    
    def _calculate_max_tokens(self, word_count: int) -> int:
        """
        计算max_tokens参数
        
        中文约1.5字符/token，需要预留空间
        
        参数:
            word_count: 目标字数
            
        返回:
            max_tokens值
        """
        base_tokens = int(word_count / self.TOKEN_RATIO)
        max_tokens = int(base_tokens * 1.3)  # 预留30%空间
        max_tokens = max(max_tokens, self.MIN_TOKENS)
        max_tokens = min(max_tokens, self.MAX_TOKENS_LIMIT)
        return max_tokens
    
    def _post_process(self, text: str, request: ContinuationRequest) -> str:
        """
        后处理生成的文本
        
        Args:
            text: 原始生成文本
            request: 续写请求参数
            
        Returns:
            处理后的文本
        """
        # 去除前后空白
        text = text.strip()
        
        # 字数控制（如果超过目标太多，截断）
        if len(text) > request.word_count * 1.5:
            # 找到最后一个句号位置
            last_period = text.rfind('。', 0, int(request.word_count * 1.2))
            if last_period > 0:
                text = text[:last_period + 1]
        
        return text
    
    def _estimate_tokens(self, prompt: str, generated: str) -> int:
        """
        估算token消耗
        
        Args:
            prompt: 提示词
            generated: 生成内容
            
        Returns:
            估算的token数
        """
        # 中文约1.5字符/token
        return int((len(prompt) + len(generated)) / 1.5)
    
    def _estimate_coherence(self, starting_text: str, continuation: str) -> float:
        """
        估算连贯性评分
        
        Args:
            starting_text: 起始文本
            continuation: 续写内容
            
        Returns:
            连贯性评分（0-1）
        """
        # 简单实现：基于长度比例和连接词检测
        if not continuation:
            return 0.0
        
        # 检查是否有连接词
        connectors = ['于是', '然后', '接着', '随后', '可是', '但是', '然而', '因此']
        has_connector = any(c in continuation[:50] for c in connectors)
        
        # 基础分
        base_score = 0.7
        
        # 有连接词加分
        if has_connector:
            base_score += 0.1
        
        # 长度合理加分
        if len(continuation) > 100:
            base_score += 0.1
        
        return min(base_score, 1.0)
    
    def _get_provider_name(self) -> str:
        """获取模型提供商名称"""
        model = self.default_model.lower()
        if 'deepseek' in model:
            return 'deepseek'
        elif 'gpt' in model or 'openai' in model:
            return 'openai'
        elif 'claude' in model:
            return 'anthropic'
        else:
            return 'unknown'
    
    def _generate_suggestions(
        self, 
        request: ContinuationRequest, 
        generated: str
    ) -> List[str]:
        """
        生成后续建议
        
        Args:
            request: 续写请求参数
            generated: 生成的续写内容
            
        Returns:
            建议列表
        """
        suggestions = []
        
        # 基于上下文完整度的建议
        if not request.outline:
            suggestions.append("建议提供章节大纲以获得更好的情节连贯性")
        
        if not request.characters:
            suggestions.append("建议提供人物设定以保持角色一致性")
        
        if not request.style_profile:
            suggestions.append("建议提供风格档案以匹配写作风格")
        
        # 基于生成内容的建议
        if len(generated) < request.word_count * 0.8:
            suggestions.append("生成内容较短，可以增加更多细节描写")
        
        return suggestions[:3]  # 最多3条建议
    
    def _record_generation(
        self,
        request: ContinuationRequest,
        result: str,
        metadata: ContinuationMetadata
    ):
        """
        记录生成历史（用于调试）
        
        Args:
            request: 续写请求参数
            result: 生成结果
            metadata: 元数据
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "direction": request.direction,
            "word_count": len(result),
            "generation_time": metadata.generation_time,
            "model": metadata.model_name
        }
        
        self._generation_history.append(record)
        
        # 限制历史大小
        if len(self._generation_history) > self.MAX_HISTORY_SIZE:
            self._generation_history = self._generation_history[-self.HISTORY_KEEP_SIZE:]
    
    # =========================================================================
    # 实现父类方法
    # =========================================================================
    
    def shutdown(self) -> bool:
        """关闭插件，清理资源"""
        try:
            if hasattr(self, '_generation_history'):
                self._generation_history.clear()
            
            if hasattr(self, '_api_client'):
                self._api_client = None
            
            if self._logger:
                self._logger.info("[ContinuationGenerator] 插件已关闭")
            
            return True
            
        except Exception as e:
            if self._logger:
                self._logger.error(f"[ContinuationGenerator] 关闭失败: {e}")
            return False


# ============================================================================
# 模块级函数（供插件加载器使用）
# ============================================================================

def get_plugin_class():
    """获取插件类（供插件加载器调用）"""
    return ContinuationGeneratorPlugin


def register_plugin():
    """注册插件（供插件加载器调用）"""
    return ContinuationGeneratorPlugin
