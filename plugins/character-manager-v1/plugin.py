"""
人物管理器插件 V1.0

版本: 1.0.0
创建日期: 2026-03-23
迁移来源: V5 scripts/character_manager/character_manager.py

功能:
- 人物档案创建和管理
- 一致性检查（性格、外貌、背景、行为、对话）
- 人物关系管理
- 人物互动分析
- 人物发展建议生成

参考文档:
- 《项目总体架构设计说明书V1.3》第四章
- 《插件接口定义V2.1》
"""

import os
import re
import json
import uuid
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict, field
from enum import Enum

import sys
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.plugin_interface import AnalyzerPlugin, PluginMetadata, PluginType, PluginContext


class Gender(Enum):
    """性别枚举"""
    MALE = "男"
    FEMALE = "女"
    UNKNOWN = "未知"


class RelationshipType(Enum):
    """关系类型枚举"""
    FAMILY = "家人"
    FRIEND = "朋友"
    ENEMY = "敌人"
    LOVE = "恋人"
    MENTOR = "师徒"
    RIVAL = "对手"
    ALLY = "盟友"
    NEUTRAL = "中立"


@dataclass
class BasicInfo:
    """基本信息"""
    name: str
    age: int = 25
    gender: str = "未知"
    occupation: str = ""
    affiliation: str = ""


@dataclass
class Personality:
    """性格设定"""
    traits: List[str] = field(default_factory=list)
    values: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    fears: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)


@dataclass
class Appearance:
    """外貌设定"""
    build: str = ""
    hair_style: str = ""
    distinguishing_features: List[str] = field(default_factory=list)


@dataclass
class Background:
    """背景设定"""
    upbringing: str = ""
    important_events: List[str] = field(default_factory=list)
    trauma: List[str] = field(default_factory=list)


@dataclass
class Relationship:
    """人物关系"""
    target_character: str
    relationship_type: str
    strength: float = 0.5
    description: str = ""
    current_status: str = "活跃"


@dataclass
class CharacterProfile:
    """人物档案"""
    id: str
    basic_info: BasicInfo
    personality: Personality
    appearance: Appearance
    background: Background
    relationships: List[Relationship] = field(default_factory=list)
    created_date: str = ""
    modified_date: str = ""


