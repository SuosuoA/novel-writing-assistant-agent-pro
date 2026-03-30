#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识库批量生成工具 - V1.0
创建日期: 2026-03-28

用途:
- 批量生成科幻、玄幻、通用知识库知识点
- 支持DeepSeek API调用
- 自动保存到JSON文件
- 质量验证和去重

使用方法:
    python tools/knowledge_generator_batch.py --category scifi --count 559
    python tools/knowledge_generator_batch.py --category xuanhuan --count 334
    python tools/knowledge_generator_batch.py --category general --count 237
"""

import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pydantic import BaseModel, Field, ConfigDict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

class KnowledgePoint(BaseModel):
    """知识点数据模型"""
    model_config = ConfigDict(frozen=False)
    
    knowledge_id: str = Field(..., description="知识点ID")
    category: str = Field(..., description="分类(scifi/xuanhuan/general/history)")
    domain: str = Field(..., description="领域(如physics/biology/magic)")
    title: str = Field(..., description="知识点标题")
    content: str = Field(..., description="知识点内容(200-500字)")
    keywords: List[str] = Field(default_factory=list, description="关键词(3-10个)")
    references: List[str] = Field(default_factory=list, description="参考文学作品")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    def validate_content(self) -> bool:
        """验证内容质量"""
        if len(self.content) < 100 or len(self.content) > 1000:
            return False
        if len(self.keywords) < 3 or len(self.keywords) > 15:
            return False
        return True


# ============================================================================
# AI服务管理器
# ============================================================================

class AIGenerator:
    """AI生成器 - 使用DeepSeek API"""
    
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = "https://api.deepseek.com"
        self.model = "deepseek-chat"
        
        # 从config.yaml加载配置
        self._load_config()
    
    def _load_config(self):
        """从config.yaml加载配置"""
        try:
            import yaml
            config_path = project_root / "config.yaml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                
                # 尝试从加密存储获取API Key
                if config.get("api_key") == "ENCRYPTED_IN_SECRETS_FILE":
                    try:
                        from core.api_key_encryption import get_api_key_encryption
                        encryption = get_api_key_encryption(project_root)
                        self.api_key = encryption.get_api_key("DeepSeek") or ""
                        logger.info("[AI] 从加密存储加载API Key成功")
                    except Exception as e:
                        logger.warning(f"[AI] 加密存储读取失败: {e}")
                        # 降级：从环境变量读取
                        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
                else:
                    self.api_key = config.get("api_key", self.api_key)
                
                # 读取base_url
                if "deepseek" in config and isinstance(config["deepseek"], dict):
                    self.base_url = config["deepseek"].get("base_url", self.base_url)
                
                logger.info(f"[AI] 配置加载成功: base_url={self.base_url}")
        except Exception as e:
            logger.warning(f"[AI] 配置加载失败: {e}")
    
    def generate_batch(self, prompt: str, count: int = 10) -> List[Dict]:
        """批量生成知识点"""
        try:
            from openai import OpenAI
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=f"{self.base_url}/v1"
            )
            
            logger.info(f"[AI] 开始生成 {count} 个知识点...")
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业的小说创作知识库构建专家。你生成的知识点应该适合小说创作参考,避免过于学术化。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=8000
            )
            
            content = response.choices[0].message.content
            
            # 解析JSON
            # 尝试提取JSON数组
            import re
            json_match = re.search(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                knowledge_points = json.loads(json_str)
                logger.info(f"[AI] 成功解析 {len(knowledge_points)} 个知识点")
                return knowledge_points
            else:
                logger.warning("[AI] 未找到JSON数组,尝试直接解析")
                return []
            
        except Exception as e:
            logger.error(f"[AI] 生成失败: {e}")
            return []
    
    def generate_knowledge_points(
        self,
        category: str,
        domain: str,
        count: int = 10,
        existing_titles: List[str] = None
    ) -> List[KnowledgePoint]:
        """生成知识点"""
        
        # 智能推荐子方向（避免重复）
        sub_directions = self._recommend_sub_directions(category, domain, existing_titles or [])
        sub_direction_hint = "\n".join([f"- {d}" for d in sub_directions[:5]])
        
        prompt = f"""
生成{count}个{category}小说创作所需的{domain}知识点。

