#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识点文件管理器 - 分条存储方案
实现一个知识点一个文件,避免误删

存储结构:
data/knowledge/
  ├── scifi/
  │   ├── physics/
  │   │   ├── scifi-physics-001.json  # 单条知识点
  │   │   ├── scifi-physics-002.json
  │   │   └── index.json              # 索引文件
  │   └── biology/
  ├── xuanhuan/
  │   └── mythology/
  │       ├── xuanhuan-mythology-001.json
  │       └── index.json
  └── writing_technique/
      ├── narrative/
      │   ├── writing_technique-narrative-001.json
      └── index.json

优点:
1. 删除单个知识点不影响其他知识点
2. 便于增量更新和版本控制
3. 降低文件损坏风险
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class KnowledgeFileManager:
    """知识点文件管理器"""
    
    def __init__(self, knowledge_dir: Path):
        """
        初始化文件管理器
        
        Args:
            knowledge_dir: 知识库根目录
        """
        self.knowledge_dir = knowledge_dir
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
    
    # ========================================================================
    # 写入操作
    # ========================================================================
    
    def save_knowledge_point(self, kp: Dict) -> Path:
        """
        保存单个知识点到独立文件
        
        Args:
            kp: 知识点字典,必须包含:
                - knowledge_id: 唯一标识(如"scifi-physics-001")
                - category: 分类(如"scifi")
                - domain: 领域(如"physics")
                - title: 标题
                - content: 内容
        
        Returns:
            保存的文件路径
        
        示例:
            kp = {
                "knowledge_id": "scifi-physics-001",
                "category": "scifi",
                "domain": "physics",
                "title": "黑洞",
                "content": "..."
            }
            file_path = manager.save_knowledge_point(kp)
            # 保存到: data/knowledge/scifi/physics/scifi-physics-001.json
        """
        # 提取必要字段
        kp_id = kp.get("knowledge_id")
        if not kp_id:
            raise ValueError("知识点缺少knowledge_id字段")
        
        category = kp.get("category", "general")
        domain = kp.get("domain", "general")
        
        # 构建保存路径
        category_dir = self.knowledge_dir / category / domain
        category_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = category_dir / f"{kp_id}.json"
        
        # 添加时间戳
        if "created_at" not in kp:
            kp["created_at"] = datetime.now().isoformat()
        kp["updated_at"] = datetime.now().isoformat()
        
        # 保存单个知识点
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(kp, f, ensure_ascii=False, indent=2)
        
        # 更新索引
        self._update_index(category, domain)
        
        logger.info(f"保存知识点: {file_path}")
        return file_path
    
    def save_knowledge_batch(self, knowledge_points: List[Dict], 
                            category: str, domain: str) -> List[Path]:
        """
        批量保存知识点
        
        Args:
            knowledge_points: 知识点列表
            category: 分类
            domain: 领域
        
        Returns:
            保存的文件路径列表
        """
        file_paths = []
        
        for kp in knowledge_points:
            # 确保包含category和domain
            kp["category"] = category
            kp["domain"] = domain
            
            # 生成knowledge_id(如果没有)
            if "knowledge_id" not in kp:
                kp["knowledge_id"] = self._generate_knowledge_id(category, domain)
            
            file_path = self.save_knowledge_point(kp)
            file_paths.append(file_path)
        
        return file_paths
    
    # ========================================================================
    # 读取操作
    # ========================================================================
    
    def load_knowledge_point(self, knowledge_id: str, 
                            category: Optional[str] = None, 
                            domain: Optional[str] = None) -> Optional[Dict]:
        """
        加载单个知识点
        
        Args:
            knowledge_id: 知识点ID
            category: 分类(可选,如果提供可加速查找)
            domain: 领域(可选)
        
        Returns:
            知识点字典或None
        """
        if category and domain:
            # 直接加载
            file_path = self.knowledge_dir / category / domain / f"{knowledge_id}.json"
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        else:
            # 遍历查找
            for json_file in self.knowledge_dir.glob("**/*.json"):
                if json_file.name == "index.json":
                    continue
                if json_file.stem == knowledge_id:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
        
        return None
    
    def load_knowledge_by_category(self, category: str, 
                                   domain: Optional[str] = None) -> List[Dict]:
        """
        加载指定分类的所有知识点
        
        Args:
            category: 分类(如"scifi")
            domain: 领域(可选,如"physics")
        
        Returns:
            知识点列表
        """
        knowledge_points = []
        
        if domain:
            # 加载指定领域
            domain_dir = self.knowledge_dir / category / domain
            if domain_dir.exists():
                for json_file in domain_dir.glob("*.json"):
                    if json_file.name == "index.json":
                        continue
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            knowledge_points.append(json.load(f))
                    except Exception as e:
                        logger.error(f"加载知识点失败: {json_file}, 错误: {e}")
        else:
            # 加载整个分类
            category_dir = self.knowledge_dir / category
            if category_dir.exists():
                for json_file in category_dir.glob("**/*.json"):
                    if json_file.name == "index.json":
                        continue
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            knowledge_points.append(json.load(f))
                    except Exception as e:
                        logger.error(f"加载知识点失败: {json_file}, 错误: {e}")
        
        return knowledge_points
    
    def load_all_knowledge(self) -> List[Dict]:
        """
        加载所有知识点
        
        Returns:
            所有知识点列表
        """
        knowledge_points = []
        
        for json_file in self.knowledge_dir.glob("**/*.json"):
            if json_file.name == "index.json":
                continue
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    knowledge_points.append(json.load(f))
            except Exception as e:
                logger.error(f"加载知识点失败: {json_file}, 错误: {e}")
        
        return knowledge_points
    
    # ========================================================================
    # 删除操作
    # ========================================================================
    
    def delete_knowledge_point(self, knowledge_id: str, 
                               category: Optional[str] = None, 
                               domain: Optional[str] = None) -> bool:
        """
        删除单个知识点(只删除对应文件,不影响其他知识点)
        
        Args:
            knowledge_id: 知识点ID
            category: 分类(可选)
            domain: 领域(可选)
        
        Returns:
            是否删除成功
        """
        # 查找文件
        if category and domain:
            file_path = self.knowledge_dir / category / domain / f"{knowledge_id}.json"
        else:
            # 遍历查找
            file_path = None
            for json_file in self.knowledge_dir.glob("**/*.json"):
                if json_file.name == "index.json":
                    continue
                if json_file.stem == knowledge_id:
                    file_path = json_file
                    break
        
        if not file_path or not file_path.exists():
            logger.warning(f"知识点不存在: {knowledge_id}")
            return False
        
        # 删除文件
        file_path.unlink()
        logger.info(f"删除知识点: {file_path}")
        
        # 更新索引
        if category and domain:
            self._update_index(category, domain)
        
        return True
    
    def delete_knowledge_batch(self, knowledge_ids: List[str]) -> Dict[str, bool]:
        """
        批量删除知识点
        
        Args:
            knowledge_ids: 知识点ID列表
        
        Returns:
            删除结果字典 {knowledge_id: success}
        """
        results = {}
        for kp_id in knowledge_ids:
            results[kp_id] = self.delete_knowledge_point(kp_id)
        return results
    
    # ========================================================================
    # 索引管理
    # ========================================================================
    
    def _update_index(self, category: str, domain: str):
        """
        更新索引文件
        
        Args:
            category: 分类
            domain: 领域
        """
        domain_dir = self.knowledge_dir / category / domain
        index_file = domain_dir / "index.json"
        
        # 收集所有知识点元数据
        index_data = {
            "category": category,
            "domain": domain,
            "updated_at": datetime.now().isoformat(),
            "knowledge_points": []
        }
        
        for json_file in sorted(domain_dir.glob("*.json")):
            if json_file.name == "index.json":
                continue
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    kp = json.load(f)
                
                index_data["knowledge_points"].append({
                    "knowledge_id": kp.get("knowledge_id"),
                    "title": kp.get("title"),
                    "difficulty": kp.get("difficulty"),
                    "created_at": kp.get("created_at"),
                    "updated_at": kp.get("updated_at")
                })
            except Exception as e:
                logger.error(f"读取知识点失败: {json_file}, 错误: {e}")
        
        index_data["count"] = len(index_data["knowledge_points"])
        
        # 保存索引
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    def get_index(self, category: str, domain: str) -> Optional[Dict]:
        """
        获取索引
        
        Args:
            category: 分类
            domain: 领域
        
        Returns:
            索引数据或None
        """
        index_file = self.knowledge_dir / category / domain / "index.json"
        
        if not index_file.exists():
            return None
        
        with open(index_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # ========================================================================
    # 迁移工具
    # ========================================================================
    
    def migrate_from_array_file(self, json_file: Path) -> List[Path]:
        """
        从数组格式JSON文件迁移到分条存储
        
        Args:
            json_file: 原JSON文件路径(包含知识点数组)
        
        Returns:
            保存的文件路径列表
        
        示例:
            # 原文件: data/knowledge/scifi_physics.json
            # 内容: [{"knowledge_id": "scifi-physics-001", ...}, ...]
            
            manager.migrate_from_array_file(Path("data/knowledge/scifi_physics.json"))
            # 迁移后:
            # data/knowledge/scifi/physics/scifi-physics-001.json
            # data/knowledge/scifi/physics/scifi-physics-002.json
            # ...
        """
        # 读取原文件
        with open(json_file, 'r', encoding='utf-8') as f:
            knowledge_points = json.load(f)
        
        # 兼容包装格式
        if isinstance(knowledge_points, dict):
            if "knowledge_points" in knowledge_points:
                knowledge_points = knowledge_points["knowledge_points"]
            else:
                # 单个知识点
                knowledge_points = [knowledge_points]
        
        # 确定分类和领域
        # 从文件名推断: scifi_physics.json -> category=scifi, domain=physics
        filename = json_file.stem
        if "_" in filename:
            parts = filename.split("_", 1)
            category = parts[0]
            domain = parts[1] if len(parts) > 1 else "general"
        else:
            category = filename
            domain = "general"
        
        # 批量保存
        file_paths = self.save_knowledge_batch(knowledge_points, category, domain)
        
        logger.info(f"迁移完成: {json_file} -> {len(file_paths)}个文件")
        
        return file_paths
    
    def migrate_all_from_directory(self, source_dir: Path):
        """
        迁移目录下所有JSON文件
        
        Args:
            source_dir: 源目录
        """
        for json_file in source_dir.glob("*.json"):
            # 跳过索引文件和临时文件
            if json_file.name in ["index.json", "knowledge_index.json"]:
                continue
            if json_file.name.startswith("."):
                continue
            
            try:
                self.migrate_from_array_file(json_file)
            except Exception as e:
                logger.error(f"迁移失败: {json_file}, 错误: {e}")
    
    # ========================================================================
    # 工具方法
    # ========================================================================
    
    def _generate_knowledge_id(self, category: str, domain: str) -> str:
        """
        生成知识点ID
        
        Args:
            category: 分类
            domain: 领域
        
        Returns:
            知识点ID(如"scifi-physics-001")
        """
        domain_dir = self.knowledge_dir / category / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        
        # 查找已有知识点数量
        existing_count = len(list(domain_dir.glob("*.json"))) - 1  # 减去index.json
        
        # 生成新ID
        return f"{category}-{domain}-{existing_count + 1:03d}"
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取知识库统计信息
        
        Returns:
            统计数据字典
        """
        stats = {
            "total_count": 0,
            "categories": {}
        }
        
        for category_dir in self.knowledge_dir.iterdir():
            if not category_dir.is_dir():
                continue
            
            category_stats = {
                "count": 0,
                "domains": {}
            }
            
            for domain_dir in category_dir.iterdir():
                if not domain_dir.is_dir():
                    continue
                
                # 统计知识点数量
                kp_count = len([f for f in domain_dir.glob("*.json") if f.name != "index.json"])
                
                category_stats["domains"][domain_dir.name] = kp_count
                category_stats["count"] += kp_count
            
            stats["categories"][category_dir.name] = category_stats
            stats["total_count"] += category_stats["count"]
        
        return stats


# ============================================================================
# 便捷函数
# ============================================================================

def get_knowledge_file_manager(workspace_root: Path) -> KnowledgeFileManager:
    """获取知识点文件管理器实例"""
    knowledge_dir = workspace_root / "data" / "knowledge"
    return KnowledgeFileManager(knowledge_dir)


if __name__ == "__main__":
    # 测试代码
    import sys
    
    workspace_root = Path(__file__).parent.parent
    manager = get_knowledge_file_manager(workspace_root)
    
    # 测试保存单个知识点
    test_kp = {
        "knowledge_id": "test-domain-001",
        "category": "test",
        "domain": "domain",
        "title": "测试知识点",
        "content": "这是一个测试知识点内容"
    }
    
    file_path = manager.save_knowledge_point(test_kp)
    print(f"保存成功: {file_path}")
    
    # 测试加载
    loaded_kp = manager.load_knowledge_point("test-domain-001", "test", "domain")
    print(f"加载成功: {loaded_kp['title']}")
    
    # 测试删除
    success = manager.delete_knowledge_point("test-domain-001", "test", "domain")
    print(f"删除成功: {success}")
    
    # 获取统计
    stats = manager.get_statistics()
    print(f"统计信息: {json.dumps(stats, ensure_ascii=False, indent=2)}")
