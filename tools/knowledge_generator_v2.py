"""
高质量知识库生成器 V2.0
优化策略：并发请求 + 重试机制 + 断点续传 + 进度保存
"""

import json
import os
import sys
import time
import threading
from typing import List, Dict, Any, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from openai import OpenAI
import yaml
from core.api_key_encryption import APIKeyEncryption


class KnowledgeGeneratorV2:
    """高性能知识库生成器 - 并发优化版"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """初始化生成器"""
        # 读取配置
        config_file = project_root / config_path
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 获取API Key
        encryption = APIKeyEncryption(project_root)
        provider = config.get('provider', 'DeepSeek')
        self.api_key = encryption.get_api_key(provider)
        
        if not self.api_key:
            raise ValueError(f"Failed to decrypt API Key for {provider}")
        
        self.model = config.get('model', 'deepseek-chat')
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com",
            timeout=120.0  # 2分钟超时
        )
        
        # 并发控制
        self.max_workers = 3  # 最大并发数
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 2.0  # 重试延迟（秒）
        
        # 统计信息
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'retried': 0
        }
        self.stats_lock = threading.Lock()
        
        # 进度文件
        self.progress_file = project_root / "data" / "knowledge" / ".generation_progress.json"
        self.progress_lock = threading.Lock()
    
    def generate_single(self, topic_info: Dict, retry_count: int = 0) -> Optional[Dict]:
        """生成单个知识点（带重试）"""
        category = topic_info['category']
        domain = topic_info['domain']
        topic = topic_info['topic']
        
        prompt = self._build_prompt(category, domain, topic)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=3000,
                stream=False
            )
            
            content = response.choices[0].message.content
            
            # 提取JSON
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                knowledge = json.loads(json_str)
                
                # 验证必要字段
                required_fields = ['knowledge_id', 'title', 'detailed_content']
                if all(f in knowledge for f in required_fields):
                    with self.stats_lock:
                        self.stats['success'] += 1
                    return knowledge
            
            # JSON解析失败
            print(f"[WARN] JSON parse failed: {topic}")
            with self.stats_lock:
                self.stats['failed'] += 1
            return None
            
        except Exception as e:
            error_msg = str(e)
            
            # 判断是否需要重试
            should_retry = (
                retry_count < self.max_retries and
                ('timeout' in error_msg.lower() or 
                 'rate_limit' in error_msg.lower() or
                 '503' in error_msg or
                 '502' in error_msg)
            )
            
            if should_retry:
                # 指数退避
                delay = self.retry_delay * (2 ** retry_count)
                print(f"[RETRY {retry_count+1}/{self.max_retries}] {topic} - waiting {delay}s")
                time.sleep(delay)
                
                with self.stats_lock:
                    self.stats['retried'] += 1
                
                return self.generate_single(topic_info, retry_count + 1)
            else:
                print(f"[FAIL] {topic}: {error_msg[:100]}")
                with self.stats_lock:
                    self.stats['failed'] += 1
                return None
    
    def batch_generate(
        self, 
        topics: List[Dict], 
        output_file: Path,
        resume: bool = True
    ) -> List[Dict]:
        """批量生成知识点（并发优化）"""
        
        # 断点续传
        existing_ids = set()
        results = []
        
        if resume and output_file.exists():
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    results = existing_data if isinstance(existing_data, list) else []
                    existing_ids = {item['knowledge_id'] for item in results if 'knowledge_id' in item}
                print(f"[RESUME] Loaded {len(results)} existing items")
            except:
                pass
        
        # 过滤已完成
        pending = [t for t in topics if f"{t['category']}-{t['domain']}-{t['topic']}" not in existing_ids]
        
        if not pending:
            print("[DONE] All topics already completed")
            return results
        
        self.stats['total'] = len(pending)
        print(f"[START] Generating {len(pending)} knowledge points with {self.max_workers} workers...")
        
        # 并发生成
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任务
            future_to_topic = {
                executor.submit(self.generate_single, topic): topic 
                for topic in pending
            }
            
            # 收集结果
            for future in as_completed(future_to_topic):
                topic = future_to_topic[future]
                try:
                    knowledge = future.result()
                    if knowledge:
                        results.append(knowledge)
                        
                        # 每5个保存一次
                        if len(results) % 5 == 0:
                            self._save_progress(results, output_file)
                            print(f"[PROGRESS] {self.stats['success']}/{self.stats['total']} completed")
                except Exception as e:
                    print(f"[ERROR] {topic['topic']}: {e}")
        
        # 最终保存
        self._save_progress(results, output_file)
        
        # 打印统计
        print("\n" + "=" * 60)
        print("GENERATION COMPLETE")
        print("=" * 60)
        print(f"Total:      {self.stats['total']}")
        print(f"Success:    {self.stats['success']}")
        print(f"Failed:     {self.stats['failed']}")
        print(f"Retried:    {self.stats['retried']}")
        print(f"Success Rate: {self.stats['success']/self.stats['total']*100:.1f}%")
        print("=" * 60)
        
        return results
    
    def _build_prompt(self, category: str, domain: str, topic: str) -> str:
        """构建Prompt"""
        return f"""请生成一个高质量知识点，严格按照JSON格式输出。

