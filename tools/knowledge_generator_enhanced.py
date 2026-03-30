# -*- coding: utf-8 -*-
"""
知识库生成器 - 增强版
修复问题：
1. 重复检测：标题完全重复或SimHash相似度过高
2. 错别字修复：自动修复常见错别字
"""

import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime


class KnowledgeGeneratorEnhanced:
    """增强版知识库生成器"""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.knowledge_base_dir = workspace_root / "data" / "knowledge"
        
        # 错别字映射表
        self.typo_map = {
            # 常见错别字修正
            "借伐": "借代",
            "排比于对偶": "排比与对偶",
            "修辞手伐": "修辞手法",
            "叙事技巧伐": "叙事技巧法",
            "描写技巧伐": "描写技巧法",
            "修辞技巧伐": "修辞技巧法",
            "结构技巧伐": "结构技巧法",
            "特殊句式伐": "特殊句式法",
            "高级技法伐": "高级技法法",
        }
        
        # 去重缓存
        self.existing_titles = set()
        self.existing_simscores = {}  # 存储标题的SimHash值
        
    def load_existing_knowledge(self, category: str, domain: str) -> List[str]:
        """加载已存在的知识点标题（用于去重）"""
        knowledge_file = self.knowledge_base_dir / category / f"{domain}.json"
        
        if not knowledge_file.exists():
            return []
        
        try:
            with open(knowledge_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                if isinstance(data, dict):
                    knowledge_points = data.get("knowledge_points", [])
                elif isinstance(data, list):
                    knowledge_points = data
                else:
                    return []
                
                # 提取所有标题
                titles = [kp.get("title", "") for kp in knowledge_points]
                return titles
                
        except Exception as e:
            print(f"⚠️ 加载现有知识点失败: {e}")
            return []
    
    def calculate_simhash(self, text: str) -> str:
        """计算SimHash（用于检测重复内容）"""
        if not text:
            return ""
        
        # 简化版SimHash实现
        text = text.lower().strip()
        text = ''.join(c for c in text if c.isalnum() or c in '，。、！？；：""''')
        
        if not text:
            return ""
        
        # 计算哈希值
        hash_obj = hashlib.md5(text.encode('utf-8'))
        return hash_obj.hexdigest()
    
    def check_duplicate(self, title: str, content: str, existing_titles: set) -> Dict[str, Any]:
        """检查重复（标题完全重复或内容相似）"""
        # 1. 检查标题完全重复
        if title in existing_titles:
            return {
                "is_duplicate": True,
                "duplicate_type": "title",
                "reason": f"标题完全重复: {title}"
            }
        
        # 2. 检查标题是否已被替换为错别字（如"借伐" vs "借代"）
        normalized_title = self.normalize_typo(title)
        for existing_title in existing_titles:
            if normalized_title == self.normalize_typo(existing_title):
                return {
                    "is_duplicate": True,
                    "duplicate_type": "typo_duplicate",
                    "reason": f"标题可能重复（错别字修正）: {title} ≈ {existing_title}"
                }
        
        # 3. 检查内容SimHash相似度过高（阈值：相同哈希或相似）
        simhash = self.calculate_simhash(content[:500])  # 只取前500字符计算
        
        for existing_title, existing_hash in self.existing_simscores.items():
            if simhash == existing_hash:
                return {
                    "is_duplicate": True,
                    "duplicate_type": "content_similarity",
                    "reason": f"内容高度相似（SimHash相同）: {title} ≈ {existing_title}"
                }
        
        # 缓存SimHash
        self.existing_simscores[title] = simhash
        
        return {
            "is_duplicate": False,
            "duplicate_type": None,
            "reason": "通过验证"
        }
    
    def normalize_typo(self, text: str) -> str:
        """修正文本中的错别字"""
        result = text
        for typo, correct in self.typo_map.items():
            result = result.replace(typo, correct)
        return result
    
    def fix_knowledge_point(self, kp: Dict[str, Any]) -> Dict[str, Any]:
        """修复单个知识点（修正错别字）"""
        fixed_kp = kp.copy()
        
        # 1. 修正标题中的错别字
        fixed_kp["title"] = self.normalize_typo(kp.get("title", ""))
        
        # 2. 修正内容中的错别字
        fixed_kp["content"] = self.normalize_typo(kp.get("content", ""))
        
        # 3. 修正关键词中的错别字
        keywords = kp.get("keywords", [])
        if keywords:
            fixed_kp["keywords"] = [self.normalize_typo(kw) for kw in keywords]
        
        # 4. 修正核心概念解释中的错别字
        if "explanation" in fixed_kp:
            fixed_kp["explanation"] = self.normalize_typo(fixed_kp["explanation"])
        
        # 5. 修正经典案例中的错别字
        if "classic_cases" in fixed_kp:
            fixed_kp["classic_cases"] = self.normalize_typo(fixed_kp["classic_cases"])
        
        # 6. 修正常见误区中的错别字
        common_mistakes = kp.get("common_mistakes", [])
        if isinstance(common_mistakes, list):
            fixed_kp["common_mistakes"] = [self.normalize_typo(m) for m in common_mistakes]
        elif isinstance(common_mistakes, str):
            fixed_kp["common_mistakes"] = self.normalize_typo(common_mistakes)
        
        return fixed_kp
    
    def generate_writing_techniques(self, category: str = "writing_technique", domains: List[str] = None) -> Dict[str, Any]:
        """
        生成写作技巧知识库（带去重和错别字修复）
        
        Args:
            category: 分类（writing_technique）
            domains: 领域列表（narrative, description, rhetoric, structure, special_sentence, advanced）
        
        Returns:
            Dict: 生成结果统计
        """
        if domains is None:
            domains = ["narrative", "description", "rhetoric", "structure", "special_sentence", "advanced"]
        
        # 创建分类目录
        category_dir = self.knowledge_base_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成统计
        stats = {
            "category": category,
            "total_generated": 0,
            "total_duplicate": 0,
            "total_typo_fixed": 0,
            "domains": {}
        }
        
        # 遍历每个领域
        for domain in domains:
            print(f"\n{'='*60}")
            print(f"生成领域: {domain}")
            print(f"{'='*60}")
            
            # 加载已存在的知识点（用于去重）
            existing_titles = self.load_existing_knowledge(category, domain)
            self.existing_titles = set(existing_titles)
            self.existing_simscores = {}
            
            # 检查是否已存在SimHash
            for title in existing_titles:
                # 这里假设内容文件名与标题一致，实际需要从文件读取内容
                self.existing_simscores[title] = self.calculate_simhash(title)
            
            # 生成该领域的知识点（这里需要实际调用AI生成逻辑）
            # 示例：模拟生成
            new_knowledge_points = self._generate_mock_knowledge(domain)
            
            # 去重和修复
            unique_points = []
            domain_stats = {
                "domain": domain,
                "generated": len(new_knowledge_points),
                "duplicate_removed": 0,
                "typo_fixed": 0,
                "final_count": 0
            }
            
            for kp in new_knowledge_points:
                title = kp.get("title", "")
                content = kp.get("content", "")
                
                # 1. 检查重复
                dup_result = self.check_duplicate(title, content, self.existing_titles)
                
                if dup_result["is_duplicate"]:
                    domain_stats["duplicate_removed"] += 1
                    print(f"  ❌ 跳过重复: {title} ({dup_result['reason']})")
                    continue
                
                # 2. 修复错别字
                original_title = title
                original_content = content
                fixed_kp = self.fix_knowledge_point(kp)
                
                # 检查是否有错别字被修复
                title_fixed = fixed_kp["title"] != original_title
                content_fixed = fixed_kp["content"] != original_content
                
                if title_fixed or content_fixed:
                    domain_stats["typo_fixed"] += 1
                    if title_fixed:
                        print(f"  ✏️ 修正标题错别字: {original_title} → {fixed_kp['title']}")
                    if content_fixed and original_content != content[:50]:
                        print(f"  ✏️ 修正内容错别字: {domain}")
                
                # 3. 添加到唯一列表
                unique_points.append(fixed_kp)
                self.existing_titles.add(fixed_kp["title"])
                domain_stats["final_count"] += 1
            
            # 保存该领域的知识点
            if unique_points:
                domain_file = category_dir / f"{domain}.json"
                
                # 合并已有知识点
                existing_data = []
                if domain_file.exists():
                    with open(domain_file, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if isinstance(existing_data, dict):
                            existing_points = existing_data.get("knowledge_points", [])
                        else:
                            existing_points = existing_data
                else:
                    existing_points = []
                
                # 更新数据
                updated_data = {
                    "knowledge_points": existing_points + unique_points,
                    "updated_at": datetime.now().isoformat(),
                    "domain": domain,
                    "category": category
                }
                
                # 保存文件
                with open(domain_file, 'w', encoding='utf-8') as f:
                    json.dump(updated_data, f, ensure_ascii=False, indent=2)
                
                print(f"  ✅ 保存 {len(unique_points)} 个知识点到 {domain_file.name}")
            
            # 统计该领域结果
            stats["domains"][domain] = domain_stats
            stats["total_generated"] += domain_stats["generated"]
            stats["total_duplicate"] += domain_stats["duplicate_removed"]
            stats["total_typo_fixed"] += domain_stats["typo_fixed"]
            
            print(f"\n  📊 领域统计: {domain_stats}")
        
        return stats
    
    def _generate_mock_knowledge(self, domain: str) -> List[Dict[str, Any]]:
        """模拟生成知识点（实际需要调用AI生成逻辑）"""
        # 这里只是示例，实际应该调用AI生成
        mock_data = []
        
        # 根据领域生成示例数据
        domain_samples = {
            "rhetoric": [
                {"title": "排比与对偶", "content": "排比和借代是常用的修辞手法。", "keywords": ["排比", "借代", "修辞"]},
                {"title": "比喻与象征", "content": "比喻和象征可以增强文学表现力。", "keywords": ["比喻", "象征", "修辞"]},
                {"title": "借伐", "content": "借伐是借代的错别字。", "keywords": ["借伐", "错别字"]},
            ],
            "narrative": [
                {"title": "第一人称叙事", "content": "第一人称叙事可以增强代入感。", "keywords": ["第一人称", "叙事", "视角"]},
                {"title": "第三人称叙事", "content": "第三人称叙事提供更客观的视角。", "keywords": ["第三人称", "叙事", "视角"]},
            ],
            "description": [
                {"title": "人物描写", "content": "人物描写要抓住特征。", "keywords": ["人物", "描写", "特征"]},
                {"title": "环境描写", "content": "环境描写可以烘托氛围。", "keywords": ["环境", "描写", "氛围"]},
            ],
            "structure": [
                {"title": "开头技巧", "content": "开头要吸引读者。", "keywords": ["开头", "技巧", "吸引"]},
                {"title": "结尾技巧", "content": "结尾要给人回味。", "keywords": ["结尾", "技巧", "回味"]},
            ],
            "special_sentence": [
                {"title": "倒装句", "content": "倒装句可以强调某个成分。", "keywords": ["倒装", "句式", "强调"]},
                {"title": "排比句", "content": "排比句可以增强气势。", "keywords": ["排比", "句式", "气势"]},
            ],
            "advanced": [
                {"title": "复调叙事", "content": "复调叙事可以让多个声音并存。", "keywords": ["复调", "叙事", "多声音"]},
                {"title": "意识流", "content": "意识流可以展现内心活动。", "keywords": ["意识流", "内心", "心理"]},
            ]
        }
        
        return domain_samples.get(domain, [])


def main():
    """主函数"""
    workspace_root = Path(__file__).parent.parent
    
    print("="*60)
    print("知识库生成器 - 增强版")
    print("="*60)
    print(f"工作区: {workspace_root}")
    print(f"知识库目录: {workspace_root / 'data' / 'knowledge'}")
    print()
    
    generator = KnowledgeGeneratorEnhanced(workspace_root)
    
    # 生成写作技巧知识库
    domains = ["rhetoric", "narrative", "description", "structure", "special_sentence", "advanced"]
    
    print("开始生成写作技巧知识库...")
    stats = generator.generate_writing_techniques(
        category="writing_technique",
        domains=domains
    )
    
    # 打印总体统计
    print("\n" + "="*60)
    print("总体统计")
    print("="*60)
    print(f"  总生成数: {stats['total_generated']}")
    print(f"  去重数量: {stats['total_duplicate']}")
    print(f"  错别字修复数: {stats['total_typo_fixed']}")
    print(f"  最终保留数: {stats['total_generated'] - stats['total_duplicate']}")
    print()
    
    # 打印各领域统计
    print("各领域统计:")
    for domain, domain_stats in stats["domains"].items():
        print(f"  {domain}:")
        print(f"    生成: {domain_stats['generated']}")
        print(f"    去重: {domain_stats['duplicate_removed']}")
        print(f"    修复: {domain_stats['typo_fixed']}")
        print(f"    最终: {domain_stats['final_count']}")
    
    print("\n✅ 生成完成！")


if __name__ == "__main__":
    main()
