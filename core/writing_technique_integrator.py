"""
写作技巧集成器

V1.0版本
创建日期：2026-03-27

功能：
- 从GUI获取选中的写作技巧
- 调用KnowledgeReferenceSelector获取强制遵循策略
- 构建写作技巧强制引用提示词
- 集成到上下文构建流程

使用示例：
    integrator = WritingTechniqueIntegrator(workspace_root)
    
    # 从GUI获取选中的技巧
    selected_techniques = ["第一人称叙事", "心理描写", "比喻修辞"]
    
    # 构建强制引用提示词
    mandatory_prompt = integrator.build_mandatory_prompt(selected_techniques)
    
    # 集成到上下文
    context_builder.add_section("写作技巧", mandatory_prompt)
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TechniqueIntegrationResult:
    """写作技巧集成结果"""
    prompt: str                    # 强制引用提示词
    techniques_count: int          # 技巧数量
    mandatory_rules: List[str]     # 强制规则列表
    success: bool                  # 是否成功
    error: Optional[str] = None    # 错误信息


class WritingTechniqueIntegrator:
    """
    写作技巧集成器
    
    职责：
    1. 根据用户选择的写作技巧，从知识库中检索对应知识点
    2. 使用KnowledgeReferenceSelector获取强制遵循策略
    3. 构建强制引用提示词
    4. 提供Token预算建议
    """
    
    # 写作技巧名称到领域的映射
    TECHNIQUE_NAME_TO_DOMAIN = {
        # 叙事技巧
        "第一人称叙事": "narrative",
        "第三人称叙事": "narrative",
        "多视角叙事": "narrative",
        "倒叙": "narrative",
        "插叙": "narrative",
        "平行叙事": "narrative",
        
        # 描写技巧
        "心理描写": "description",
        "环境描写": "description",
        "动作描写": "description",
        "对话描写": "description",
        "细节描写": "description",
        "象征手法": "description",
        
        # 修辞技巧
        "比喻": "rhetoric",
        "拟人": "rhetoric",
        "夸张": "rhetoric",
        "排比": "rhetoric",
        "对比": "rhetoric",
        "反讽": "rhetoric",
        
        # 结构技巧
        "悬念设置": "structure",
        "伏笔铺垫": "structure",
        "高潮设计": "structure",
        "节奏控制": "structure",
        "章节衔接": "structure",
        "主题升华": "structure"
    }
    
    # 领域到JSON文件的映射
    DOMAIN_TO_FILE = {
        "narrative": "writing_technique_narrative.json",
        "description": "writing_technique_description.json",
        "rhetoric": "writing_technique_rhetoric.json",
        "structure": "writing_technique_structure.json"
    }
    
    def __init__(self, workspace_root: Path):
        """
        初始化集成器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = workspace_root
        self.knowledge_dir = workspace_root / "data" / "knowledge"
        
        # 延迟导入选择器
        self._selector = None
    
    def _get_selector(self):
        """延迟获取KnowledgeReferenceSelector实例"""
        if self._selector is None:
            try:
                from core.knowledge_reference_selector import get_reference_selector
                self._selector = get_reference_selector()
            except Exception as e:
                logger.error(f"初始化KnowledgeReferenceSelector失败: {e}")
                raise
        return self._selector
    
    def build_mandatory_prompt(
        self,
        selected_techniques: List[str]
    ) -> TechniqueIntegrationResult:
        """
        构建写作技巧强制引用提示词
        
        Args:
            selected_techniques: 用户选择的写作技巧列表
        
        Returns:
            TechniqueIntegrationResult: 集成结果
        """
        if not selected_techniques:
            return TechniqueIntegrationResult(
                prompt="",
                techniques_count=0,
                mandatory_rules=[],
                success=True
            )
        
        try:
            # 1. 检索知识点
            knowledge_points = self._fetch_knowledge_points(selected_techniques)
            
            if not knowledge_points:
                return TechniqueIntegrationResult(
                    prompt="",
                    techniques_count=0,
                    mandatory_rules=[],
                    success=False,
                    error="未找到对应的写作技巧知识点"
                )
            
            # 2. 获取强制遵循策略
            selector = self._get_selector()
            strategies = selector.batch_select_strategies(knowledge_points)
            
            # 3. 过滤强制遵循策略
            mandatory_strategies = selector.filter_mandatory_strategies(strategies)
            
            # 4. 构建提示词
            prompt = self._build_prompt(mandatory_strategies)
            
            mandatory_rules = [s.guidance for s in mandatory_strategies]
            
            return TechniqueIntegrationResult(
                prompt=prompt,
                techniques_count=len(mandatory_strategies),
                mandatory_rules=mandatory_rules,
                success=True
            )
            
        except Exception as e:
            logger.error(f"构建写作技巧提示词失败: {e}", exc_info=True)
            return TechniqueIntegrationResult(
                prompt="",
                techniques_count=0,
                mandatory_rules=[],
                success=False,
                error=str(e)
            )
    
    def _fetch_knowledge_points(self, technique_names: List[str]) -> List[Dict[str, Any]]:
        """
        从知识库检索写作技巧知识点
        
        Args:
            technique_names: 技巧名称列表
        
        Returns:
            知识点列表
        """
        import json
        
        knowledge_points = []
        
        # 按领域分组技巧
        domain_to_techniques = {}
        for name in technique_names:
            domain = self.TECHNIQUE_NAME_TO_DOMAIN.get(name)
            if domain:
                if domain not in domain_to_techniques:
                    domain_to_techniques[domain] = []
                domain_to_techniques[domain].append(name)
        
        # 从对应JSON文件加载知识点
        for domain, techniques in domain_to_techniques.items():
            json_file = self.knowledge_dir / self.DOMAIN_TO_FILE[domain]
            
            if not json_file.exists():
                logger.warning(f"写作技巧知识库文件不存在: {json_file}")
                continue
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    all_points = json.load(f)
                
                # 根据技巧名称过滤
                for point in all_points:
                    if point.get("title") in techniques:
                        knowledge_points.append(point)
                
            except Exception as e:
                logger.error(f"加载写作技巧知识库失败: {json_file}, 错误: {e}")
        
        return knowledge_points
    
    def _build_prompt(self, mandatory_strategies: List[Any]) -> str:
        """
        构建强制引用提示词
        
        Args:
            mandatory_strategies: 强制遵循策略列表
        
        Returns:
            提示词文本
        """
        if not mandatory_strategies:
            return ""
        
        prompt_parts = [
            "【写作技巧强制遵循规则】",
            "以下写作技巧是AI必须100%遵守的规则，不得违反：",
            ""
        ]
        
        for i, strategy in enumerate(mandatory_strategies, 1):
            prompt_parts.append(f"{i}. **{strategy.title}**")
            prompt_parts.append(f"   {strategy.guidance}")
            prompt_parts.append("")
        
        prompt_parts.extend([
            "⚠️ 注意：",
            "- 上述规则必须严格执行，不得省略或变通",
            "- 如果生成内容违反任何一条规则，将被视为不合格",
            "- 请在生成前确认理解所有规则"
        ])
        
        return "\n".join(prompt_parts)
    
    def suggest_token_budget(self, techniques_count: int) -> int:
        """
        建议Token预算
        
        Args:
            techniques_count: 技巧数量
        
        Returns:
            建议的Token预算
        """
        # 每个技巧约占用200 tokens
        base_budget = 100  # 基础开销
        per_technique_budget = 200
        
        return base_budget + techniques_count * per_technique_budget


# ============================================================================
# 便捷函数
# ============================================================================

def get_writing_technique_integrator(workspace_root: Path) -> WritingTechniqueIntegrator:
    """获取写作技巧集成器实例"""
    return WritingTechniqueIntegrator(workspace_root)
