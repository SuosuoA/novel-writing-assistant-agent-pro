"""
大纲解析器插件 V3.0

版本: 3.0.0
创建日期: 2026-03-23
迁移来源: V5 scripts/outline_parser_v3.py

功能:
- 使用LangChain的MarkdownHeaderTextSplitter进行智能分块
- 基于标题级别的层次化解析
- 支持LLM增强提取(Instructor + LangExtract)
- 更准确的结构识别和内容提取
- 支持复杂嵌套结构

参考文档:
- 《项目总体架构设计说明书V1.3》第四章
- 《插件接口定义V2.1》
"""

import os
import re
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, asdict, field

import sys
from pathlib import Path

# 添加项目根目录到sys.path（支持直接运行测试）
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.plugin_interface import AnalyzerPlugin, PluginMetadata, PluginType, PluginContext

# 可选依赖检测
try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False

try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from langchain.text_splitter import MarkdownHeaderTextSplitter
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

try:
    import instructor
    HAS_INSTRUCTOR = True
except ImportError:
    HAS_INSTRUCTOR = False


@dataclass
class OutlineChapter:
    """章节数据结构
    
    核心字段：
    - chapter_number: 章节序号
    - title: 章节标题
    - estimated_words: 预期字数
    - summary: 故事梗概
    - characters: 出场人物（主要人物名单）
    - supporting_characters: 配角人数
    - plot_points: 关键情节（核心内容）
    - keywords: 关键词
    """
    title: str
    level: int  # 标题级别(1-6)
    chapter_number: int  # 章节序号
    content: str
    estimated_words: int
    keywords: List[str] = field(default_factory=list)
    characters: List[str] = field(default_factory=list)  # 主要人物名单
    supporting_characters: int = 0  # 配角人数
    plot_points: List[str] = field(default_factory=list)  # 关键情节
    summary: str = ""  # 故事梗概
    key_content: str = ""  # 核心内容
    raw_metadata: Dict = field(default_factory=dict)


@dataclass
class OutlineMetadata:
    """大纲元数据"""
    title: str
    author: str
    genre: str
    target_word_count: int
    total_chapters: int
    summary: str
    created_date: str
    modified_date: str
    volume_structure: Dict = field(default_factory=dict)


