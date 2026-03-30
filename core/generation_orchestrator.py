"""
创作流程编排器

V1.0版本
创建日期：2026-03-27

功能：
- 编排创作流程（传统知识库 + 写作技巧库）
- 集成两种知识库的调用逻辑
- 构建完整的生成提示词
- 提供给GUI调用的统一接口

设计参考：
- 灵活联动方案 13.知识库与创作灵活联动方案✅️.md
- V5核心模块保护规则

使用示例：
    orchestrator = GenerationOrchestrator(workspace_root)
    
    # GUI调用
    result = orchestrator.prepare_generation(
        selected_kb=["scifi", "xuanhuan"],
        selected_techniques=["第一人称叙事", "心理描写"],
        chapter_range=(1, 3),
        target_words=900
    )
    
    # 获取构建好的提示词
    prompt = result.prompt
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class GenerationPreparationResult:
    """生成准备结果"""
    prompt: str                           # 完整提示词
    kb_references: List[str]              # 传统知识库引用列表
    technique_references: List[str]       # 写作技巧引用列表
    total_tokens: int                     # 总Token数
    success: bool                         # 是否成功
    error: Optional[str] = None           # 错误信息
    metadata: Dict[str, Any] = None       # 元数据


class GenerationOrchestrator:
    """
    创作流程编排器
    
    职责：
    1. 整合传统知识库和写作技巧库
    2. 构建完整的生成提示词
    3. 提供给GUI的统一调用接口
    
    工作流程：
    1. 接收GUI的用户选择（知识库分类 + 写作技巧）
    2. 传统知识库：调用KnowledgeReferenceSelector，获取灵活引用策略
    3. 写作技巧库：调用WritingTechniqueIntegrator，获取强制遵循规则
    4. 构建完整提示词：项目设定 + 传统知识库 + 写作技巧库
    5. 返回构建结果
    """
    
    def __init__(self, workspace_root: Path):
        """
        初始化编排器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = workspace_root
        
        # 延迟导入依赖模块
        self._kb_selector = None
        self._technique_integrator = None
        self._context_builder = None
    
    def _get_kb_selector(self):
        """延迟获取知识库选择器"""
        if self._kb_selector is None:
            try:
                from core.knowledge_reference_selector import get_reference_selector
                self._kb_selector = get_reference_selector()
            except Exception as e:
                logger.error(f"初始化KnowledgeReferenceSelector失败: {e}")
                raise
        return self._kb_selector
    
    def _get_technique_integrator(self):
        """延迟获取写作技巧集成器"""
        if self._technique_integrator is None:
            try:
                from core.writing_technique_integrator import get_writing_technique_integrator
                self._technique_integrator = get_writing_technique_integrator(self.workspace_root)
            except Exception as e:
                logger.error(f"初始化WritingTechniqueIntegrator失败: {e}")
                raise
        return self._technique_integrator
    
    def prepare_generation(
        self,
        selected_kb: List[str],
        selected_techniques: List[str],
        chapter_range: Tuple[int, int],
        target_words: int,
        project_context: Optional[Dict[str, Any]] = None
    ) -> GenerationPreparationResult:
        """
        准备生成任务
        
        Args:
            selected_kb: 选中的传统知识库分类（如["scifi", "xuanhuan"]）
            selected_techniques: 选中的写作技巧（如["第一人称叙事", "心理描写"]）
            chapter_range: 章节范围（起始, 结束）
            target_words: 目标字数
            project_context: 项目上下文（世界观、人物、大纲、风格）
        
        Returns:
            GenerationPreparationResult: 生成准备结果
        """
        try:
            # 1. 处理传统知识库（灵活引用）
            kb_prompt, kb_refs = self._process_traditional_kb(selected_kb)
            
            # 2. 处理写作技巧库（强制遵循）
            technique_prompt, technique_refs = self._process_writing_techniques(selected_techniques)
            
            # 3. 构建完整提示词
            full_prompt = self._build_full_prompt(
                project_context=project_context,
                kb_prompt=kb_prompt,
                technique_prompt=technique_prompt,
                chapter_range=chapter_range,
                target_words=target_words
            )
            
            # 4. 估算Token数
            total_tokens = len(full_prompt) // 4  # 粗略估算：1 token ≈ 4 字符
            
            return GenerationPreparationResult(
                prompt=full_prompt,
                kb_references=kb_refs,
                technique_references=technique_refs,
                total_tokens=total_tokens,
                success=True,
                metadata={
                    "selected_kb": selected_kb,
                    "selected_techniques": selected_techniques,
                    "chapter_range": chapter_range,
                    "target_words": target_words
                }
            )
            
        except Exception as e:
            logger.error(f"准备生成任务失败: {e}", exc_info=True)
            return GenerationPreparationResult(
                prompt="",
                kb_references=[],
                technique_references=[],
                total_tokens=0,
                success=False,
                error=str(e)
            )
    
    def _process_traditional_kb(
        self,
        selected_kb: List[str]
    ) -> Tuple[str, List[str]]:
        """
        处理传统知识库（灵活引用）
        
        Args:
            selected_kb: 选中的知识库分类
        
        Returns:
            (提示词, 引用列表)
        """
        if not selected_kb:
            return "", []
        
        # 从向量库检索知识点
        try:
            from core.knowledge_retriever import get_knowledge_retriever
            retriever = get_knowledge_retriever(self.workspace_root)
            
            # 检索每个分类的知识点
            all_knowledge = []
            for category in selected_kb:
                if category == "writing_technique":
                    continue  # 跳过写作技巧库
                
                # 简单检索：获取该分类的前10个知识点
                # 实际应使用向量检索
                knowledge_list = self._fetch_kb_by_category(category)
                all_knowledge.extend(knowledge_list)
            
            if not all_knowledge:
                return "", []
            
            # 获取引用策略
            selector = self._get_kb_selector()
            strategies = selector.batch_select_strategies(all_knowledge)
            
            # 过滤灵活引用策略
            flexible_strategies = selector.filter_flexible_strategies(strategies)
            
            # 构建提示词
            prompt_parts = [
                "【知识库参考】",
                "以下知识点可作为创作参考，灵活引用：",
                ""
            ]
            
            refs = []
            for strategy in flexible_strategies[:5]:  # 最多5个
                prompt_parts.append(f"- {strategy.title}")
                prompt_parts.append(f"  {strategy.guidance}")
                refs.append(strategy.knowledge_id)
            
            return "\n".join(prompt_parts), refs
            
        except Exception as e:
            logger.warning(f"处理传统知识库失败: {e}")
            return "", []
    
    def _process_writing_techniques(
        self,
        selected_techniques: List[str]
    ) -> Tuple[str, List[str]]:
        """
        处理写作技巧库（强制遵循）
        
        Args:
            selected_techniques: 选中的写作技巧
        
        Returns:
            (提示词, 引用列表)
        """
        if not selected_techniques:
            return "", []
        
        integrator = self._get_technique_integrator()
        result = integrator.build_mandatory_prompt(selected_techniques)
        
        return result.prompt, result.mandatory_rules
    
    def _build_full_prompt(
        self,
        project_context: Optional[Dict[str, Any]],
        kb_prompt: str,
        technique_prompt: str,
        chapter_range: Tuple[int, int],
        target_words: int
    ) -> str:
        """
        构建完整提示词
        
        Args:
            project_context: 项目上下文
            kb_prompt: 知识库提示词
            technique_prompt: 写作技巧提示词
            chapter_range: 章节范围
            target_words: 目标字数
        
        Returns:
            完整提示词
        """
        prompt_parts = []
        
        # 1. 项目设定（如果有）
        if project_context:
            prompt_parts.append("【项目设定】")
            if "worldview" in project_context:
                prompt_parts.append(f"世界观：{project_context['worldview'][:500]}")
            if "characters" in project_context:
                prompt_parts.append(f"人物：{project_context['characters'][:500]}")
            if "outline" in project_context:
                prompt_parts.append(f"大纲：{project_context['outline'][:500]}")
            if "style" in project_context:
                prompt_parts.append(f"风格：{project_context['style'][:500]}")
            prompt_parts.append("")
        
        # 2. 写作技巧（强制遵循，优先级最高）
        if technique_prompt:
            prompt_parts.append(technique_prompt)
            prompt_parts.append("")
        
        # 3. 传统知识库（灵活引用）
        if kb_prompt:
            prompt_parts.append(kb_prompt)
            prompt_parts.append("")
        
        # 4. 生成要求
        prompt_parts.extend([
            "【生成要求】",
            f"- 章节范围：第{chapter_range[0]}章 至 第{chapter_range[1]}章",
            f"- 目标字数：{target_words}字/章",
            f"- 必须严格遵守上述写作技巧规则",
            f"- 可灵活引用传统知识库内容",
            f"- 章节结尾必须包含【本章完】标记",
            ""
        ])
        
        return "\n".join(prompt_parts)
    
    def _fetch_kb_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        从JSON文件加载指定分类的知识点
        
        Args:
            category: 分类名称
        
        Returns:
            知识点列表
        """
        knowledge_dir = self.workspace_root / "data" / "knowledge"
        
        # 查找该分类的所有JSON文件
        knowledge_points = []
        
        # 遍历knowledge目录下的所有JSON文件
        for json_file in knowledge_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    points = json.load(f)
                
                # 过滤指定分类
                for point in points:
                    if point.get("category") == category:
                        knowledge_points.append(point)
                
            except Exception as e:
                logger.warning(f"加载知识库文件失败: {json_file}, 错误: {e}")
        
        return knowledge_points


# ============================================================================
# 便捷函数
# ============================================================================

def get_generation_orchestrator(workspace_root: Path) -> GenerationOrchestrator:
    """获取创作流程编排器实例"""
    return GenerationOrchestrator(workspace_root)