**主题**: {topic}
**分类**: {category}/{domain}

**输出格式**:
```json
{{
  "knowledge_id": "{category}-{domain}-{topic}-001",
  "category": "{category}",
  "domain": "{domain}",
  "title": "{topic}",
  "content": "核心概念（1-2句话）",
  "detailed_content": "详细说明（300-500字）",
  "classic_cases": [
    {{"title": "案例1", "source": "来源", "content": "描述", "analysis": "分析"}}
  ],
  "writing_advice": {{
    "character_building": "角色塑造建议",
    "worldbuilding": "世界观建议",
    "plot_design": "情节设计建议"
  }},
  "common_mistakes": ["误区1", "误区2", "误区3"],
  "references": [
    {{"author": "作者", "year": "年份", "title": "标题"}}
  ],
  "related_concepts": ["概念1", "概念2", "概念3"]
}}
```

**质量要求**:
- detailed_content 必须详细（300字以上）
- classic_cases 至少2个案例
- common_mistakes 至少3个
- references 至少3个

直接输出JSON，不要其他内容。"""
    
    def _save_progress(self, results: List[Dict], output_file: Path):
        """保存进度"""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)


# 主题配置
TOPICS_CONFIG = {
    "scifi": {
        "physics": [
            "牛顿运动定律", "狭义相对论", "广义相对论", "量子力学基础", "量子纠缠",
            "电磁波谱", "核裂变与核聚变", "暗物质与暗能量", "黑洞物理学", "热力学定律",
            "超导现象", "弦理论入门", "量子场论", "熵与信息论", "时间膨胀效应"
        ],
        "biology": [
            "基因编辑技术", "克隆技术", "人体冷冻", "外星生物假想", "进化论前沿",
            "脑机接口", "合成生物学", "长寿基因研究", "生态圈模拟", "太空生物学"
        ],
        "space": [
            "星际旅行", "虫洞理论", "戴森球", "费米悖论", "宇宙大爆炸",
            "黑洞探索", "火星殖民", "小行星采矿", "太空电梯", "曲速引擎"
        ],
        "technology": [
            "人工智能觉醒", "量子计算机", "纳米机器人", "虚拟现实", "脑机接口",
            "反物质能源", "聚变反应堆", "太空电梯材料", "意识上传", "通用人工智能"
        ]
    },
    "xuanhuan": {
        "mythology": [
            "修真体系", "仙界架构", "天道法则", "因果轮回", "五行法则",
            "阴阳之道", "天劫雷罚", "元神修炼", "法宝炼制", "阵法之道"
        ],
        "religion": [
            "东方神系", "西方神系", "佛教体系", "道教体系", "神话起源",
            "信仰之力", "神格系统", "神域空间", "神魔之战", "创世神话"
        ]
    },
    "general": {
        "logic": [
            "三段论推理", "归纳与演绎", "逻辑谬误", "悖论分析", "因果关系",
            "概率思维", "博弈论基础", "决策树", "批判性思维", "认知偏差"
        ],
        "philosophy": [
            "存在主义", "功利主义", "道德困境", "自由意志", "意识本质",
            "时间哲学", "美学原理", "生死观", "东西方哲学差异", "虚无主义"
        ]
    }
}


def main():
    """主函数"""
    print("=" * 60)
    print("Knowledge Generator V2.0 - High Performance Edition")
    print("=" * 60)
    
    generator = KnowledgeGeneratorV2()
    
    all_results = []
    
    # 按分类生成
    for category, domains in TOPICS_CONFIG.items():
        for domain, topics in domains.items():
            print(f"\n{'='*60}")
            print(f"Processing: {category}/{domain} ({len(topics)} topics)")
            print(f"{'='*60}")
            
            topic_list = [
                {"category": category, "domain": domain, "topic": t}
                for t in topics
            ]
            
            output_file = project_root / "data" / "knowledge" / category / f"{domain}.json"
            
            results = generator.batch_generate(
                topics=topic_list,
                output_file=output_file,
                resume=True
            )
            
            all_results.extend(results)
            
            # 分类间休息
            time.sleep(2)
    
    print(f"\n[FINAL] Total {len(all_results)} knowledge points generated")
    print(f"Output directory: {project_root / 'data' / 'knowledge'}")


if __name__ == "__main__":
    main()