class OutlineParserPlugin(AnalyzerPlugin):
    """大纲解析器插件 - V5核心模块迁移

    实现 AnalyzerPlugin 接口，提供大纲解析功能。

    分析类型:
    - outline: 完整大纲解析
    - structure: 结构提取
    - chapters: 章节提取

    支持格式:
    - txt: 纯文本
    - docx: Word文档
    - md: Markdown文档
    """

    # 类常量
    PLUGIN_ID = "outline-parser-v3"
    PLUGIN_NAME = "大纲解析器 V3"
    PLUGIN_VERSION = "3.0.0"

    def __init__(self):
        """初始化插件"""
        metadata = PluginMetadata(
            id=self.PLUGIN_ID,
            name=self.PLUGIN_NAME,
            version=self.PLUGIN_VERSION,
            description="基于LangChain和LLM的智能大纲解析",
            author="项目组",
            plugin_type=PluginType.ANALYZER,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=["outline-parser-v1", "outline-parser-v2"],
            permissions=["file.read"],
            min_platform_version="6.0.0",
            entry_class="OutlineParserPlugin",
        )
        super().__init__(metadata)
        
        # 初始化状态
        self._parser = None
        self._config = {}
        self._use_langchain = True
        self._logger = logging.getLogger(__name__)

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据（类方法）"""
        return PluginMetadata(
            id=cls.PLUGIN_ID,
            name=cls.PLUGIN_NAME,
            version=cls.PLUGIN_VERSION,
            description="基于LangChain和LLM的智能大纲解析",
            author="项目组",
            plugin_type=PluginType.ANALYZER,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=["outline-parser-v1", "outline-parser-v2"],
            permissions=["file.read"],
            min_platform_version="6.0.0",
            entry_class="OutlineParserPlugin",
        )

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件

        Args:
            context: 插件上下文

        Returns:
            是否初始化成功
        """
        if not super().initialize(context):
            return False

        # 加载默认配置
        self._config = self._load_config()
        
        # 检测可选依赖
        self._use_langchain = HAS_LANGCHAIN and self._config.get("use_langchain", True)
        
        # 初始化解析器
        self._init_parser()
        
        # 中文数字映射
        self.chinese_numbers = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
            '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
            '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20
        }
        
        # 阿拉伯数字映射
        self.arabic_numbers = {str(i): i for i in range(1, 101)}
        
        return True

    def _load_config(self) -> Dict:
        """加载配置"""
        default_config = {
            "supported_formats": [".docx", ".txt", ".md"],
            "encoding": "utf-8",
            "auto_detect_encoding": True,
            "chapter_header_patterns": [
                (r'^#{1,6}\s*第([\d一二三四五六七八九十百千]+)章[:：]\s*(.+)$', 'markdown'),
                (r'^第([\d一二三四五六七八九十百千]+)章[:：]\s*(.+)$', 'plain'),
            ],
            "section_patterns": [
                r'^#{1,6}\s+',
                r'^[\d]+\.',
                r'^[一二三四五六七八九十]、',
                r'^[-•]\s+'
            ],
            "max_file_size_mb": 10,
            "use_langchain": True,
            "langchain_headers_to_split_on": [
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
                ("####", "Header 4"),
                ("#####", "Header 5"),
                ("######", "Header 6"),
            ]
        }
        
        # 从配置管理器加载用户配置
        if self._context and self._context.config_manager:
            user_config = self._context.config_manager.get("plugins.outline_parser", {})
            default_config.update(user_config)
        
        return default_config

    def _init_parser(self):
        """初始化解析器"""
        # 设置日志
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)

    def analyze(self, content: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """分析大纲内容

        Args:
            content: 大纲文本内容或文件路径
            options: 解析选项
                - format: 输入格式 (txt/docx/md/auto)
                - file_path: 文件路径（可选，用于文件解析）
                - use_langchain: 是否使用LangChain分块

        Returns:
            解析结果字典:
                - success: bool - 是否成功
                - metadata: Dict - 大纲元数据
                - chapters: List[Dict] - 章节列表
                - total_chapters: int - 章节总数
                - total_estimated_words: int - 预估总字数
                - parsed_date: str - 解析日期
                - extraction_method: str - 解析方法
        """
        options = options or {}
        
        # 检查是否是文件路径
        file_path = options.get("file_path")
        if file_path and os.path.exists(file_path):
            return self.parse_file(file_path)
        
        # 直接解析文本内容
        return self._parse_content(content, options)

    def _parse_content(self, content: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """解析文本内容"""
        self._logger.info("开始解析大纲内容")
        
        # 提取结构
        if self._use_langchain and options.get("use_langchain", True):
            structure = self._extract_structure_langchain(content)
            extraction_method = "langchain"
        else:
            structure = self._extract_structure_traditional(content)
            extraction_method = "traditional"
        
        # 提取元数据
        metadata = self._extract_metadata(content, structure)
        
        # 提取章节
        chapters = self._extract_chapters_advanced(content, structure, metadata)
        
        # 更新元数据
        metadata.total_chapters = len(chapters)
        
        result = {
            "success": True,
            "metadata": asdict(metadata),
            "chapters": [asdict(chapter) for chapter in chapters],
            "volumes": [],  # 【修复V3.3】卷结构（初始为空，通过add_volume添加）
            "total_chapters": len(chapters),
            "total_estimated_words": sum(ch.estimated_words for ch in chapters),
            "parsed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "extraction_method": extraction_method
        }
        
        self._logger.info(f"大纲解析完成: {len(chapters)} 章，预估 {result['total_estimated_words']} 字")
        return result

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """解析大纲文件

        Args:
            file_path: 文件路径

        Returns:
            解析结果字典
        """
        self._logger.info(f"开始解析文件: {file_path}")
        
        # 验证文件
        if not self._validate_file(file_path):
            return {"success": False, "error": "文件验证失败"}
        
        # 根据文件类型选择解析方法
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == ".docx":
            content = self._parse_docx(file_path)
        elif file_ext in [".txt", ".md"]:
            content = self._parse_txt(file_path)
        else:
            return {"success": False, "error": f"不支持的文件格式: {file_ext}"}
        
        if "error" in content:
            return {"success": False, "error": content["error"]}
        
        # 解析内容
        return self._parse_content(content["text"], {"file_path": file_path})

    def _validate_file(self, file_path: str) -> bool:
        """验证文件"""
        if not os.path.exists(file_path):
            self._logger.error(f"文件不存在: {file_path}")
            return False
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
        if file_size > self._config["max_file_size_mb"]:
            self._logger.error(f"文件过大: {file_size:.2f} MB，最大 {self._config['max_file_size_mb']} MB")
            return False
        
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in self._config["supported_formats"]:
            self._logger.error(f"不支持的文件格式: {file_ext}")
            return False
        
        return True

    def _parse_txt(self, file_path: str) -> Dict[str, Any]:
        """解析TXT文件"""
        try:
            # 检测文件编码
            if self._config.get("auto_detect_encoding", True) and HAS_CHARDET:
                with open(file_path, 'rb') as f:
                    raw_data = f.read()
                    encoding = chardet.detect(raw_data)['encoding']
            else:
                encoding = self._config.get("encoding", "utf-8")
            
            # 读取文件
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    text = f.read()
            except UnicodeDecodeError:
                for enc in ['utf-8', 'gbk', 'gb2312', 'utf-16']:
                    try:
                        with open(file_path, 'r', encoding=enc) as f:
                            text = f.read()
                        encoding = enc
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    return {"error": "无法解码文件，请检查文件编码"}
            
            return {
                "text": text,
                "encoding": encoding,
                "type": "txt"
            }
            
        except Exception as e:
            self._logger.error(f"解析TXT文件失败: {e}")
            return {"error": f"解析TXT文件失败: {str(e)}"}

    def _parse_docx(self, file_path: str) -> Dict[str, Any]:
        """解析Word文档"""
        if not HAS_DOCX:
            return {"error": "未安装python-docx库，无法解析Word文档"}
        
        try:
            doc = docx.Document(file_path)
            paragraphs = []
            
            for para in doc.paragraphs:
                if para.text.strip():
                    paragraphs.append({
                        "text": para.text,
                        "style": para.style.name if para.style else "Normal"
                    })
            
            text = "\n".join([p["text"] for p in paragraphs])
            
            return {
                "text": text,
                "paragraphs": paragraphs,
                "type": "docx"
            }
            
        except Exception as e:
            self._logger.error(f"解析Word文档失败: {e}")
            return {"error": f"解析Word文档失败: {str(e)}"}

    def _extract_structure_langchain(self, content: str) -> List[Dict]:
        """使用LangChain提取结构"""
        if not HAS_LANGCHAIN:
            return self._extract_structure_traditional(content)
        
        try:
            # 使用MarkdownHeaderTextSplitter
            splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=self._config["langchain_headers_to_split_on"],
                strip_headers=False
            )
            
            # 分割文档
            docs = splitter.split_text(content)
            
            # 转换为结构化格式
            structure = []
            for doc in docs:
                structure.append({
                    "text": doc.page_content,
                    "metadata": doc.metadata
                })
            
            self._logger.info(f"LangChain分块完成: {len(docs)} 个文档块")
            return structure
            
        except Exception as e:
            self._logger.warning(f"LangChain分块失败: {e}，使用传统方法")
            return self._extract_structure_traditional(content)

    def _extract_structure_traditional(self, content: str) -> List[Dict]:
        """传统方法提取结构"""
        structure = []
        lines = content.split('\n')
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # 检测标题
            match = re.match(r'^(#{1,6})\s+(.+)$', line_stripped)
            if match:
                level = len(match.group(1))
                title = match.group(2)
                structure.append({
                    "text": title,
                    "level": level,
                    "type": "heading"
                })
        
        return structure

    def _extract_metadata(self, content: str, structure: List[Dict]) -> OutlineMetadata:
        """提取元数据"""
        # 尝试从文本中提取信息
        title = "未命名大纲"
        author = "未知作者"
        genre = "未知类型"
        target_word_count = 50000
        summary = ""
        
        # 提取标题
        lines = content.split('\n')
        for line in lines:
            line_stripped = line.strip()
            if line_stripped and len(line_stripped) < 100:
                if not line_stripped.startswith('#'):
                    title = line_stripped
                    break
                if '《' in line_stripped and '》' in line_stripped:
                    title = line_stripped
                    break
        
        # 提取作者
        author_match = re.search(r'作者[:：]\s*(.+)', content)
        if author_match:
            author = author_match.group(1).strip()
        
        # 提取类型
        genre_match = re.search(r'类型[:：]\s*(.+)', content)
        if genre_match:
            genre = genre_match.group(1).strip()
        
        # 提取目标字数
        word_count_match = re.search(r'目标字数[:：]\s*([\d,]+)', content)
        if word_count_match:
            try:
                target_word_count = int(word_count_match.group(1).replace(',', ''))
            except ValueError:
                pass
        
        # 提取简介
        intro_match = re.search(r'简介[:：]\s*(.+?)(?=\n\n|\n#{1,3}|\Z)', content, re.DOTALL)
        if intro_match:
            summary = intro_match.group(1).strip()
        
        return OutlineMetadata(
            title=title,
            author=author,
            genre=genre,
            target_word_count=target_word_count,
            total_chapters=0,
            summary=summary,
            created_date=datetime.now().strftime("%Y-%m-%d"),
            modified_date=datetime.now().strftime("%Y-%m-%d")
        )

    def _extract_chapters_advanced(self, content: str, structure: List[Dict],
                                   metadata: OutlineMetadata) -> List[OutlineChapter]:
        """高级章节提取"""
        chapters = []
        
        # 识别所有章节标题
        chapter_headers = self._find_all_chapter_headers(content)
        
        self._logger.info(f"识别到 {len(chapter_headers)} 个章节标题")
        
        # 根据章节标题分割内容
        for idx, header in enumerate(chapter_headers):
            start_pos = header['position']
            end_pos = chapter_headers[idx + 1]['position'] if idx + 1 < len(chapter_headers) else len(content)
            
            chapter_content = content[start_pos:end_pos]
            
            chapter = self._create_chapter_v3(
                header['title'],
                header['level'],
                idx + 1,
                chapter_content,
                metadata
            )
            
            chapters.append(chapter)
        
        # 如果没有识别到章节,尝试备用方法
        if not chapters:
            self._logger.warning("未识别到章节标题")
        
        return chapters

    def _find_all_chapter_headers(self, text: str) -> List[Dict]:
        """查找所有章节标题"""
        headers = []
        lines = text.split('\n')
        
        # 获取章节标题匹配模式（使用默认值或配置值）
        chapter_patterns = self._config.get("chapter_header_patterns", [
            (r'^#{1,6}\s*第([\d一二三四五六七八九十百千]+)章[:：]\s*(.+)$', 'markdown'),
            (r'^第([\d一二三四五六七八九十百千]+)章[:：]\s*(.+)$', 'plain'),
        ])
        
        for line_num, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            for pattern, pattern_type in chapter_patterns:
                match = re.match(pattern, line_stripped, re.UNICODE)
                if match:
                    chapter_number_str = match.group(1)
                    # 提取纯标题（不包含章节前缀）
                    chapter_title = match.group(2).strip() if len(match.groups()) > 1 else ""
                    
                    chapter_number = self._parse_chapter_number(chapter_number_str)
                    level = self._determine_heading_level(line_stripped)
                    
                    position = sum(len(l) + 1 for l in lines[:line_num])
                    
                    headers.append({
                        'title': chapter_title,  # 使用纯标题，不包含章节前缀
                        'full_title': line_stripped,  # 保留完整标题供参考
                        'chapter_number': chapter_number,
                        'level': level,
                        'pattern_type': pattern_type,
                        'position': position
                    })
                    
                    break
        
        return headers

    def _parse_chapter_number(self, number_str: str) -> int:
        """解析章节号"""
        if number_str in self.arabic_numbers:
            return self.arabic_numbers[number_str]
        
        if number_str in self.chinese_numbers:
            return self.chinese_numbers[number_str]
        
        try:
            return int(number_str)
        except ValueError:
            numbers = re.findall(r'\d+', number_str)
            if numbers:
                return int(numbers[0])
        
        return 0

    def _determine_heading_level(self, text: str) -> int:
        """确定标题级别"""
        match = re.match(r'^(#+)\s+', text)
        if match:
            return len(match.group(1))
        return 1

    def _create_chapter_v3(self, title: str, level: int, chapter_number: int,
                          content: str, metadata: OutlineMetadata) -> OutlineChapter:
        """创建章节对象 V3"""
        clean_title = title.strip()
        clean_title = re.sub(r'^[#\s]*', '', clean_title)
        
        chapter_metadata = self._extract_chapter_metadata(content)
        
        estimated_words = chapter_metadata.get('estimated_words', 0)
        if estimated_words == 0:
            estimated_words = self._calculate_estimated_words_v3(content, chapter_number, metadata)
        
        characters = self._extract_characters_v3(content)
        plot_points = self._extract_plot_points_v3(content)
        summary = chapter_metadata.get('summary', '')
        key_content = chapter_metadata.get('key_content', '')
        keywords = self._extract_keywords_v3(content)
        
        # 计算配角人数（出场人物中排除主要人物）
        supporting_count = max(0, len(characters) - 1)  # 假设第一个是主角
        
        return OutlineChapter(
            title=clean_title,
            level=level,
            chapter_number=chapter_number,
            content=content,
            estimated_words=estimated_words,
            keywords=keywords,
            characters=characters,
            supporting_characters=supporting_count,
            plot_points=plot_points,
            summary=summary,
            key_content=key_content,
            raw_metadata=chapter_metadata
        )

    def _extract_chapter_metadata(self, content: str) -> Dict:
        """提取章节元数据
        
        提取字段：
        - estimated_words: 预计字数
        - summary: 章节梗概/故事概要
        - main_characters: 主要人物（区分主配）
        - supporting_characters: 配角人数
        - key_content: 关键内容/核心情节
        """
        metadata = {}
        lines = content.split('\n')
        
        # 状态标记
        in_section = None  # 当前所在段落
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # 1. 提取预计字数
            if '预计字数' in line_stripped or '**预计字数**' in line_stripped:
                match = re.search(r'[:：]\s*(\d+)\s*字', line_stripped)
                if match:
                    metadata['estimated_words'] = int(match.group(1))
                continue
            
            # 2. 提取章节梗概（多种格式）
            if '**章节梗概**' in line_stripped or '**故事梗概**' in line_stripped or '**梗概**' in line_stripped:
                in_section = 'summary'
                # 检查是否同行有内容
                if '：' in line_stripped or ':' in line_stripped:
                    after_colon = re.split(r'[:：]', line_stripped, 1)
                    if len(after_colon) > 1 and after_colon[1].strip():
                        metadata['summary'] = after_colon[1].strip()
                        in_section = None
                continue
            
            # 3. 提取关键内容/核心情节
            if '**关键内容**' in line_stripped or '**核心情节**' in line_stripped or '**主要内容**' in line_stripped:
                in_section = 'key_content'
                # 检查是否同行有内容
                if '：' in line_stripped or ':' in line_stripped:
                    after_colon = re.split(r'[:：]', line_stripped, 1)
                    if len(after_colon) > 1 and after_colon[1].strip():
                        metadata['key_content'] = after_colon[1].strip()
                        in_section = None
                continue
            
            # 4. 检测人物标记 - 从同行提取
            if '**登场人物**' in line_stripped or '**出场人物**' in line_stripped:
                if '：' in line_stripped or ':' in line_stripped:
                    after_colon = re.split(r'[:：]', line_stripped, 1)
                    if len(after_colon) > 1 and after_colon[1].strip():
                        char_text = after_colon[1].strip()
                        # 简单计数，实际人物提取在 _extract_characters_v3 中
                        char_list = re.split(r'[、，,和\s]+', char_text)
                        valid_chars = [c.strip() for c in char_list if 2 <= len(c.strip()) <= 4]
                        metadata['character_preview'] = '、'.join(valid_chars[:5])
                continue
            
            # 5. 检查是否进入其他标记段落（终止当前段落）
            if line_stripped.startswith('**') and line_stripped.endswith('**'):
                if in_section and in_section in ['summary', 'key_content']:
                    in_section = None
                continue
            
            # 6. 收集段落内容
            if in_section == 'summary' and not line_stripped.startswith('-'):
                # 梗概通常是多行文本
                if 'summary' not in metadata:
                    metadata['summary'] = line_stripped
                else:
                    metadata['summary'] += ' ' + line_stripped
                continue
            
            if in_section == 'key_content':
                # 关键内容通常是列表项或文本
                if line_stripped.startswith('-') or line_stripped.startswith('*'):
                    clean_point = re.sub(r'^[-*]\s*', '', line_stripped).strip()
                    if 'key_content' not in metadata:
                        metadata['key_content'] = clean_point
                    else:
                        metadata['key_content'] += '；' + clean_point
                elif not line_stripped.startswith('**'):
                    # 也支持纯文本形式
                    if 'key_content' not in metadata:
                        metadata['key_content'] = line_stripped
                    else:
                        metadata['key_content'] += ' ' + line_stripped
                continue
        
        # 7. 清理摘要文本
        if 'summary' in metadata:
            metadata['summary'] = metadata['summary'].strip()
            if len(metadata['summary']) > 500:
                metadata['summary'] = metadata['summary'][:500] + '...'
        
        return metadata

    def _extract_characters_v3(self, content: str) -> List[str]:
        """提取人物 V3"""
        characters = []
        lines = content.split('\n')
        
        in_character_section = False
        for line in lines:
            line_stripped = line.strip()
            
            # 检测人物段落开始
            if '**登场人物**' in line_stripped or '**出场人物**' in line_stripped:
                in_character_section = True
                # 检查是否同行有内容（如 "**登场人物**：林风、李雪"）
                if '：' in line_stripped or ':' in line_stripped:
                    after_colon = re.split(r'[:：]', line_stripped, 1)
                    if len(after_colon) > 1 and after_colon[1].strip():
                        # 提取同行的人物
                        char_text = after_colon[1].strip()
                        char_list = re.split(r'[、，,和\s]+', char_text)
                        for char in char_list:
                            char_clean = char.strip()
                            if char_clean and 2 <= len(char_clean) <= 4:
                                if char_clean not in ['电话', '手机', '消息', '通知', '声音', '主要', '配角']:
                                    if char_clean not in characters:
                                        characters.append(char_clean)
                continue
            
            # 检测人物段落结束（遇到其他**标记）
            elif in_character_section and line_stripped.startswith('**'):
                if not any(keyword in line_stripped for keyword in 
                          ['**关键转折**', '**关键情节**', '**语言风格**', '**关键词**']):
                    break
            
            # 提取人物列表（下一行内容）
            elif in_character_section and line_stripped:
                # 去除项目符号
                clean_line = re.sub(r'^[-*]\s*', '', line_stripped)
                clean_line = re.sub(r'^[**]*\w+[**]*[:：]\s*', '', clean_line)
                
                if clean_line and '等' not in clean_line:
                    # 按分隔符分割人物
                    char_list = re.split(r'[、，,和\s]+', clean_line)
                    for char in char_list:
                        char_clean = char.strip()
                        if char_clean and 2 <= len(char_clean) <= 4:
                            if char_clean not in ['电话', '手机', '消息', '通知', '声音', '主要', '配角']:
                                if char_clean not in characters:
                                    characters.append(char_clean)
        
        return characters[:10]

    def _extract_plot_points_v3(self, content: str) -> List[str]:
        """提取情节点 V3"""
        plot_points = []
        lines = content.split('\n')
        
        in_plot_section = False
        for line in lines:
            line_stripped = line.strip()
            
            if '**关键情节**' in line_stripped:
                in_plot_section = True
                continue
            
            elif in_plot_section and line_stripped.startswith('**'):
                if not any(keyword in line_stripped for keyword in 
                          ['**登场人物**', '**出场人物**', '**关键词**']):
                    break
            
            elif in_plot_section and line_stripped.startswith('-'):
                clean_point = re.sub(r'^[-*]\s*', '', line_stripped).strip()
                if clean_point and len(clean_point) > 5:
                    plot_points.append(clean_point)
        
        return plot_points[:10]

    def _extract_keywords_v3(self, content: str) -> List[str]:
        """提取关键词 V3"""
        keywords = []
        lines = content.split('\n')
        
        in_keyword_section = False
        for line in lines:
            line_stripped = line.strip()
            
            if '**关键词**' in line_stripped:
                in_keyword_section = True
                continue
            
            elif in_keyword_section and line_stripped.startswith('**'):
                if not any(keyword in line_stripped for keyword in 
                          ['**登场人物**', '**出场人物**', '**关键情节**']):
                    break
            
            elif in_keyword_section and line_stripped:
                clean_line = re.sub(r'^[-*]\s*', '', line_stripped).strip()
                
                if clean_line and len(clean_line) >= 2:
                    keywords.append(clean_line)
        
        # 如果没有从关键词部分提取到,使用jieba
        if not keywords:
            try:
                import jieba.analyse
                keywords = jieba.analyse.extract_tags(content, topK=5)
            except:
                from collections import Counter
                words = re.findall(r'[\u4e00-\u9fff]{2,}', content)
                word_counts = Counter(words)
                keywords = [word for word, _ in word_counts.most_common(5)]
        
        return keywords[:5]

    def _calculate_estimated_words_v3(self, content: str, chapter_number: int,
                                     metadata: OutlineMetadata) -> int:
        """计算预估字数 V3"""
        estimated = self._extract_estimated_words_from_content(content)
        if estimated > 0:
            return estimated
        
        if metadata.target_word_count > 0:
            total_estimated = 100
            base_words = metadata.target_word_count // total_estimated
            
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
            english_chars = len(re.findall(r'[a-zA-Z]', content))
            content_length = chinese_chars + (english_chars // 5)
            
            avg_length = 500
            if content_length > 0:
                ratio = min(max(content_length / avg_length, 0.8), 1.2)
                estimated = int(base_words * ratio)
            else:
                estimated = base_words
            
            return max(1000, estimated)
        
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
        return max(100, chinese_chars)

    def _extract_estimated_words_from_content(self, content: str) -> int:
        """从内容中提取预计字数"""
        lines = content.split('\n')
        for line in lines:
            line_stripped = line.strip()
            if '**预计字数**' in line_stripped or '预计字数' in line_stripped:
                match = re.search(r'[:：]\s*(\d+)\s*字', line_stripped)
                if match:
                    return int(match.group(1))
        return 0

    def create_outline(self, name: str, novel_type: str, target_words: int, 
                       description: str) -> Dict[str, Any]:
        """创建新大纲（适配UI新建大纲功能）
        
        Args:
            name: 大纲名称
            novel_type: 小说类型（玄幻/都市/科幻/历史/奇幻等）
            target_words: 目标字数
            description: 简介
            
        Returns:
            创建结果字典，包含success、outline_id、outline_data等
        """
        try:
            # 生成大纲ID
            outline_id = f"outline_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # 创建基础大纲结构
            outline_data = {
                "id": outline_id,
                "name": name,
                "novel_type": novel_type,
                "target_words": target_words,
                "description": description,
                "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "modified_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "volumes": [],  # 卷结构
                "chapters": [],  # 章节列表
                "status": "draft",
                "progress": 0.0,
                "total_words": 0
            }
            
            # 根据类型生成建议的卷结构
            suggested_volumes = self._suggest_volumes(novel_type, target_words)
            outline_data["suggested_volumes"] = suggested_volumes
            
            self._logger.info(f"创建大纲成功: {name} ({novel_type}, {target_words}字)")
            
            return {
                "success": True,
                "outline_id": outline_id,
                "outline_data": outline_data,
                "message": f"大纲 '{name}' 创建成功"
            }
            
        except Exception as e:
            self._logger.error(f"创建大纲失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _suggest_volumes(self, novel_type: str, target_words: int) -> List[Dict]:
        """根据类型和字数建议卷结构"""
        # 简化的卷结构建议
        volume_count = max(1, target_words // 200000)  # 每20万字一卷
        volumes = []
        
        for i in range(volume_count):
            volumes.append({
                "volume_number": i + 1,
                "volume_name": f"第{i + 1}卷",
                "suggested_words": target_words // volume_count,
                "suggested_chapters": 20
            })
        
        return volumes
    
    def get_outline_template(self, novel_type: str) -> Dict[str, Any]:
        """获取大纲模板（适配UI模板选择功能）
        
        Args:
            novel_type: 小说类型
            
        Returns:
            大纲模板字典
        """
        templates = {
            "玄幻": {
                "structure": ["开篇", "修炼", "历练", "突破", "高潮", "结局"],
                "key_elements": ["主角", "修炼体系", "世界观", "势力分布", "重要物品"],
                "default_chapters": 100
            },
            "都市": {
                "structure": ["开篇", "发展", "冲突", "高潮", "结局"],
                "key_elements": ["主角", "职业设定", "情感线", "冲突事件"],
                "default_chapters": 50
            },
            "科幻": {
                "structure": ["背景铺垫", "冲突展开", "探索发现", "危机爆发", "最终决战"],
                "key_elements": ["主角", "科技设定", "世界观", "外星文明/危机"],
                "default_chapters": 80
            },
            "历史": {
                "structure": ["穿越/开局", "立足", "发展", "争霸", "结局"],
                "key_elements": ["主角", "历史背景", "重要人物", "战略布局"],
                "default_chapters": 60
            },
            "奇幻": {
                "structure": ["开篇", "冒险", "成长", "试炼", "终局"],
                "key_elements": ["主角", "魔法体系", "种族设定", "任务系统"],
                "default_chapters": 70
            }
        }
        
        return templates.get(novel_type, templates["玄幻"])

    def get_supported_formats(self) -> List[str]:
        """获取支持的输入格式"""
        return ["txt", "docx", "md", "json"]

    def get_analysis_types(self) -> List[str]:
        """获取支持的分析类型"""
        return ["outline", "structure", "chapters"]

    # ========================================================================
    # 章节管理操作（增删改）
    # ========================================================================
    
    def add_volume(self, outline_data: Dict, volume_name: str, 
                   volume_description: str = "",
                   selected_chapters: Optional[List[int]] = None) -> Dict[str, Any]:
        """添加卷
        
        Args:
            outline_data: 现有大纲数据
            volume_name: 卷名称
            volume_description: 卷描述
            selected_chapters: 选中的章节索引列表（可选）
            
        Returns:
            更新后的大纲数据
        """
        try:
            volumes = outline_data.get('volumes', [])
            chapters = outline_data.get('chapters', [])
            
            # 计算卷号
            volume_number = len(volumes) + 1
            
            # 确定卷包含的章节
            volume_chapters = []
            if selected_chapters:
                # 使用选中的章节索引
                for idx in selected_chapters:
                    if 0 <= idx < len(chapters):
                        volume_chapters.append(idx)
            
            # 创建新卷
            new_volume = {
                "volume_number": volume_number,
                "volume_name": volume_name or f"第{volume_number}卷",
                "description": volume_description,
                "chapters": volume_chapters,  # 存储章节索引列表
                "chapter_count": len(volume_chapters),
                "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            volumes.append(new_volume)
            outline_data['volumes'] = volumes
            outline_data['modified_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            self._logger.info(f"添加卷成功: {volume_name}（包含{len(volume_chapters)}章）")
            
            return {
                "success": True,
                "outline_data": outline_data,
                "volume": new_volume,
                "message": f"卷 '{volume_name}' 添加成功"
            }
            
        except Exception as e:
            self._logger.error(f"添加卷失败: {e}")
            return {"success": False, "error": str(e)}
    
    def delete_volume(self, outline_data: Dict, volume_index: int, 
                      keep_chapters: bool = True) -> Dict[str, Any]:
        """删除卷
        
        Args:
            outline_data: 现有大纲数据
            volume_index: 卷索引（0开始）
            keep_chapters: 是否保留章节（True则章节变为未分类）
            
        Returns:
            更新后的大纲数据
        """
        try:
            volumes = outline_data.get('volumes', [])
            
            if volume_index < 0 or volume_index >= len(volumes):
                return {"success": False, "error": f"无效的卷索引: {volume_index}"}
            
            # 获取被删除的卷信息
            deleted_volume = volumes.pop(volume_index)
            deleted_name = deleted_volume.get('volume_name', f'第{volume_index+1}卷')
            
            # 重新编号剩余卷
            for i, vol in enumerate(volumes):
                vol['volume_number'] = i + 1
            
            outline_data['volumes'] = volumes
            outline_data['modified_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            self._logger.info(f"删除卷成功: {deleted_name}")
            
            return {
                "success": True,
                "outline_data": outline_data,
                "deleted_volume": deleted_volume,
                "message": f"卷 '{deleted_name}' 删除成功"
            }
            
        except Exception as e:
            self._logger.error(f"删除卷失败: {e}")
            return {"success": False, "error": str(e)}
    
    def move_chapter_to_volume(self, outline_data: Dict, chapter_index: int,
                               volume_index: int) -> Dict[str, Any]:
        """将章节移入卷
        
        Args:
            outline_data: 现有大纲数据
            chapter_index: 章节索引（0开始）
            volume_index: 目标卷索引（0开始，-1表示移出所有卷）
            
        Returns:
            更新后的大纲数据
        """
        try:
            chapters = outline_data.get('chapters', [])
            volumes = outline_data.get('volumes', [])
            
            if chapter_index < 0 or chapter_index >= len(chapters):
                return {"success": False, "error": f"无效的章节索引: {chapter_index}"}
            
            chapter_title = chapters[chapter_index].get('title', f'第{chapter_index+1}章')
            
            # 先从所有卷中移除该章节
            for vol in volumes:
                vol_chapters = vol.get('chapters', [])
                if chapter_index in vol_chapters:
                    vol_chapters.remove(chapter_index)
                    vol['chapter_count'] = len(vol_chapters)
            
            # 如果目标卷有效（>=0），添加到目标卷
            if volume_index >= 0 and volume_index < len(volumes):
                target_vol = volumes[volume_index]
                vol_chapters = target_vol.get('chapters', [])
                if chapter_index not in vol_chapters:
                    vol_chapters.append(chapter_index)
                    # 保持有序
                    target_vol['chapters'] = sorted(vol_chapters)
                    target_vol['chapter_count'] = len(vol_chapters)
                    vol_name = target_vol.get('volume_name', f'第{volume_index+1}卷')
                    message = f"章节 '{chapter_title}' 已移入卷 '{vol_name}'"
                else:
                    message = f"章节 '{chapter_title}' 已在目标卷中"
            else:
                message = f"章节 '{chapter_title}' 已移出所有卷"
            
            outline_data['volumes'] = volumes
            outline_data['modified_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            self._logger.info(message)
            
            return {
                "success": True,
                "outline_data": outline_data,
                "message": message
            }
            
        except Exception as e:
            self._logger.error(f"移动章节失败: {e}")
            return {"success": False, "error": str(e)}
    
    def update_volume(self, outline_data: Dict, volume_index: int,
                      volume_data: Dict) -> Dict[str, Any]:
        """编辑卷信息
        
        Args:
            outline_data: 现有大纲数据
            volume_index: 卷索引（0开始）
            volume_data: 更新的卷数据（volume_name, description等）
            
        Returns:
            更新后的大纲数据
        """
        try:
            volumes = outline_data.get('volumes', [])
            
            if volume_index < 0 or volume_index >= len(volumes):
                return {"success": False, "error": f"无效的卷索引: {volume_index}"}
            
            volume = volumes[volume_index]
            old_name = volume.get('volume_name', f'第{volume_index+1}卷')
            
            # 更新卷信息
            if 'volume_name' in volume_data:
                volume['volume_name'] = volume_data['volume_name']
            if 'description' in volume_data:
                volume['description'] = volume_data['description']
            
            outline_data['volumes'] = volumes
            outline_data['modified_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            new_name = volume.get('volume_name', old_name)
            self._logger.info(f"编辑卷成功: {old_name} -> {new_name}")
            
            return {
                "success": True,
                "outline_data": outline_data,
                "volume": volume,
                "message": f"卷 '{new_name}' 更新成功"
            }
            
        except Exception as e:
            self._logger.error(f"编辑卷失败: {e}")
            return {"success": False, "error": str(e)}
    
    def add_chapter(self, outline_data: Dict, chapter_data: Dict,
                    volume_index: Optional[int] = None,
                    after_chapter: Optional[int] = None) -> Dict[str, Any]:
        """添加章节
        
        Args:
            outline_data: 现有大纲数据
            chapter_data: 章节数据（包含title, summary, characters, estimated_words等）
            volume_index: 卷索引（可选，None表示添加到最后）
            after_chapter: 在某章节后插入（可选，None表示添加到末尾）
            
        Returns:
            更新后的大纲数据
        """
        try:
            chapters = outline_data.get('chapters', [])
            
            # 创建新章节
            new_chapter = {
                "title": chapter_data.get('title', '未命名章节'),
                "level": chapter_data.get('level', 3),
                "chapter_number": len(chapters) + 1,
                "content": chapter_data.get('content', ''),
                "estimated_words": chapter_data.get('estimated_words', 2000),
                "keywords": chapter_data.get('keywords', []),
                "characters": chapter_data.get('characters', []),
                "supporting_characters": chapter_data.get('supporting_characters', 0),
                "plot_points": chapter_data.get('plot_points', []),
                "summary": chapter_data.get('summary', ''),
                "key_content": chapter_data.get('key_content', ''),
                "raw_metadata": {}
            }
            
            # 确定插入位置
            if after_chapter is not None and 0 <= after_chapter < len(chapters):
                chapters.insert(after_chapter + 1, new_chapter)
            else:
                chapters.append(new_chapter)
            
            # 重新编号所有章节
            for i, chapter in enumerate(chapters):
                chapter['chapter_number'] = i + 1
            
            outline_data['chapters'] = chapters
            outline_data['total_chapters'] = len(chapters)
            outline_data['modified_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            self._logger.info(f"添加章节成功: {new_chapter['title']}")
            
            return {
                "success": True,
                "outline_data": outline_data,
                "chapter": new_chapter,
                "chapter_index": len(chapters) - 1,
                "message": f"章节 '{new_chapter['title']}' 添加成功"
            }
            
        except Exception as e:
            self._logger.error(f"添加章节失败: {e}")
            return {"success": False, "error": str(e)}
    
    def update_chapter(self, outline_data: Dict, chapter_index: int,
                       chapter_data: Dict) -> Dict[str, Any]:
        """编辑章节
        
        Args:
            outline_data: 现有大纲数据
            chapter_index: 章节索引（0开始）
            chapter_data: 更新的章节数据
            
        Returns:
            更新后的大纲数据
        """
        try:
            chapters = outline_data.get('chapters', [])
            
            if chapter_index < 0 or chapter_index >= len(chapters):
                return {"success": False, "error": f"无效的章节索引: {chapter_index}"}
            
            # 更新章节（保留未提供的字段）
            chapter = chapters[chapter_index]
            for key, value in chapter_data.items():
                if value is not None:
                    chapter[key] = value
            
            outline_data['chapters'] = chapters
            outline_data['modified_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            self._logger.info(f"编辑章节成功: 第{chapter_index + 1}章")
            
            return {
                "success": True,
                "outline_data": outline_data,
                "chapter": chapter,
                "message": f"章节 '{chapter.get('title', '')}' 更新成功"
            }
            
        except Exception as e:
            self._logger.error(f"编辑章节失败: {e}")
            return {"success": False, "error": str(e)}
    
    def delete_chapter(self, outline_data: Dict, chapter_index: int) -> Dict[str, Any]:
        """删除章节
        
        Args:
            outline_data: 现有大纲数据
            chapter_index: 章节索引（0开始）
            
        Returns:
            更新后的大纲数据
        """
        try:
            chapters = outline_data.get('chapters', [])
            
            if chapter_index < 0 or chapter_index >= len(chapters):
                return {"success": False, "error": f"无效的章节索引: {chapter_index}"}
            
            # 删除章节
            deleted_chapter = chapters.pop(chapter_index)
            
            # 重新编号所有章节
            for i, chapter in enumerate(chapters):
                chapter['chapter_number'] = i + 1
            
            outline_data['chapters'] = chapters
            outline_data['total_chapters'] = len(chapters)
            outline_data['modified_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            self._logger.info(f"删除章节成功: {deleted_chapter.get('title', '')}")
            
            return {
                "success": True,
                "outline_data": outline_data,
                "deleted_chapter": deleted_chapter,
                "message": f"章节 '{deleted_chapter.get('title', '')}' 删除成功"
            }
            
        except Exception as e:
            self._logger.error(f"删除章节失败: {e}")
            return {"success": False, "error": str(e)}
    
    def reorder_chapters(self, outline_data: Dict, from_index: int, to_index: int) -> Dict[str, Any]:
        """重新排序章节（拖拽排序）
        
        【架构修复V3.3】业务逻辑在插件层实现，GUI只负责事件处理
        
        Args:
            outline_data: 现有大纲数据
            from_index: 源章节索引（0开始）
            to_index: 目标章节索引（0开始）
            
        Returns:
            更新后的大纲数据
        """
        try:
            chapters = outline_data.get('chapters', [])
            volumes = outline_data.get('volumes', [])
            
            if from_index < 0 or from_index >= len(chapters):
                return {"success": False, "error": f"无效的源章节索引: {from_index}"}
            
            if to_index < 0 or to_index >= len(chapters):
                return {"success": False, "error": f"无效的目标章节索引: {to_index}"}
            
            if from_index == to_index:
                return {"success": True, "outline_data": outline_data, "message": "位置未变化"}
            
            # 移动章节
            chapter = chapters.pop(from_index)
            chapters.insert(to_index, chapter)
            
            # 重新编号所有章节
            for i, ch in enumerate(chapters):
                ch['chapter_number'] = i + 1
            
            outline_data['chapters'] = chapters
            outline_data['modified_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 更新卷数据中的章节索引
            if volumes:
                for vol in volumes:
                    vol_chapters = vol.get('chapters', [])
                    # 更新章节索引映射
                    new_vol_chapters = []
                    for old_idx in vol_chapters:
                        if old_idx == from_index:
                            new_vol_chapters.append(to_index)
                        elif from_index < to_index:
                            # 向后移动：from_index和to_index之间的章节索引减1
                            if from_index < old_idx <= to_index:
                                new_vol_chapters.append(old_idx - 1)
                            else:
                                new_vol_chapters.append(old_idx)
                        else:
                            # 向前移动：to_index和from_index之间的章节索引加1
                            if to_index <= old_idx < from_index:
                                new_vol_chapters.append(old_idx + 1)
                            else:
                                new_vol_chapters.append(old_idx)
                    vol['chapters'] = sorted(new_vol_chapters)
            
            self._logger.info(f"章节排序成功: {from_index} -> {to_index}")
            
            return {
                "success": True,
                "outline_data": outline_data,
                "message": f"章节移动成功: 位置{from_index + 1} -> {to_index + 1}"
            }
            
        except Exception as e:
            self._logger.error(f"章节排序失败: {e}")
            return {"success": False, "error": str(e)}
    
    def shutdown(self) -> bool:
        """优雅关闭插件
        
        清理资源：
        1. 清理解析器配置
        2. 调用父类shutdown
        """
        try:
            # 清理配置
            if hasattr(self, '_config'):
                self._config.clear()
            
            # 清理解析器引用
            self._parser = None
            
            self._logger.info(f"[{self.PLUGIN_ID}] 插件已关闭")
            return super().shutdown()
            
        except Exception as e:
            self._logger.error(f"[{self.PLUGIN_ID}] 关闭失败: {e}")
            return False


# ============================================================================
# 模块级函数（供插件加载器使用）
# ============================================================================

def get_plugin_class():
    """获取插件类"""
    return OutlineParserPlugin


def register_plugin():
    """注册插件"""
    return OutlineParserPlugin


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("大纲解析器插件 V3 测试")
    print("=" * 60)
    
    # 创建插件实例
    plugin = OutlineParserPlugin()
    print(f"\n1. 插件元数据:")
    print(f"   ID: {plugin.metadata.id}")
    print(f"   名称: {plugin.metadata.name}")
    print(f"   版本: {plugin.metadata.version}")
    print(f"   类型: {plugin.metadata.plugin_type.value}")
    
    # 测试analyze方法
    print(f"\n2. 测试analyze方法:")
    
    test_outline = """
# 《测试小说》大纲

作者：测试作者
类型：玄幻
目标字数：100,000

## 第一章：开端

**预计字数**：2000字

**登场人物**：林风、李雪、王刚

**章节梗概**：主角林风在一次意外中获得了神秘力量，开始了他的修炼之路。

**关键情节**：
- 林风在山中采药时发现神秘洞穴
- 洞穴中有一本古老的书卷
- 林风开始按照书卷修炼

## 第二章：成长

**预计字数**：2500字

**登场人物**：林风、陈师傅

**章节梗概**：林风在陈师傅的指导下，修炼进步神速。
"""
    
    result = plugin.analyze(test_outline)
    
    if result.get("success"):
        print(f"   解析成功!")
        print(f"   标题: {result['metadata']['title']}")
        print(f"   作者: {result['metadata']['author']}")
        print(f"   章节数: {result['total_chapters']}")
        print(f"   预估总字数: {result['total_estimated_words']}")
        print(f"   解析方法: {result['extraction_method']}")
        
        if result['chapters']:
            print(f"\n   章节:")
            for ch in result['chapters'][:3]:
                print(f"     - {ch['title']} ({ch['estimated_words']}字)")
    else:
        print(f"   解析失败: {result.get('error')}")
    
    print(f"\n3. 支持的格式:")
    print(f"   {plugin.get_supported_formats()}")
    
    print(f"\n4. 分析类型:")
    print(f"   {plugin.get_analysis_types()}")
    
    print(f"\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