**重要要求**:
1. 每个知识点包含: title(标题), content(内容200-400字), keywords(关键词5-8个), references(参考作品3个)
2. 知识点应适合小说创作参考,避免过于学术化
3. 覆盖{domain}的基础概念、常见误解、经典应用场景
4. 内容要有具体细节,能为创作提供灵感
5. 标题要简洁明了,一眼就能看出知识点主题

**推荐的新生成方向**（优先覆盖这些子领域）:
{sub_direction_hint}

**已存在的知识点标题**（避免重复）:
{chr(10).join([f"- {title}" for title in (existing_titles or [])[:30]])}

**输出格式(JSON数组)**:
[
  {{
    "title": "知识点标题",
    "content": "知识点详细内容(200-400字)",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
    "references": ["参考作品1", "参考作品2", "参考作品3"]
  }},
  ...
]

请生成{count}个知识点:
"""
        
        results = self.generate_batch(prompt, count)
        
        knowledge_points = []
        for i, item in enumerate(results):
            try:
                kp = KnowledgePoint(
                    knowledge_id=f"{category}-{domain}-{str(uuid.uuid4())[:8]}",
                    category=category,
                    domain=domain,
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    keywords=item.get("keywords", []),
                    references=item.get("references", [])
                )
                
                if kp.validate_content():
                    knowledge_points.append(kp)
                else:
                    logger.warning(f"[验证] 知识点质量不达标: {kp.title}")
            except Exception as e:
                logger.error(f"[解析] 知识点解析失败: {e}")
        
        logger.info(f"[生成] 成功生成 {len(knowledge_points)} 个知识点")
        return knowledge_points
    
    def _recommend_sub_directions(self, category: str, domain: str, existing_titles: List[str]) -> List[str]:
        """智能推荐子方向"""
        # 预定义常见子方向
        sub_directions_map = {
            "physics": ["力学", "光学", "声学", "热学", "电磁学", "天文学", "材料", "量子力学", "相对论"],
            "biology": ["基因工程", "进化论", "生态系统", "微生物", "植物学", "动物行为", "生物化学"],
            "space": ["星系", "行星", "恒星", "黑洞", "虫洞", "宇宙膨胀", "暗物质"],
            "technology": ["人工智能", "机器人", "纳米技术", "能源", "交通", "通信", "医疗技术"],
            "magic": ["元素魔法", "召唤术", "炼金术", "符文", "结界", "幻术", "治愈术"],
            "cultivation": ["功法", "丹药", "法宝", "阵法", "灵兽", "境界", "渡劫"],
            "worldview": ["种族", "势力", "地理", "历史", "宗教", "政治", "经济"],
            "writing": ["叙事技巧", "人物塑造", "情节设计", "对话", "描写", "节奏", "视角"]
        }
        
        all_directions = sub_directions_map.get(domain, [])
        
        # 分析已存在的子方向
        covered = set()
        for title in existing_titles:
            for direction in all_directions:
                if direction in title:
                    covered.add(direction)
        
        # 推荐未覆盖的子方向
        uncovered = [d for d in all_directions if d not in covered]
        
        return uncovered if uncovered else all_directions


# ============================================================================
# 知识库管理器
# ============================================================================

class KnowledgeBaseManager:
    """知识库管理器"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.data_dir = workspace / "data" / "knowledge"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.ai_generator = AIGenerator()
        
        # 目标数量配置
        self.targets = {
            "scifi": {
                "physics": 209,
                "biology": 150,
                "space": 100,
                "technology": 100
            },
            "xuanhuan": {
                "magic": 150,
                "cultivation": 100,
                "worldview": 84
            },
            "general": {
                "writing": 150,
                "plot": 87
            }
        }
    
    def generate_category(self, category: str, total_count: Optional[int] = None):
        """生成某个分类的知识库"""
        logger.info(f"\n{'='*60}")
        logger.info(f"开始生成 {category} 知识库")
        logger.info(f"{'='*60}")
        
        if category not in self.targets:
            logger.error(f"未知分类: {category}")
            return
        
        domains = self.targets[category]
        
        for domain, target_count in domains.items():
            if total_count is not None:
                target_count = min(target_count, total_count)
                total_count = max(0, total_count - target_count)
            
            logger.info(f"\n[Domain] {domain} - 目标: {target_count}条")
            
            # 加载已存在的知识点
            existing = self._load_existing_knowledge(category, domain)
            existing_count = len(existing)
            existing_titles = [kp.get("title", "") for kp in existing]
            
            logger.info(f"[存在] 已有 {existing_count} 条知识点")
            
            # 计算需要生成的数量
            need_count = max(0, target_count - existing_count)
            
            if need_count == 0:
                logger.info(f"[完成] {domain} 已达到目标数量")
                continue
            
            # 批量生成（每批最多20条）
            batch_size = 20
            generated_total = []
            
            for batch in range(0, need_count, batch_size):
                current_batch_size = min(batch_size, need_count - len(generated_total))
                
                logger.info(f"\n[Batch {batch//batch_size + 1}] 生成 {current_batch_size} 条...")
                
                knowledge_points = self.ai_generator.generate_knowledge_points(
                    category=category,
                    domain=domain,
                    count=current_batch_size,
                    existing_titles=existing_titles + [kp.title for kp in generated_total]
                )
                
                generated_total.extend(knowledge_points)
                
                # 每生成一批就保存
                if knowledge_points:
                    self._save_knowledge_batch(category, domain, knowledge_points)
                
                # 避免API限流
                time.sleep(2)
            
            logger.info(f"\n[统计] {domain} 共生成 {len(generated_total)} 条知识点")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"{category} 知识库生成完成")
        logger.info(f"{'='*60}\n")
    
    def _load_existing_knowledge(self, category: str, domain: str) -> List[Dict]:
        """加载已存在的知识点"""
        file_path = self.data_dir / category / f"{domain}.json"
        
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("knowledge_points", [])
        except Exception as e:
            logger.error(f"[加载] 读取失败: {e}")
            return []
    
    def _save_knowledge_batch(self, category: str, domain: str, knowledge_points: List[KnowledgePoint]):
        """保存知识点到JSON文件"""
        file_path = self.data_dir / category / f"{domain}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载已存在的知识点
        existing = self._load_existing_knowledge(category, domain)
        
        # 添加新知识点
        existing.extend([kp.model_dump() for kp in knowledge_points])
        
        # 保存
        data = {
            "category": category,
            "domain": domain,
            "total_count": len(existing),
            "updated_at": datetime.now().isoformat(),
            "knowledge_points": existing
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[保存] {file_path} - {len(knowledge_points)} 条新知识点")
    
    def get_statistics(self) -> Dict:
        """获取知识库统计信息"""
        stats = {"total": 0, "categories": {}}
        
        for category in self.targets.keys():
            category_dir = self.data_dir / category
            if not category_dir.exists():
                stats["categories"][category] = 0
                continue
            
            count = 0
            for json_file in category_dir.glob("*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        count += len(data.get("knowledge_points", []))
                except:
                    pass
            
            stats["categories"][category] = count
            stats["total"] += count
        
        return stats
    
    # ========================================================================
    # P0-建议1: 数据完整性检查
    # ========================================================================
    
    def check_data_completeness(self) -> Dict:
        """
        检查知识库数据完整性
        
        Returns:
            Dict: 包含各分类的完整性报告
        """
        logger.info("\n" + "="*60)
        logger.info("知识库数据完整性检查")
        logger.info("="*60)
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "categories": {},
            "overall_completion_rate": 0.0,
            "status": "incomplete"
        }
        
        total_target = 0
        total_actual = 0
        
        for category, domains in self.targets.items():
            category_report = {
                "target": sum(domains.values()),
                "actual": 0,
                "domains": {},
                "completion_rate": 0.0
            }
            
            category_dir = self.data_dir / category
            if category_dir.exists():
                for domain, target_count in domains.items():
                    domain_file = category_dir / f"{domain}.json"
                    
                    actual_count = 0
                    if domain_file.exists():
                        try:
                            with open(domain_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                actual_count = len(data.get("knowledge_points", []))
                        except Exception as e:
                            logger.warning(f"[检查] {domain_file} 读取失败: {e}")
                    
                    domain_rate = (actual_count / target_count) if target_count > 0 else 0
                    
                    category_report["domains"][domain] = {
                        "target": target_count,
                        "actual": actual_count,
                        "completion_rate": domain_rate
                    }
                    
                    category_report["actual"] += actual_count
                    logger.info(f"  {category}/{domain}: {actual_count}/{target_count} ({domain_rate:.1%})")
            
            category_report["completion_rate"] = (
                category_report["actual"] / category_report["target"]
                if category_report["target"] > 0 else 0
            )
            
            report["categories"][category] = category_report
            total_target += category_report["target"]
            total_actual += category_report["actual"]
        
        report["overall_completion_rate"] = (total_actual / total_target) if total_target > 0 else 0
        report["status"] = "complete" if report["overall_completion_rate"] >= 0.95 else "incomplete"
        
        logger.info(f"\n总进度: {total_actual}/{total_target} ({report['overall_completion_rate']:.1%})")
        logger.info(f"状态: {report['status']}")
        logger.info("="*60 + "\n")
        
        return report
    
    def fill_missing(self, dry_run: bool = False):
        """
        补充缺失的知识点
        
        Args:
            dry_run: 如果为True，只显示需要补充的内容，不实际生成
        """
        logger.info("\n" + "="*60)
        logger.info("补充缺失知识点")
        logger.info("="*60)
        
        completeness = self.check_data_completeness()
        
        for category, category_report in completeness["categories"].items():
            for domain, domain_report in category_report["domains"].items():
                missing = domain_report["target"] - domain_report["actual"]
                
                if missing <= 0:
                    continue
                
                logger.info(f"\n[待补充] {category}/{domain}: 缺少 {missing} 条")
                
                if dry_run:
                    logger.info(f"  [Dry Run] 跳过生成")
                    continue
                
                # 实际生成
                self.generate_category(category, missing)
    
    # ========================================================================
    # P0-建议2: AI质量自动评估
    # ========================================================================
    
    def auto_evaluate_quality(self, sample_ratio: float = 0.1) -> Dict:
        """
        使用AI自动评估知识库质量
        
        Args:
            sample_ratio: 抽样比例（默认10%）
        
        Returns:
            Dict: 质量评估报告
        """
        import random
        
        logger.info("\n" + "="*60)
        logger.info("AI质量自动评估")
        logger.info("="*60)
        
        # 收集所有知识点
        all_knowledge = self._load_all_knowledge()
        
        if not all_knowledge:
            logger.warning("[评估] 没有可评估的知识点")
            return {
                "status": "error",
                "message": "没有可评估的知识点"
            }
        
        # 随机抽样
        sample_size = max(5, int(len(all_knowledge) * sample_ratio))
        sample_size = min(sample_size, 30)  # 最多30条
        samples = random.sample(all_knowledge, min(sample_size, len(all_knowledge)))
        
        logger.info(f"[抽样] 从 {len(all_knowledge)} 条中抽取 {len(samples)} 条")
        
        # 构建评估Prompt
        evaluation_prompt = self._build_evaluation_prompt(samples)
        
        # 调用AI评估
        try:
            from openai import OpenAI
            
            client = OpenAI(
                api_key=self.ai_generator.api_key,
                base_url=f"{self.ai_generator.base_url}/v1"
            )
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": """你是一位专业的小说创作知识库质量评审专家。
请从以下维度评估知识点质量（每项0-10分）：
1. 内容准确性：知识点是否符合科学常识或文学传统
2. 创作适用性：知识点是否适合小说创作参考
3. 信息密度：知识点是否提供足够的具体细节
4. 语言表达：知识点是否表述清晰、易于理解

请输出JSON格式的评估结果。"""
                    },
                    {
                        "role": "user",
                        "content": evaluation_prompt
                    }
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            
            # 解析评估结果
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                evaluation = json.loads(json_match.group(0))
                
                report = {
                    "status": "success",
                    "sample_size": len(samples),
                    "total_samples": len(all_knowledge),
                    "total_score": evaluation.get("total_score", 0),
                    "dimension_scores": evaluation.get("dimension_scores", {}),
                    "low_quality_ids": evaluation.get("low_quality_ids", []),
                    "improvements": evaluation.get("improvements", []),
                    "evaluated_at": datetime.now().isoformat()
                }
                
                logger.info(f"\n[评估结果]")
                logger.info(f"  总分: {report['total_score']:.1f}/10")
                logger.info(f"  维度得分:")
                for dim, score in report["dimension_scores"].items():
                    logger.info(f"    - {dim}: {score:.1f}/10")
                logger.info(f"  低质量知识点: {len(report['low_quality_ids'])} 条")
                
                if report["improvements"]:
                    logger.info(f"\n  改进建议:")
                    for i, imp in enumerate(report["improvements"][:5], 1):
                        logger.info(f"    {i}. {imp}")
                
                return report
            else:
                logger.warning("[评估] AI响应格式异常")
                return {
                    "status": "error",
                    "message": "AI响应格式异常"
                }
                
        except Exception as e:
            logger.error(f"[评估] 评估失败: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _build_evaluation_prompt(self, samples: List[Dict]) -> str:
        """构建质量评估Prompt"""
        samples_text = []
        for i, sample in enumerate(samples[:10], 1):  # 最多显示10条
            samples_text.append(
                f"{i}. [{sample.get('knowledge_id', 'unknown')}]\n"
                f"   标题: {sample.get('title', '')}\n"
                f"   内容: {sample.get('content', '')[:200]}...\n"
                f"   关键词: {', '.join(sample.get('keywords', []))}"
            )
        
        return f"""请评估以下{len(samples)}个知识点的质量：

{chr(10).join(samples_text)}

输出格式（JSON）：
{{
  "total_score": 8.5,
  "dimension_scores": {{
    "内容准确性": 9.0,
    "创作适用性": 8.5,
    "信息密度": 8.0,
    "语言表达": 8.5
  }},
  "low_quality_ids": ["scifi-physics-xxx"],
  "improvements": [
    "建议补充具体实例",
    "关键词可以更具体"
  ]
}}

请输出评估结果："""
    
    def _load_all_knowledge(self) -> List[Dict]:
        """加载所有知识点"""
        all_knowledge = []
        
        for category in self.targets.keys():
            category_dir = self.data_dir / category
            if not category_dir.exists():
                continue
            
            for json_file in category_dir.glob("*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for kp in data.get("knowledge_points", []):
                            kp["_source_file"] = str(json_file)
                            all_knowledge.append(kp)
                except:
                    pass
        
        return all_knowledge


# ============================================================================
# 主函数
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="知识库批量生成工具")
    parser.add_argument("--category", type=str, help="分类(scifi/xuanhuan/general/all)")
    parser.add_argument("--count", type=int, help="生成数量(可选,不指定则按目标数量)")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    parser.add_argument("--check-completeness", action="store_true", help="检查数据完整性")
    parser.add_argument("--fill-missing", action="store_true", help="补充缺失的知识点")
    parser.add_argument("--dry-run", action="store_true", help="干运行(只显示需要做什么)")
    parser.add_argument("--evaluate", action="store_true", help="AI质量自动评估")
    parser.add_argument("--sample-ratio", type=float, default=0.1, help="评估抽样比例(默认0.1)")
    
    args = parser.parse_args()
    
    workspace = project_root
    manager = KnowledgeBaseManager(workspace)
    
    # 检查数据完整性
    if args.check_completeness:
        report = manager.check_data_completeness()
        # 保存报告
        report_path = workspace / "data" / "knowledge_completeness_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {report_path}")
        return
    
    # 补充缺失知识点
    if args.fill_missing:
        manager.fill_missing(dry_run=args.dry_run)
        return
    
    # AI质量评估
    if args.evaluate:
        report = manager.auto_evaluate_quality(sample_ratio=args.sample_ratio)
        # 保存报告
        report_path = workspace / "data" / "knowledge_quality_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {report_path}")
        return
    
    # 显示统计信息
    if args.stats:
        stats = manager.get_statistics()
        print("\n" + "="*60)
        print("知识库统计信息")
        print("="*60)
        print(f"总计: {stats['total']} 条知识点")
        print("\n各分类数量:")
        for category, count in stats["categories"].items():
            target = sum(manager.targets[category].values())
            percentage = (count / target * 100) if target > 0 else 0
            print(f"  {category}: {count}/{target} ({percentage:.1f}%)")
        print("="*60 + "\n")
        return
    
    # 生成知识库
    if args.category:
        if args.category == "all":
            # 生成所有分类
            for category in ["scifi", "xuanhuan", "general"]:
                manager.generate_category(category, args.count)
        else:
            manager.generate_category(args.category, args.count)
    else:
        parser.print_help()
        return
    
    # 显示最终统计
    stats = manager.get_statistics()
    print("\n" + "="*60)
    print("生成完成 - 最终统计")
    print("="*60)
    print(f"总计: {stats['total']} 条知识点")
    for category, count in stats["categories"].items():
        target = sum(manager.targets[category].values())
        print(f"  {category}: {count}/{target}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
