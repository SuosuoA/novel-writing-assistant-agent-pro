#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识库验证器主控制器

负责协调验证流程，管理生命周期。

P2安全增强：
- 路径安全检查集成
- 权限验证集成
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Any, Optional

from .deduplication_engine import DeduplicationEngine
from .quality_evaluator import QualityEvaluator
from .file_cleaner import FileCleaner, PathSecurityError, PermissionError
from .claw_optimizer import ClawOptimizer

logger = logging.getLogger(__name__)


class KnowledgeVerifier:
    """知识库验证Agent - 主控制器"""
    
    def __init__(self, workspace_root: Path):
        """
        初始化验证器
        
        P2安全增强：设置允许操作的目录白名单
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = Path(workspace_root).resolve()
        self.knowledge_dir = self.workspace_root / "data" / "knowledge"
        self.backup_dir = self.workspace_root / "data" / "知识库验证器" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # P2安全增强：设置允许操作的目录白名单
        allowed_dirs = [
            self.knowledge_dir,
            self.backup_dir,
            self.workspace_root / "data"
        ]
        
        # 初始化子模块
        self.dedup_engine = DeduplicationEngine(workspace_root)
        self.quality_evaluator = QualityEvaluator()
        self.claw_optimizer = ClawOptimizer(workspace_root)
        self.file_cleaner = FileCleaner(self.backup_dir, allowed_dirs)
        
        logger.info(f"[KNOWLEDGE_VERIFIER] 初始化完成, 知识库目录: {self.knowledge_dir}")
    
    def verify_all(self, 
                  enable_dedup: bool = True,
                  enable_quality: bool = True,
                  dry_run: bool = False,
                  progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        批量验证所有知识点
        
        Args:
            enable_dedup: 是否启用查重
            enable_quality: 是否启用质量评估
            dry_run: 干运行（只检查，不删除）
            progress_callback: 进度回调 callback(percent, message, detail)
        
        Returns:
            {
                "timestamp": datetime.now().isoformat(),
                "total_knowledge": 1130,
                "dedup_removed": 50,
                "quality_removed": 30,
                "removed_count": 80,
                "final_count": 1050,
                "removed_ids": [...],
                "reasons": {...},
                "optimization_data": {...},
                "dry_run": dry_run
            }
        """
        logger.info("[KNOWLEDGE_VERIFIER] 开始批量验证")
        
        # 1. 收集所有知识点 (5%)
        if progress_callback:
            progress_callback(5, "收集知识点...", "")
        
        all_knowledge = self._collect_all_knowledge()
        total_count = len(all_knowledge)
        
        logger.info(f"[KNOWLEDGE_VERIFIER] 共收集 {total_count} 条知识点")
        
        if total_count == 0:
            return {
                "timestamp": datetime.now().isoformat(),
                "total_knowledge": 0,
                "dedup_removed": 0,
                "quality_removed": 0,
                "removed_count": 0,
                "final_count": 0,
                "removed_ids": [],
                "reasons": {},
                "optimization_data": {},
                "dry_run": dry_run
            }
        
        # 2. 查重 (5%-40%)
        duplicate_ids: Set[str] = set()
        if enable_dedup:
            if progress_callback:
                progress_callback(10, "检测重复词条...", "正在执行完全匹配去重...")
            
            duplicate_ids.update(self._dedup_all(all_knowledge, progress_callback))
        
        logger.info(f"[KNOWLEDGE_VERIFIER] 检测到 {len(duplicate_ids)} 条重复词条")
        
        # 3. 质量评估 (40%-70%)
        low_quality_ids: Set[str] = set()
        if enable_quality:
            if progress_callback:
                progress_callback(45, "评估词条质量...", "正在评估内容长度...")
            
            low_quality_ids.update(self._evaluate_all_quality(all_knowledge, progress_callback))
        
        logger.info(f"[KNOWLEDGE_VERIFIER] 检测到 {len(low_quality_ids)} 条低质量词条")
        
        # 4. 合并删除列表
        to_remove = duplicate_ids | low_quality_ids
        removed_count = len(to_remove)
        
        # 5. 构建删除原因映射
        reasons = {}
        for kp_id in duplicate_ids:
            reasons[kp_id] = "duplicate"
        
        for kp_id in low_quality_ids:
            if kp_id in reasons:
                reasons[kp_id] = "duplicate_and_low_quality"
            else:
                reasons[kp_id] = "low_quality"
        
        # 6. 执行删除 (70%-90%)
        if not dry_run and to_remove:
            if progress_callback:
                progress_callback(75, "删除不合格词条...", f"将删除 {removed_count} 条词条")
            
            self._remove_all(to_remove, reasons, progress_callback)
        elif dry_run:
            logger.info("[KNOWLEDGE_VERIFIER] 干运行模式，不执行删除")
        
        # 7. 报告给Claw (90%-95%)
        removed_knowledge = [
            kp for kp in all_knowledge 
            if kp.get('knowledge_id', '') in to_remove
        ]
        
        optimization_data = {}
        if removed_knowledge:
            try:
                optimization_data = self.claw_optimizer.report_cleanup(removed_knowledge, reasons)
            except Exception as e:
                logger.error(f"[KNOWLEDGE_VERIFIER] Claw优化报告失败: {e}")
                optimization_data = {"error": str(e)}
        
        # 8. 返回结果 (100%)
        if progress_callback:
            progress_callback(100, "验证完成", f"原始: {total_count} → 最终: {total_count - removed_count}")
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "total_knowledge": total_count,
            "dedup_removed": len(duplicate_ids),
            "quality_removed": len(low_quality_ids),
            "removed_count": removed_count,
            "final_count": total_count - removed_count,
            "removed_ids": list(to_remove),
            "reasons": reasons,
            "optimization_data": optimization_data,
            "dry_run": dry_run
        }
        
        logger.info(f"[KNOWLEDGE_VERIFIER] 验证完成: 删除{removed_count}条")
        
        return result
    
    def verify_file(self, 
                  file_path: Path, 
                  dry_run: bool = False) -> Dict[str, Any]:
        """
        验证单个知识库文件
        
        Args:
            file_path: JSON文件路径
            dry_run: 干运行模式
        
        Returns:
            {
                "file_path": str,
                "original_count": 100,
                "removed_count": 10,
                "removed_ids": ["id1", "id2", ...],
                "reasons": {...}
            }
        """
        logger.info(f"[KNOWLEDGE_VERIFIER] 验证单个文件: {file_path}")
        
        # 读取文件
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"[KNOWLEDGE_VERIFIER] 读取文件失败: {e}")
            return {
                "file_path": str(file_path),
                "original_count": 0,
                "removed_count": 0,
                "removed_ids": [],
                "reasons": {},
                "error": str(e)
            }
        
        knowledge_points = data.get('knowledge_points', [])
        original_count = len(knowledge_points)
        
        # 查重
        duplicate_ids = self.dedup_engine._exact_match_dedup(knowledge_points)
        
        # 质量评估
        low_quality_ids = set()
        for kp in knowledge_points:
            score = self.quality_evaluator.evaluate_single(kp)
            if not score.passed:
                low_quality_ids.add(kp.get('knowledge_id', ''))
        
        # 合并
        to_remove = duplicate_ids | low_quality_ids
        
        # 构建原因
        reasons = {}
        for kp_id in duplicate_ids:
            reasons[kp_id] = "duplicate"
        for kp_id in low_quality_ids:
            if kp_id in reasons:
                reasons[kp_id] = "duplicate_and_low_quality"
            else:
                reasons[kp_id] = "low_quality"
        
        # 删除
        if not dry_run and to_remove:
            self.file_cleaner.remove_from_file(file_path, list(to_remove), dry_run=False)
        
        return {
            "file_path": str(file_path),
            "original_count": original_count,
            "removed_count": len(to_remove),
            "removed_ids": list(to_remove),
            "reasons": reasons,
            "dry_run": dry_run
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取知识库统计信息
        
        Returns:
            {
                "total_knowledge": 1130,
                "category_stats": {...},
                "timestamp": "..."
            }
        """
        all_knowledge = self._collect_all_knowledge()
        
        # 统计分类
        category_stats = {}
        for json_file in self.knowledge_dir.rglob("*.json"):
            category = json_file.stem
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    count = len(data.get('knowledge_points', []))
                    if count > 0:
                        category_stats[category] = count
            except Exception:
                pass
        
        return {
            "total_knowledge": len(all_knowledge),
            "category_stats": category_stats,
            "timestamp": datetime.now().isoformat()
        }
    
    def _collect_all_knowledge(self) -> List[Dict]:
        """
        收集所有知识点
        
        Returns:
            知识点列表
        """
        all_knowledge = []
        
        if not self.knowledge_dir.exists():
            logger.warning(f"[KNOWLEDGE_VERIFIER] 知识库目录不存在: {self.knowledge_dir}")
            return all_knowledge
        
        for json_file in self.knowledge_dir.rglob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    if 'knowledge_points' in data:
                        all_knowledge.extend(data['knowledge_points'])
            except Exception as e:
                logger.warning(f"[KNOWLEDGE_VERIFIER] 读取文件失败: {json_file}, {e}")
        
        return all_knowledge
    
    def _dedup_all(self, 
                   knowledge_list: List[Dict],
                   progress_callback: Optional[callable] = None) -> Set[str]:
        """
        执行所有查重策略
        
        Returns:
            重复词条ID集合
        """
        duplicate_ids = set()
        
        # 策略1: 完全匹配去重 (10%-20%)
        if progress_callback:
            progress_callback(15, "完全匹配去重...", "检测标题+关键词完全相同")
        
        exact_dups = self.dedup_engine._exact_match_dedup(knowledge_list)
        duplicate_ids.update(exact_dups)
        
        # 策略2: 语义相似度去重 (20%-30%)
        if progress_callback:
            progress_callback(25, "语义相似度去重...", "使用向量检索检测语义相似")
        
        semantic_groups = self.dedup_engine._semantic_similarity_dedup(knowledge_list)
        for group in semantic_groups:
            duplicate_ids.update(group.get('duplicate_ids', []))
        
        # 策略3: 内容重叠度去重 (30%-40%)
        if progress_callback:
            progress_callback(35, "内容重叠度去重...", "计算Jaccard相似度")
        
        overlap_groups = self.dedup_engine._content_overlap_dedup(knowledge_list)
        for group in overlap_groups:
            duplicate_ids.update(group.get('duplicate_ids', []))
        
        return duplicate_ids
    
    def _evaluate_all_quality(self, 
                           knowledge_list: List[Dict],
                           progress_callback: Optional[callable] = None) -> Set[str]:
        """
        评估所有知识点质量
        
        Returns:
            低质量词条ID集合
        """
        low_quality_ids = set()
        
        total = len(knowledge_list)
        for i, kp in enumerate(knowledge_list):
            score = self.quality_evaluator.evaluate_single(kp)
            
            # 判断是否应该自动删除
            if self.quality_evaluator.should_auto_delete(score):
                low_quality_ids.add(kp.get('knowledge_id', ''))
            
            # 进度更新 (45%-70%)
            if progress_callback and i % 50 == 0 and total > 0:
                percent = 50 + int((i / total) * 20)
                progress_callback(percent, "评估词条质量...", f"已评估: {i}/{total}")
        
        return low_quality_ids
    
    def _remove_all(self, 
                  knowledge_ids: Set[str],
                  reasons: Dict[str, str],
                  progress_callback: Optional[callable] = None) -> None:
        """
        删除所有指定词条
        
        Args:
            knowledge_ids: 要删除的词条ID集合
            reasons: 删除原因映射 {id: reason}
            progress_callback: 进度回调
        """
        # 按文件分组
        id_to_file = {}
        for json_file in self.knowledge_dir.rglob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    if 'knowledge_points' in data:
                        for kp in data['knowledge_points']:
                            kp_id = kp.get('knowledge_id', '')
                            if kp_id in knowledge_ids:
                                id_to_file[kp_id] = json_file
            except Exception as e:
                logger.warning(f"[KNOWLEDGE_VERIFIER] 读取文件失败: {json_file}, {e}")
        
        # 按文件删除
        file_to_ids = {}
        for kp_id, file_path in id_to_file.items():
            if file_path not in file_to_ids:
                file_to_ids[file_path] = set()
            file_to_ids[file_path].add(kp_id)
        
        # 执行删除
        total_removed = 0
        total_files = len(file_to_ids)
        
        for i, (file_path, ids) in enumerate(file_to_ids.items()):
            result = self.file_cleaner.remove_from_file(
                file_path, 
                list(ids), 
                dry_run=False
            )
            total_removed += result['removed_count']
            
            logger.info(f"[KNOWLEDGE_VERIFIER] 文件 {file_path.name}: 删除 {result['removed_count']} 条")
            
            # 进度更新 (70%-90%)
            if progress_callback and total_files > 0:
                percent = 75 + int((i / total_files) * 15)
                progress_callback(percent, "删除不合格词条...", f"已处理 {i+1}/{total_files} 文件")
        
        logger.info(f"[KNOWLEDGE_VERIFIER] 共删除 {total_removed} 条词条")
