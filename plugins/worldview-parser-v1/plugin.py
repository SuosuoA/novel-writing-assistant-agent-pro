"""
世界观解析器插件 V1.0

版本: 1.0.0
创建日期: 2026-03-23
迁移来源: V5 scripts/universal_worldview_parser.py

功能:
- 支持多种格式的世界观文件解析
- Markdown格式、括号格式、列表格式、纯文本格式
- 自动识别分类（时间线、地理位置、势力分布等）
- 属性提取和重要性标记

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
from dataclasses import dataclass, asdict, field

import sys
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.plugin_interface import AnalyzerPlugin, PluginMetadata, PluginType, PluginContext


@dataclass
class WorldviewElement:
    """世界观元素数据结构"""
    category: str
    subcategory: Optional[str]
    name: str
    description: str
    attributes: Dict[str, str] = field(default_factory=dict)
    importance: str = "中"
    source_file: str = ""


class WorldviewParserPlugin(AnalyzerPlugin):
    """世界观解析器插件 - V5核心模块迁移

    实现 AnalyzerPlugin 接口，提供世界观解析功能。

    分析类型:
    - worldview: 完整世界观解析
    - elements: 元素提取
    - categories: 分类提取

    支持格式:
    - txt: 纯文本
    - md: Markdown文档
    - json: JSON格式
    """

    PLUGIN_ID = "worldview-parser-v1"
    PLUGIN_NAME = "世界观解析器 V1"
    PLUGIN_VERSION = "1.0.0"

    def __init__(self):
        """初始化插件"""
        metadata = PluginMetadata(
            id=self.PLUGIN_ID,
            name=self.PLUGIN_NAME,
            version=self.PLUGIN_VERSION,
            description="通用世界观解析器，支持多种格式的世界观文件解析",
            author="项目组",
            plugin_type=PluginType.ANALYZER,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=[],
            permissions=["file.read"],
            min_platform_version="6.0.0",
            entry_class="WorldviewParserPlugin",
        )
        super().__init__(metadata)
        
        self._config = {}
        self._category_keywords = {}
        self._logger = logging.getLogger(__name__)

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id=cls.PLUGIN_ID,
            name=cls.PLUGIN_NAME,
            version=cls.PLUGIN_VERSION,
            description="通用世界观解析器，支持多种格式的世界观文件解析",
            author="项目组",
            plugin_type=PluginType.ANALYZER,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=[],
            permissions=["file.read"],
            min_platform_version="6.0.0",
            entry_class="WorldviewParserPlugin",
        )

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件"""
        if not super().initialize(context):
            return False

        # 加载配置
        self._config = self._load_config()
        
        # 初始化分类关键词
        self._init_category_keywords()
        
        return True

    def _load_config(self) -> Dict:
        """加载配置"""
        default_config = {
            "supported_formats": [".txt", ".md", ".json"],
            "encoding": "utf-8",
            "auto_detect_category": True,
            "default_importance": "中",
            "importance_levels": ["高", "中", "低"],
        }
        
        if self._context and self._context.config_manager:
            user_config = self._context.config_manager.get("plugins.worldview_parser", {})
            default_config.update(user_config)
        
        return default_config

    def _init_category_keywords(self):
        """初始化分类关键词"""
        self._category_keywords = {
            '时间线': ['时间', '年代', '历史', '时期', '纪元', '朝代', '时代', '年'],
            '地理位置': ['地点', '位置', '地域', '国家', '城市', '区域', '地形', '山脉', '海洋', '岛屿', '大陆'],
            '势力分布': ['势力', '势力分布', '组织', '集团', '派系', '联盟', '军队', '教派', '门派', '宗门'],
            '文化习俗': ['文化', '习俗', '传统', '礼仪', '风俗', '习惯', '节日', '信仰', '宗教'],
            '魔法体系': ['魔法', '法术', '咒语', '术式', '力量', '能力', '灵力', '气', '异能', '修仙', '功法'],
            '科技水平': ['科技', '技术', '装备', '武器', '工具', '设备', '机械', '机甲', '兵器'],
            '种族设定': ['种族', '物种', '人类', '精灵', '矮人', '兽人', '魔族', '神族'],
            '经济体系': ['货币', '经济', '贸易', '商业', '市场', '交易'],
            '政治体系': ['政治', '政府', '制度', '法律', '法规', '统治'],
            '其他': []
        }

    def analyze(self, content: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """分析世界观内容

        Args:
            content: 世界观文本内容或文件路径
            options: 解析选项
                - format: 输入格式 (txt/md/json/auto)
                - file_path: 文件路径（可选）
                - analysis_type: 分析类型 (full/elements/categories)

        Returns:
            解析结果字典:
                - success: bool - 是否成功
                - elements: List[Dict] - 世界观元素列表
                - categories: Dict[str, int] - 分类统计
                - total_elements: int - 元素总数
                - parsed_date: str - 解析日期
        """
        options = options or {}
        
        # 检查是否是文件路径
        file_path = options.get("file_path")
        if file_path and os.path.exists(file_path):
            return self._parse_file(file_path, options)
        
        # 检查content是否是文件路径
        if content and os.path.exists(content):
            return self._parse_file(content, options)
        
        # 直接解析文本内容
        return self._parse_content(content, options)

    def _parse_file(self, file_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """解析文件"""
        self._logger.info(f"开始解析文件: {file_path}")
        
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == ".json":
            return self._parse_json_file(file_path, options)
        elif file_ext in [".txt", ".md"]:
            return self._parse_text_file(file_path, options)
        else:
            return {"success": False, "error": f"不支持的文件格式: {file_ext}"}

    def _parse_text_file(self, file_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """解析文本文件"""
        try:
            encoding = self._config.get("encoding", "utf-8")
            
            # 尝试多种编码
            for enc in [encoding, 'utf-8', 'gbk', 'gb2312']:
                try:
                    with open(file_path, 'r', encoding=enc) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return {"success": False, "error": "无法解码文件"}
            
            result = self._parse_content(content, options)
            result["source_file"] = file_path
            
            # 更新元素来源文件
            for element in result.get("elements", []):
                element["source_file"] = file_path
            
            return result
            
        except Exception as e:
            self._logger.error(f"解析文件失败: {e}")
            return {"success": False, "error": str(e)}

    def _parse_json_file(self, file_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """解析JSON文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            elements = []
            if isinstance(data, list):
                elements = data
            elif isinstance(data, dict) and 'elements' in data:
                elements = data['elements']
            
            result = {
                "success": True,
                "elements": elements,
                "categories": self._count_categories(elements),
                "total_elements": len(elements),
                "parsed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source_file": file_path
            }
            
            return result
            
        except Exception as e:
            self._logger.error(f"解析JSON文件失败: {e}")
            return {"success": False, "error": str(e)}

    def _parse_content(self, content: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """解析文本内容"""
        self._logger.info("开始解析世界观内容")
        
        # 尝试不同格式解析
        elements = self._try_markdown_format(content)
        
        if not elements:
            elements = self._try_bracket_format(content)
        
        if not elements:
            elements = self._try_list_format(content)
        
        if not elements:
            elements = self._try_text_format(content)
        
        # 统计分类
        categories = self._count_categories(elements)
        
        result = {
            "success": True,
            "elements": elements,
            "categories": categories,
            "total_elements": len(elements),
            "parsed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        self._logger.info(f"世界观解析完成: {len(elements)} 个元素")
        return result

    def _try_markdown_format(self, content: str) -> List[Dict]:
        """尝试解析 Markdown 格式"""
        elements = []
        lines = content.split('\n')
        
        current_category = None
        current_subcategory = None
        current_element_name = None
        current_description_lines = []
        current_attributes = {}
        
        for line in lines:
            line = line.strip()
            
            if not line or line.startswith('---'):
                if current_element_name:
                    self._add_element(elements, current_category, current_subcategory,
                                     current_element_name, current_description_lines,
                                     current_attributes)
                    current_element_name = None
                    current_description_lines = []
                    current_attributes = {}
                continue
            
            # 一级标题 ## 分类
            if line.startswith('## ') and not line.startswith('###'):
                if current_element_name:
                    self._add_element(elements, current_category, current_subcategory,
                                     current_element_name, current_description_lines,
                                     current_attributes)
                    current_element_name = None
                    current_description_lines = []
                    current_attributes = {}
                
                category_name = line[3:].strip()
                current_category = category_name
                current_subcategory = None
                continue
            
            # 二级标题 ### 元素名称或子分类
            if line.startswith('### ') and not line.startswith('####'):
                if current_element_name:
                    self._add_element(elements, current_category, current_subcategory,
                                     current_element_name, current_description_lines,
                                     current_attributes)
                    current_element_name = None
                    current_description_lines = []
                    current_attributes = {}
                
                level2_name = line[4:].strip()
                
                if ('（' in level2_name or '(' in level2_name or 
                    '时代' in level2_name or '时期' in level2_name or
                    not self._is_category_name(level2_name)):
                    current_element_name = level2_name
                else:
                    current_subcategory = level2_name
                    current_element_name = None
                continue
            
            # 三级标题 #### 元素名称
            if line.startswith('#### '):
                if current_element_name:
                    self._add_element(elements, current_category, current_subcategory,
                                     current_element_name, current_description_lines,
                                     current_attributes)
                    current_element_name = None
                    current_description_lines = []
                    current_attributes = {}
                
                element_name = line[5:].strip()
                current_element_name = element_name
                continue
            
            # 列表项
            if line.startswith('- ') or line.startswith('* '):
                list_item = line[2:].strip()
                
                if not current_element_name and ':' in list_item:
                    parts = re.split(r'[:：]', list_item, 1)
                    if len(parts) == 2:
                        name = parts[0].strip()
                        desc = parts[1].strip()
                        name = self._clean_name(name)
                        if name:
                            current_element_name = name
                            current_description_lines = [desc] if desc else []
                            current_attributes = {}
                        continue
                
                if current_element_name:
                    match = re.match(r'\*\*([^*]+)\*\*\s*[:：]\s*(.*)', list_item)
                    if match:
                        attr_name = match.group(1).strip()
                        attr_value = match.group(2).strip()
                        if attr_name not in ['重要程度', '重要性']:
                            current_attributes[attr_name] = attr_value
                    else:
                        current_description_lines.append(list_item)
                continue
            
            # 编号列表项
            if re.match(r'^\d+\.\s+', line):
                list_item = re.sub(r'^\d+\.\s+', '', line).strip()
                
                if ':' in list_item or '：' in list_item:
                    parts = re.split(r'[:：]', list_item, 1)
                    if len(parts) == 2:
                        name = parts[0].strip()
                        desc = parts[1].strip()
                        name = self._clean_name(name)
                        if name:
                            if current_element_name:
                                self._add_element(elements, current_category, current_subcategory,
                                                 current_element_name, current_description_lines,
                                                 current_attributes)
                                current_description_lines = []
                                current_attributes = {}
                            
                            current_element_name = name
                            current_description_lines = [desc] if desc else []
                continue
            
            # 普通文本行
            if current_element_name:
                current_description_lines.append(line)
        
        # 保存最后一个元素
        if current_element_name:
            self._add_element(elements, current_category, current_subcategory,
                             current_element_name, current_description_lines,
                             current_attributes)
        
        return elements

    def _try_bracket_format(self, content: str) -> List[Dict]:
        """尝试解析括号格式：【分类】"""
        elements = []
        lines = content.split('\n')
        
        current_category = None
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
            
            # 检查是否是分类标题
            if line.startswith('【') and line.endswith('】'):
                current_category = line[1:-1].strip()
                continue
            
            if line.startswith('#'):
                current_category = line.lstrip('#').strip()
                continue
            
            # 跳过分隔线
            if line.startswith('-') or line.startswith('=') or line.startswith('*'):
                continue
            
            # 跳过序号
            if re.match(r'^\d+[\.\、]', line):
                line = re.sub(r'^\d+[\.\、]\s*', '', line)
            
            # 解析元素
            element = self._parse_element_line(line, current_category)
            if element:
                elements.append(element)
        
        return elements

    def _try_list_format(self, content: str) -> List[Dict]:
        """尝试解析列表格式"""
        elements = []
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
            
            # 跳过序号
            if re.match(r'^\d+[\.\、]', line):
                line = re.sub(r'^\d+[\.\、]\s*', '', line)
            
            # 解析元素
            element = self._parse_element_line(line)
            if element:
                elements.append(element)
        
        return elements

    def _try_text_format(self, content: str) -> List[Dict]:
        """尝试解析纯文本格式"""
        elements = []
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            if not line or len(line) < 2:
                continue
            
            # 跳过分隔线和序号
            if line.startswith('-') or line.startswith('=') or line.startswith('*'):
                continue
            
            if re.match(r'^\d+[\.\、]', line):
                line = re.sub(r'^\d+[\.\、]\s*', '', line)
            
            # 跳过看起来像分类的行
            if self._is_category_name(line):
                continue
            
            # 解析元素
            element = self._parse_element_line(line)
            if element:
                elements.append(element)
        
        return elements

    def _add_element(self, elements: List[Dict], category: Optional[str], 
                    subcategory: Optional[str], name: str, 
                    description_lines: List[str], attributes: Dict):
        """添加元素到列表"""
        element = {
            'category': category or '其他',
            'subcategory': subcategory,
            'name': name,
            'description': '\n'.join(description_lines),
            'attributes': attributes.copy(),
            'importance': self._config.get("default_importance", "中")
        }
        elements.append(element)

    def _parse_element_line(self, line: str, category: Optional[str] = None) -> Optional[Dict]:
        """解析单行元素"""
        # 格式1: 名称: 描述
        if ':' in line or '：' in line:
            parts = re.split(r'[:：]', line, 1)
            if len(parts) == 2:
                name = parts[0].strip()
                desc = parts[1].strip()
                
                name = self._clean_name(name)
                
                if not name:
                    return None
                
                if not category:
                    category = self._detect_category(name + desc)
                
                return {
                    'category': category or '其他',
                    'subcategory': None,
                    'name': name,
                    'description': desc,
                    'attributes': {},
                    'importance': self._config.get("default_importance", "中")
                }
        
        # 格式2: 名称（无描述）
        name = self._clean_name(line)
        if not name:
            return None
        
        if not category:
            category = self._detect_category(name)
        
        return {
            'category': category or '其他',
            'subcategory': None,
            'name': name,
            'description': '',
            'attributes': {},
            'importance': self._config.get("default_importance", "中")
        }

    def _clean_name(self, name: str) -> str:
        """清理元素名称"""
        # 移除 Markdown 加粗标记
        if name.startswith('**') and name.endswith('**'):
            name = name[2:-2].strip()
        
        # 移除多余空格
        name = name.strip()
        
        # 跳过过短的名称
        if len(name) < 2:
            return ''
        
        return name

    def _detect_category(self, text: str) -> str:
        """根据文本自动识别分类"""
        text_lower = text.lower()
        
        for category, keywords in self._category_keywords.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    return category
        
        return '其他'

    def _is_category_name(self, text: str) -> bool:
        """判断是否是分类名称"""
        text_lower = text.lower()
        
        for category, keywords in self._category_keywords.items():
            for keyword in keywords:
                if keyword.lower() == text_lower:
                    return True
        
        return False

    def _count_categories(self, elements: List[Dict]) -> Dict[str, int]:
        """统计分类数量"""
        categories = {}
        for element in elements:
            category = element.get('category', '其他')
            categories[category] = categories.get(category, 0) + 1
        return categories

    def get_supported_formats(self) -> List[str]:
        """获取支持的输入格式"""
        return ["txt", "md", "json"]

    def get_analysis_types(self) -> List[str]:
        """获取支持的分析类型"""
        return ["worldview", "elements", "categories"]

    def create_worldview(self, name: str, category: str, core_elements: str,
                         description: str = "") -> Dict[str, Any]:
        """创建新世界观（适配UI新建世界观功能）
        
        Args:
            name: 世界观名称
            category: 世界观类别（玄幻/都市/科幻/历史/奇幻等）
            core_elements: 核心元素描述
            description: 详细描述
            
        Returns:
            创建结果字典
        """
        try:
            # 生成世界观ID
            worldview_id = f"worldview_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # 创建世界观数据结构
            worldview_data = {
                "id": worldview_id,
                "name": name,
                "category": category,
                "core_elements": core_elements,
                "description": description,
                "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "modified_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "elements": [],  # 世界观元素列表
                "status": "draft",
                "importance": "中"
            }
            
            # 根据类别生成建议的世界观结构
            suggested_structure = self._suggest_worldview_structure(category)
            worldview_data["suggested_structure"] = suggested_structure
            
            # 自动解析核心元素，生成初始元素列表
            if core_elements:
                parsed_elements = self._parse_core_elements(core_elements, category)
                worldview_data["elements"] = parsed_elements
            
            self._logger.info(f"创建世界观成功: {name} ({category})")
            
            return {
                "success": True,
                "worldview_id": worldview_id,
                "worldview_data": worldview_data,
                "message": f"世界观 '{name}' 创建成功"
            }
            
        except Exception as e:
            self._logger.error(f"创建世界观失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _suggest_worldview_structure(self, category: str) -> List[Dict[str, str]]:
        """根据类别建议世界观结构"""
        structures = {
            "玄幻": [
                {"name": "时间线", "description": "历史年代、重要事件"},
                {"name": "地理位置", "description": "大陆、宗门、秘境"},
                {"name": "势力分布", "description": "正道、魔道、中立势力"},
                {"name": "修炼体系", "description": "境界、功法、灵力"},
                {"name": "种族设定", "description": "人族、妖族、神族等"}
            ],
            "都市": [
                {"name": "时间背景", "description": "年代、社会背景"},
                {"name": "地理位置", "description": "城市、区域、地标"},
                {"name": "社会阶层", "description": "职业、身份、地位"},
                {"name": "经济体系", "description": "财富、产业、资源"},
                {"name": "文化习俗", "description": "风俗、习惯、潮流"}
            ],
            "科幻": [
                {"name": "时间线", "description": "纪元、历史事件"},
                {"name": "地理位置", "description": "星球、星系、空间站"},
                {"name": "科技水平", "description": "技术水平、武器装备"},
                {"name": "种族设定", "description": "人类、AI、外星种族"},
                {"name": "政治体系", "description": "政府、联盟、势力"}
            ],
            "历史": [
                {"name": "时间线", "description": "朝代、年号、重要事件"},
                {"name": "地理位置", "description": "疆域、城市、关隘"},
                {"name": "政治体系", "description": "朝廷、官制、法律"},
                {"name": "经济体系", "description": "货币、税收、产业"},
                {"name": "文化习俗", "description": "礼仪、风俗、信仰"}
            ],
            "奇幻": [
                {"name": "时间线", "description": "纪元、历史事件"},
                {"name": "地理位置", "description": "大陆、王国、禁地"},
                {"name": "势力分布", "description": "王国、组织、教会"},
                {"name": "魔法体系", "description": "魔法类型、施法方式"},
                {"name": "种族设定", "description": "人类、精灵、矮人等"}
            ]
        }
        
        return structures.get(category, structures["玄幻"])
    
    def _parse_core_elements(self, core_elements: str, category: str) -> List[Dict]:
        """解析核心元素生成初始元素列表"""
        elements = []
        
        # 按逗号、顿号或换行分割
        parts = re.split(r'[，、,\n]+', core_elements)
        
        for i, part in enumerate(parts):
            part = part.strip()
            if part:
                elements.append({
                    "category": self._detect_category(part),
                    "name": part,
                    "description": "",
                    "importance": "中",
                    "source": "核心元素"
                })
        
        return elements[:20]  # 限制最多20个初始元素

    def shutdown(self) -> bool:
        """优雅关闭插件
        
        清理资源：
        1. 清理分类关键词
        2. 清理配置
        3. 调用父类shutdown
        """
        try:
            # 清理分类关键词
            if hasattr(self, '_category_keywords'):
                self._category_keywords.clear()
            
            # 清理配置
            if hasattr(self, '_config'):
                self._config.clear()
            
            self._logger.info(f"[{self.PLUGIN_ID}] 插件已关闭")
            return super().shutdown()
            
        except Exception as e:
            self._logger.error(f"[{self.PLUGIN_ID}] 关闭失败: {e}")
            return False


# 模块级函数
def get_plugin_class():
    return WorldviewParserPlugin

def register_plugin():
    return WorldviewParserPlugin


# 测试入口
if __name__ == "__main__":
    print("=" * 60)
    print("世界观解析器插件 V1 测试")
    print("=" * 60)
    
    plugin = WorldviewParserPlugin()
    print(f"\n1. 插件元数据:")
    print(f"   ID: {plugin.metadata.id}")
    print(f"   名称: {plugin.metadata.name}")
    print(f"   版本: {plugin.metadata.version}")
    
    test_worldview = """
## 时间线

### 上古时代

**创世之初**：天地混沌，神魔大战，最终天地分离。

**灵气复苏**：修仙者开始出现，各大宗门建立。

## 地理位置

### 东大陆

**青云宗**：位于东大陆中部，是天下第一大派。

**落霞山**：青云宗的护山大阵所在，终年云雾缭绕。

### 西大陆

**魔域**：魔族聚居之地，常年黑暗。

## 势力分布

**正道联盟**：由青云宗领导，维护天下正道。

**魔教**：潜伏于暗处，意图颠覆正道秩序。
"""
    
    result = plugin.analyze(test_worldview)
    
    if result.get("success"):
        print(f"\n2. 解析结果:")
        print(f"   元素总数: {result['total_elements']}")
        print(f"   分类统计: {result['categories']}")
        
        if result['elements']:
            print(f"\n   元素列表:")
            for el in result['elements'][:5]:
                print(f"     - [{el['category']}] {el['name']}")
    
    print(f"\n3. 支持的格式: {plugin.get_supported_formats()}")
    print(f"4. 分析类型: {plugin.get_analysis_types()}")
    
    print(f"\n" + "=" * 60)
    print("测试完成！")