class CharacterManagerPlugin(AnalyzerPlugin):
    """人物管理器插件 - V5核心模块迁移

    实现 AnalyzerPlugin 接口，提供人物管理功能。

    分析类型:
    - character: 人物档案分析
    - consistency: 一致性检查
    - relationship: 关系分析
    - interaction: 互动分析

    支持格式:
    - txt: 纯文本
    - json: JSON格式人物档案
    """

    PLUGIN_ID = "character-manager-v1"
    PLUGIN_NAME = "人物管理器 V1"
    PLUGIN_VERSION = "1.0.0"

    def __init__(self):
        """初始化插件"""
        metadata = PluginMetadata(
            id=self.PLUGIN_ID,
            name=self.PLUGIN_NAME,
            version=self.PLUGIN_VERSION,
            description="人物设定管理器，提供人物创建、一致性检查、关系管理等功能",
            author="项目组",
            plugin_type=PluginType.ANALYZER,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=[],
            permissions=["file.read", "file.write"],
            min_platform_version="6.0.0",
            entry_class="CharacterManagerPlugin",
        )
        super().__init__(metadata)
        
        self._config = {}
        self._profiles: Dict[str, CharacterProfile] = {}
        self._logger = logging.getLogger(__name__)

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            id=cls.PLUGIN_ID,
            name=cls.PLUGIN_NAME,
            version=cls.PLUGIN_VERSION,
            description="人物设定管理器，提供人物创建、一致性检查、关系管理等功能",
            author="项目组",
            plugin_type=PluginType.ANALYZER,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=[],
            permissions=["file.read", "file.write"],
            min_platform_version="6.0.0",
            entry_class="CharacterManagerPlugin",
        )

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件"""
        if not super().initialize(context):
            return False

        # 加载配置
        self._config = self._load_config()
        
        # 初始化人物档案存储
        self._profiles = {}
        
        return True

    def _load_config(self) -> Dict:
        """加载配置"""
        default_config = {
            "profiles_dir": "人物设定",
            "supported_formats": [".json", ".txt"],
            "encoding": "utf-8",
        }
        
        if self._context and self._context.config_manager:
            user_config = self._context.config_manager.get("plugins.character_manager", {})
            default_config.update(user_config)
        
        return default_config

    def analyze(self, content: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """分析人物内容

        Args:
            content: 人物描述文本或文件路径
            options: 分析选项
                - analysis_type: 分析类型 (profile/consistency/relationship/interaction)
                - character_id: 人物ID（用于一致性检查）
                - content: 待检查的文本内容

        Returns:
            分析结果字典
        """
        options = options or {}
        analysis_type = options.get("analysis_type", "profile")
        
        # 检查是否是文件路径
        if content and os.path.exists(content):
            return self._analyze_file(content, options)
        
        # 根据分析类型执行不同分析
        if analysis_type == "consistency":
            return self._check_consistency(content, options)
        elif analysis_type == "relationship":
            return self._analyze_relationships(options)
        elif analysis_type == "interaction":
            return self._analyze_interaction(options)
        else:
            return self._create_profile_from_text(content, options)

    def _analyze_file(self, file_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """分析文件"""
        if file_path.endswith('.json'):
            return self._load_profile_from_json(file_path)
        elif file_path.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self._create_profile_from_text(content, options)
        else:
            return {"success": False, "error": f"不支持的文件格式"}

    def _create_profile_from_text(self, text: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """从文本创建人物档案"""
        # 提取基本信息
        name = self._extract_name(text)
        age = self._extract_age(text)
        gender = self._extract_gender(text)
        occupation = self._extract_occupation(text)
        
        # 提取性格设定
        traits = self._extract_traits(text)
        values = self._extract_values(text)
        goals = self._extract_goals(text)
        weaknesses = self._extract_weaknesses(text)
        
        # 创建档案
        profile = CharacterProfile(
            id=str(uuid.uuid4())[:8],
            basic_info=BasicInfo(
                name=name,
                age=age,
                gender=gender,
                occupation=occupation
            ),
            personality=Personality(
                traits=traits,
                values=values,
                goals=goals,
                weaknesses=weaknesses
            ),
            appearance=Appearance(),
            background=Background(),
            created_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        # 保存到内存
        self._profiles[profile.id] = profile
        
        return {
            "success": True,
            "profile": asdict(profile),
            "message": f"人物档案创建成功: {name}"
        }

    def _extract_name(self, text: str) -> str:
        """提取姓名"""
        patterns = [
            r'姓名[:：]\s*(\S+)',
            r'名字[:：]\s*(\S+)',
            r'人物[:：]\s*(\S+)',
            r'^([^，。！？\n]{2,4})'  # 开头的2-4个字
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return "未命名人物"

    def _extract_age(self, text: str) -> int:
        """提取年龄"""
        match = re.search(r'年龄[:：]\s*(\d+)', text)
        if match:
            return int(match.group(1))
        return 25

    def _extract_gender(self, text: str) -> str:
        """提取性别"""
        if '男' in text:
            return "男"
        elif '女' in text:
            return "女"
        return "未知"

    def _extract_occupation(self, text: str) -> str:
        """提取职业"""
        patterns = [
            r'职业[:：]\s*([^\n，。]+)',
            r'身份[:：]\s*([^\n，。]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_traits(self, text: str) -> List[str]:
        """提取性格特质"""
        traits = []
        patterns = [
            r'性格[:：]\s*([^\n]+)',
            r'特质[:：]\s*([^\n]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                trait_str = match.group(1)
                # 分割并清理
                raw_traits = re.split(r'[，、,，]', trait_str)
                traits = [t.strip() for t in raw_traits if t.strip()]
                break
        return traits[:10]

    def _extract_values(self, text: str) -> List[str]:
        """提取价值观"""
        values = []
        match = re.search(r'价值观[:：]\s*([^\n]+)', text)
        if match:
            value_str = match.group(1)
            raw_values = re.split(r'[，、,，]', value_str)
            values = [v.strip() for v in raw_values if v.strip()]
        return values[:10]

    def _extract_goals(self, text: str) -> List[str]:
        """提取目标"""
        goals = []
        patterns = [
            r'目标[:：]\s*([^\n]+)',
            r'追求[:：]\s*([^\n]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                goal_str = match.group(1)
                raw_goals = re.split(r'[，、,，]', goal_str)
                goals = [g.strip() for g in raw_goals if g.strip()]
                break
        return goals[:10]

    def _extract_weaknesses(self, text: str) -> List[str]:
        """提取弱点"""
        weaknesses = []
        patterns = [
            r'弱点[:：]\s*([^\n]+)',
            r'缺点[:：]\s*([^\n]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                weak_str = match.group(1)
                raw_weak = re.split(r'[，、,，]', weak_str)
                weaknesses = [w.strip() for w in raw_weak if w.strip()]
                break
        return weaknesses[:10]

    def _load_profile_from_json(self, file_path: str) -> Dict[str, Any]:
        """从JSON文件加载人物档案"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            profile = CharacterProfile(
                id=data.get('id', str(uuid.uuid4())[:8]),
                basic_info=BasicInfo(**data.get('basic_info', {})),
                personality=Personality(**data.get('personality', {})),
                appearance=Appearance(**data.get('appearance', {})),
                background=Background(**data.get('background', {})),
                relationships=[Relationship(**r) for r in data.get('relationships', [])],
                created_date=data.get('created_date', ''),
                modified_date=data.get('modified_date', '')
            )
            
            self._profiles[profile.id] = profile
            
            return {
                "success": True,
                "profile": asdict(profile),
                "message": f"人物档案加载成功: {profile.basic_info.name}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _check_consistency(self, content: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """检查人物一致性"""
        character_id = options.get("character_id")
        
        if not character_id or character_id not in self._profiles:
            return {
                "success": False,
                "error": "请提供有效的人物ID"
            }
        
        profile = self._profiles[character_id]
        
        # 执行一致性检查
        results = {
            'personality_consistency': self._check_personality(content, profile),
            'behavior_consistency': self._check_behavior(content, profile),
            'dialogue_consistency': self._check_dialogue(content, profile),
        }
        
        # 计算总分
        overall_score = sum(r['score'] for r in results.values()) / len(results)
        
        # 生成建议
        suggestions = self._generate_suggestions(results)
        
        return {
            "success": True,
            "character_name": profile.basic_info.name,
            "overall_score": round(overall_score, 2),
            "detailed_results": results,
            "suggestions": suggestions,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def _check_personality(self, content: str, profile: CharacterProfile) -> Dict[str, Any]:
        """检查性格一致性"""
        personality = profile.personality
        matches = 0
        
        for trait in personality.traits:
            if trait in content:
                matches += 1
        
        score = matches / len(personality.traits) if personality.traits else 1.0
        
        return {
            'score': round(score, 2),
            'matches': matches,
            'total_traits': len(personality.traits)
        }

    def _check_behavior(self, content: str, profile: CharacterProfile) -> Dict[str, Any]:
        """检查行为一致性"""
        # 简化版：检查人物行为是否符合性格
        behavior_count = len(re.findall(r'[。！？]', content))
        
        # 默认评分
        score = 0.8 if behavior_count > 0 else 1.0
        
        return {
            'score': score,
            'behavior_count': behavior_count
        }

    def _check_dialogue(self, content: str, profile: CharacterProfile) -> Dict[str, Any]:
        """检查对话一致性"""
        # 提取对话
        dialogues = re.findall(r'["「]([^"」]+)["」]', content)
        
        if not dialogues:
            return {
                'score': 1.0,
                'dialogue_count': 0,
                'note': '无对话内容'
            }
        
        # 检查对话风格
        consistent_count = 0
        for dialogue in dialogues:
            # 简化版：检查是否包含性格关键词
            for trait in profile.personality.traits:
                if trait in dialogue:
                    consistent_count += 1
                    break
        
        score = consistent_count / len(dialogues) if dialogues else 1.0
        
        return {
            'score': round(score, 2),
            'dialogue_count': len(dialogues),
            'consistent_count': consistent_count
        }

    def _generate_suggestions(self, results: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        for check_type, result in results.items():
            score = result.get('score', 1.0)
            
            if score < 0.7:
                if check_type == 'personality_consistency':
                    suggestions.append("加强人物性格描写，使其更符合设定")
                elif check_type == 'behavior_consistency':
                    suggestions.append("调整人物行为，使其更符合性格特征")
                elif check_type == 'dialogue_consistency':
                    suggestions.append("优化人物对话，使其更符合说话风格")
        
        return suggestions[:5]

    def _analyze_relationships(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """分析人物关系"""
        nodes = []
        edges = []
        
        for profile in self._profiles.values():
            nodes.append({
                'id': profile.id,
                'name': profile.basic_info.name,
                'gender': profile.basic_info.gender,
                'occupation': profile.basic_info.occupation
            })
            
            for rel in profile.relationships:
                target = self._get_profile_by_name(rel.target_character)
                if target:
                    edges.append({
                        'source': profile.id,
                        'target': target.id,
                        'type': rel.relationship_type,
                        'strength': rel.strength
                    })
        
        return {
            "success": True,
            "nodes": nodes,
            "edges": edges,
            "total_characters": len(nodes),
            "total_relationships": len(edges)
        }

    def _analyze_interaction(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """分析人物互动"""
        char1_id = options.get("character1_id")
        char2_id = options.get("character2_id")
        
        if not char1_id or not char2_id:
            return {
                "success": False,
                "error": "请提供两个人物ID"
            }
        
        if char1_id not in self._profiles or char2_id not in self._profiles:
            return {
                "success": False,
                "error": "人物不存在"
            }
        
        char1 = self._profiles[char1_id]
        char2 = self._profiles[char2_id]
        
        # 计算兼容性
        compatibility = self._calculate_compatibility(char1, char2)
        
        # 生成对话建议
        dialogue = self._generate_dialogue(char1, char2)
        
        return {
            "success": True,
            "character1": char1.basic_info.name,
            "character2": char2.basic_info.name,
            "compatibility_score": compatibility,
            "suggested_dialogue": dialogue,
            "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def _get_profile_by_name(self, name: str) -> Optional[CharacterProfile]:
        """根据姓名获取档案"""
        for profile in self._profiles.values():
            if profile.basic_info.name == name:
                return profile
        return None

    def _calculate_compatibility(self, char1: CharacterProfile, char2: CharacterProfile) -> float:
        """计算人物兼容性"""
        compatibility = 0.5
        
        # 性格特质相似度
        traits1 = set(char1.personality.traits)
        traits2 = set(char2.personality.traits)
        
        if traits1 and traits2:
            common = traits1.intersection(traits2)
            similarity = len(common) / max(len(traits1), len(traits2))
            compatibility += similarity * 0.3
        
        return round(min(compatibility, 1.0), 2)

    def _generate_dialogue(self, char1: CharacterProfile, char2: CharacterProfile) -> str:
        """生成对话建议"""
        return f"{char1.basic_info.name}看着{char2.basic_info.name}，说道：" \
               f"\"你好，{char2.basic_info.name}，很高兴见到你。\""

    def create_character(self, name: str, role_type: str = "主角", 
                        appearance: str = "", personality: str = "",
                        background: str = "", abilities: str = "") -> Dict[str, Any]:
        """创建新人物（适配UI新建人物弹窗）
        
        对应UI弹窗字段：
        - 姓名 → name
        - 角色类型 → role_type（主角/配角/反派/路人）
        - 外貌描述 → appearance
        - 性格特点 → personality
        - 背景故事 → background
        - 能力特长 → abilities
        
        Args:
            name: 姓名
            role_type: 角色类型（主角/配角/反派/路人）
            appearance: 外貌描述
            personality: 性格特点
            background: 背景故事
            abilities: 能力特长
            
        Returns:
            创建结果字典
        """
        try:
            # 生成人物ID
            character_id = f"char_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # 解析性格特点（逗号分割）
            traits = [t.strip() for t in re.split(r'[，、,，]', personality) if t.strip()] if personality else []
            
            # 解析能力特长
            skills = [s.strip() for s in re.split(r'[，、,，]', abilities) if s.strip()] if abilities else []
            
            # 创建人物档案
            profile = CharacterProfile(
                id=character_id,
                basic_info=BasicInfo(
                    name=name,
                    age=25,
                    gender="未知",
                    occupation=role_type,
                    affiliation=""
                ),
                personality=Personality(
                    traits=traits,
                    values=[],
                    goals=[],
                    fears=[],
                    skills=skills,
                    weaknesses=[]
                ),
                appearance=Appearance(
                    build="",
                    hair_style="",
                    distinguishing_features=[appearance] if appearance else []
                ),
                background=Background(
                    upbringing=background,
                    important_events=[],
                    trauma=[]
                ),
                relationships=[],
                created_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                modified_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
            # 保存到内存
            self._profiles[character_id] = profile
            
            self._logger.info(f"创建人物成功: {name} ({role_type})")
            
            return {
                "success": True,
                "character_id": character_id,
                "profile": asdict(profile),
                "message": f"人物 '{name}' 创建成功"
            }
            
        except Exception as e:
            self._logger.error(f"创建人物失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_profile(self, name: str, **kwargs) -> Dict[str, Any]:
        """创建人物档案（兼容旧接口）
        
        Args:
            name: 人物名称
            **kwargs: 其他属性
            
        Returns:
            创建结果字典
        """
        # 映射到新方法
        return self.create_character(
            name=name,
            role_type=kwargs.get('role_type', kwargs.get('occupation', '主角')),
            appearance=kwargs.get('appearance', ''),
            personality=','.join(kwargs.get('traits', [])) if kwargs.get('traits') else '',
            background=kwargs.get('upbringing', ''),
            abilities=','.join(kwargs.get('skills', [])) if kwargs.get('skills') else ''
        )

    def list_profiles(self) -> List[Dict[str, Any]]:
        """列出所有人物档案"""
        return [
            {
                "id": profile.id,
                "name": profile.basic_info.name,
                "gender": profile.basic_info.gender,
                "age": profile.basic_info.age,
                "occupation": profile.basic_info.occupation
            }
            for profile in self._profiles.values()
        ]

    def get_supported_formats(self) -> List[str]:
        """获取支持的输入格式"""
        return ["txt", "json"]

    def get_analysis_types(self) -> List[str]:
        """获取支持的分析类型"""
        return ["profile", "consistency", "relationship", "interaction"]

    def shutdown(self) -> bool:
        """优雅关闭插件
        
        清理资源：
        1. 清理人物档案存储
        2. 清理配置
        3. 调用父类shutdown
        """
        try:
            # 清理人物档案存储
            if hasattr(self, '_profiles'):
                self._profiles.clear()
            
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
    return CharacterManagerPlugin

def register_plugin():
    return CharacterManagerPlugin


# 测试入口
if __name__ == "__main__":
    print("=" * 60)
    print("人物管理器插件 V1 测试")
    print("=" * 60)
    
    plugin = CharacterManagerPlugin()
    print(f"\n1. 插件元数据:")
    print(f"   ID: {plugin.metadata.id}")
    print(f"   名称: {plugin.metadata.name}")
    print(f"   版本: {plugin.metadata.version}")
    
    # 创建人物档案
    print(f"\n2. 创建人物档案:")
    result = plugin.create_profile(
        name="林风",
        age=28,
        gender="男",
        occupation="捕快",
        traits=["正义", "勇敢", "聪明", "责任心强"],
        values=["正义", "真相", "保护弱者"],
        goals=["查明真相", "保护百姓", "维护正义"],
        weaknesses=["有时过于固执", "容易感情用事"]
    )
    
    if result.get("success"):
        print(f"   创建成功: {result['profile']['basic_info']['name']}")
        print(f"   ID: {result['character_id']}")
    
    # 列出档案
    print(f"\n3. 人物列表:")
    profiles = plugin.list_profiles()
    for p in profiles:
        print(f"   - {p['name']} ({p['gender']}, {p['age']}岁, {p['occupation']})")
    
    print(f"\n4. 支持的格式: {plugin.get_supported_formats()}")
    print(f"5. 分析类型: {plugin.get_analysis_types()}")
    
    print(f"\n" + "=" * 60)
    print("测试完成！")
