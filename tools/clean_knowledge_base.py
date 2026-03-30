"""
知识库修复脚本
用于清理重复和错别字内容
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Set

class KnowledgeBaseCleaner:
    """知识库清理工具"""
    
    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = knowledge_dir
        # 常见错别字映射
        self.typo_map = {
            "借伐": "借代",
            "修词": "修辞",
            "修飾": "修辞",
            "修辭": "修辞",
            "排比与对偶": "排比、对偶",  # 修正标题格式
            "夸张与低调": "夸张、低调陈述",
        }
        
    def fix_typos(self, text: str) -> str:
        """修复常见错别字"""
        for typo, correct in self.typo_map.items():
            text = text.replace(typo, correct)
        return text
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（简单版本）"""
        # 使用Jaccard相似度
        set1 = set(text1.split())
        set2 = set(text2.split())
        intersection = set1 & set2
        union = set1 | set2
        return len(intersection) / len(union) if union else 0
    
    def deduplicate_knowledge_points(self, knowledge_points: List[Dict[str, Any]], similarity_threshold: float = 0.95) -> List[Dict[str, Any]]:
        """
        去重知识点
        
        Args:
            knowledge_points: 知识点列表
            similarity_threshold: 相似度阈值（0-1）
        
        Returns:
            去重后的知识点列表
        """
        unique_points = []
        seen_hashes: Set[str] = set()
        seen_titles: Set[str] = set()
        
        for kp in knowledge_points:
            # 修复错别字
            kp['title'] = self.fix_typos(kp['title'])
            kp['content'] = self.fix_typos(kp['content'])
            if 'description' in kp:
                kp['description'] = self.fix_typos(kp['description'])
            
            title = kp['title'].strip()
            content = kp['content']
            
            # 1. 标题去重（完全相同）
            if title in seen_titles:
                print(f"  标题重复，跳过: {title}")
                continue
            
            # 2. 内容去重（MD5哈希）
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            if content_hash in seen_hashes:
                print(f"  内容重复，跳过: {title}")
                continue
            
            # 3. 相似度去重
            is_similar = False
            for existing_kp in unique_points:
                similarity = self.calculate_similarity(content, existing_kp['content'])
                if similarity >= similarity_threshold:
                    print(f"  内容高度相似 ({similarity:.2%})，跳过: {title} (相似于 {existing_kp['title']})")
                    is_similar = True
                    break
            
            if is_similar:
                continue
            
            # 通过所有检查，添加到列表
            unique_points.append(kp)
            seen_titles.add(title)
            seen_hashes.add(content_hash)
        
        return unique_points
    
    def clean_json_file(self, json_file: Path) -> Dict[str, Any]:
        """
        清理单个JSON文件
        
        Args:
            json_file: JSON文件路径
        
        Returns:
            清理结果统计
        """
        print(f"\n{'='*60}")
        print(f"清理文件: {json_file.name}")
        print(f"{'='*60}")
        
        # 读取文件
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        original_count = len(data.get('knowledge_points', []))
        print(f"原始知识点数量: {original_count}")
        
        # 去重
        unique_points = self.deduplicate_knowledge_points(data.get('knowledge_points', []))
        
        # 更新数据
        data['knowledge_points'] = unique_points
        data['total'] = len(unique_points)
        
        # 保存回文件
        backup_file = json_file.with_suffix('.json.backup')
        if not backup_file.exists():
            import shutil
            shutil.copy(json_file, backup_file)
            print(f"已创建备份: {backup_file.name}")
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 统计
        removed_count = original_count - len(unique_points)
        print(f"清理后知识点数量: {len(unique_points)}")
        print(f"移除重复/错误数量: {removed_count}")
        print(f"{'='*60}\n")
        
        return {
            'file': json_file.name,
            'original_count': original_count,
            'final_count': len(unique_points),
            'removed_count': removed_count
        }
    
    def clean_all_writing_techniques(self):
        """清理所有写作技巧文件"""
        results = []
        
        # 写作技巧目录
        writing_technique_dir = self.knowledge_dir / 'writing_technique'
        
        # 清理所有JSON文件
        for json_file in writing_technique_dir.glob('*.json'):
            result = self.clean_json_file(json_file)
            results.append(result)
        
        # 打印汇总报告
        print(f"\n{'='*60}")
        print(f"清理汇总报告")
        print(f"{'='*60}")
        total_original = sum(r['original_count'] for r in results)
        total_final = sum(r['final_count'] for r in results)
        total_removed = sum(r['removed_count'] for r in results)
        
        print(f"原始总知识点数: {total_original}")
        print(f"清理后总知识点数: {total_final}")
        print(f"移除总数: {total_removed}")
        print(f"减少比例: {total_removed/total_original:.2%}")
        print(f"{'='*60}\n")
        
        return results


if __name__ == "__main__":
    # 知识库目录
    knowledge_dir = Path(r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge")
    
    # 创建清理器
    cleaner = KnowledgeBaseCleaner(knowledge_dir)
    
    # 清理所有写作技巧文件
    print("开始清理写作技巧知识库...")
    results = cleaner.clean_all_writing_techniques()
    
    print(f"\n清理完成！共处理 {len(results)} 个文件。")
