"""
知识库质量验证与去重工具
解决同批次生成中的重复和错别字问题
"""

import json
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Tuple


class KnowledgeValidator:
    """知识库质量验证器"""
    
    def __init__(self, knowledge_base_dir: str):
        self.knowledge_base_dir = Path(knowledge_base_dir)
        self.issues = []
        
    def validate_and_deduplicate(self, category: str, domain: str) -> List[Dict]:
        """
        验证并去重知识点
        
        Args:
            category: 分类（如 scifi, fantasy）
            domain: 领域（如 rhetoric, structure）
            
        Returns:
            去重后的知识点列表
        """
        json_file = self.knowledge_base_dir / category / f"{domain}.json"
        
        if not json_file.exists():
            return []
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        knowledge_points = data.get("knowledge_points", [])
        
        # 1. 标题去重（完全相同）
        seen_titles = set()
        unique_points = []
        
        for kp in knowledge_points:
            title = kp.get("title", "").strip()
            
            if title in seen_titles:
                self.issues.append({
                    "type": "duplicate_title",
                    "title": title,
                    "category": category,
                    "domain": domain
                })
                continue
            
            seen_titles.add(title)
            unique_points.append(kp)
        
        # 2. SimHash去重（内容相似）
        unique_points = self._deduplicate_by_simhash(unique_points)
        
        # 3. 错别字检查和修复
        unique_points = self._fix_typos(unique_points)
        
        # 保存去重后的数据
        data["knowledge_points"] = unique_points
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 打印报告
        print(f"\n{category}/{domain} 验证结果：")
        print(f"  原始数量：{len(knowledge_points)}")
        print(f"  去重后：{len(unique_points)}")
        print(f"  去除重复：{len(knowledge_points) - len(unique_points)}")
        print(f"  修复错别字：{self._typo_count}")
        
        return unique_points
    
    def _deduplicate_by_simhash(self, knowledge_points: List[Dict]) -> List[Dict]:
        """
        使用SimHash进行内容去重
        
        Args:
            knowledge_points: 知识点列表
            
        Returns:
            去重后的知识点列表
        """
        unique_points = []
        seen_simhash = {}
        
        for kp in knowledge_points:
            content = kp.get("content", "")
            title = kp.get("title", "")
            
            # 计算SimHash
            simhash = self._calculate_simhash(content)
            
            # 检查是否相似（海明距离<=3）
            is_duplicate = False
            for seen_hash, seen_kp in seen_simhash.items():
                if self._hamming_distance(simhash, seen_hash) <= 3:
                    self.issues.append({
                        "type": "simhash_duplicate",
                        "title": title,
                        "similar_to": seen_kp.get("title", ""),
                        "category": kp.get("category", ""),
                        "domain": kp.get("domain", "")
                    })
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_points.append(kp)
                seen_simhash[simhash] = kp
        
        return unique_points
    
    def _calculate_simhash(self, text: str, hash_bits: int = 64) -> int:
        """
        计算SimHash（简化的哈希算法）
        
        Args:
            text: 输入文本
            hash_bits: 哈希位数（64位）
            
        Returns:
            SimHash值
        """
        if not text:
            return 0
        
        # 中文分词（简单按字符分割）
        tokens = [c for c in text if c.strip()]
        
        if not tokens:
            return 0
        
        # 计算每个字符的哈希
        v = [0] * hash_bits
        for token in tokens:
            token_hash = hashlib.md5(token.encode('utf-8')).digest()
            token_hash_int = int.from_bytes(token_hash[:8], 'big')
            
            # 更新向量
            for i in range(hash_bits):
                bitmask = 1 << (hash_bits - 1 - i)
                if token_hash_int & bitmask:
                    v[i] += 1
                else:
                    v[i] -= 1
        
        # 生成最终哈希
        simhash = 0
        for i in range(hash_bits):
            if v[i] >= 0:
                simhash |= (1 << (hash_bits - 1 - i))
        
        return simhash
    
    def _hamming_distance(self, x: int, y: int) -> int:
        """
        计算海明距离（SimHash相似度）
        
        Args:
            x, y: SimHash值
            
        Returns:
            海明距离（越小越相似）
        """
        return bin(x ^ y).count('1')
    
    def _fix_typos(self, knowledge_points: List[Dict]) -> List[Dict]:
        """
        修复常见错别字
        
        Args:
            knowledge_points: 知识点列表
            
        Returns:
            修复后的知识点列表
        """
        self._typo_count = 0
        
        # 常见错别字映射
        typo_map = {
            "借伐": "借代",
            "排比与对偶": "排比",  # 简化
            "排比、对偶": "排比",  # 逗号分隔的简化
            "修辞技巧：排比与对偶": "排比",
        }
        
        for kp in knowledge_points:
            # 检查标题
            title = kp.get("title", "")
            for typo, correct in typo_map.items():
                if typo in title:
                    title = title.replace(typo, correct)
                    kp["title"] = title
                    self._typo_count += 1
                    self.issues.append({
                        "type": "typo",
                        "typo": typo,
                        "correct": correct,
                        "title": title,
                        "category": kp.get("category", ""),
                        "domain": kp.get("domain", "")
                    })
            
            # 检查内容
            content = kp.get("content", "")
            for typo, correct in typo_map.items():
                if typo in content:
                    content = content.replace(typo, correct)
                    kp["content"] = content
                    self._typo_count += 1
        
        return knowledge_points
    
    def validate_all(self) -> Dict[str, List[Dict]]:
        """
        验证所有分类和领域
        
        Returns:
            验证结果字典
        """
        results = {}
        self.issues = []
        self._typo_count = 0
        
        # 遍历所有分类
        for category_dir in self.knowledge_base_dir.iterdir():
            if not category_dir.is_dir():
                continue
            
            category = category_dir.name
            
            # 跳过特殊目录
            if category in ["domains", "writing_technique", "philosophy"]:
                continue
            
            # 遍历所有领域
            for json_file in category_dir.glob("*.json"):
                domain = json_file.stem
                
                if domain == "index":
                    continue
                
                # 验证并去重
                unique_points = self.validate_and_deduplicate(category, domain)
                
                if category not in results:
                    results[category] = []
                
                results[category].extend(unique_points)
        
        # 打印总报告
        print("\n" + "="*60)
        print("知识库验证总报告")
        print("="*60)
        print(f"  总问题数：{len(self.issues)}")
        print(f"  标题重复：{len([i for i in self.issues if i['type'] == 'duplicate_title'])}")
        print(f"  SimHash重复：{len([i for i in self.issues if i['type'] == 'simhash_duplicate'])}")
        print(f"  错别字修复：{self._typo_count}")
        print("="*60)
        
        # 保存问题报告
        report_file = self.knowledge_base_dir / "validation_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.issues, f, ensure_ascii=False, indent=2)
        
        print(f"\n问题报告已保存到：{report_file}")
        
        return results


def main():
    """主函数"""
    # 设置知识库目录
    workspace_root = Path(__file__).parent.parent
    knowledge_base_dir = workspace_root / "data" / "knowledge"
    
    # 创建验证器
    validator = KnowledgeValidator(knowledge_base_dir)
    
    # 执行验证
    validator.validate_all()
    
    print("\n验证完成！")


if __name__ == "__main__":
    main()
