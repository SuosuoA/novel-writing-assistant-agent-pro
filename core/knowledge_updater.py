#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识库自动更新器

从用户反馈中自动提取新知识点，保持知识库持续进化。
"""

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KnowledgeUpdater:
    """知识库自动更新器 - 从用户反馈中提取新知识点"""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.knowledge_dir = workspace_root / "data" / "knowledge"
        self.config_file = workspace_root / "config.yaml"
        
        self.api_key = ""
        self.base_url = "https://api.deepseek.com"
        self.model = "deepseek-chat"
        
        self._load_config()
    
    def _load_config(self):
        """加载API配置"""
        try:
            import yaml
            
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                
                # 获取API Key
                api_key = config.get("api_key", "")
                if api_key == "ENCRYPTED_IN_SECRETS_FILE":
                    try:
                        from core.api_key_encryption import get_api_key_encryption
                        encryption = get_api_key_encryption(self.workspace_root)
                        self.api_key = encryption.get_api_key("DeepSeek") or ""
                    except:
                        pass
                else:
                    self.api_key = api_key
                
                # 获取其他配置
                if "deepseek" in config and isinstance(config["deepseek"], dict):
                    self.base_url = config["deepseek"].get("base_url", self.base_url)
                
                self.model = config.get("model", self.model)
                
        except Exception as e:
            logger.warning(f"[KNOWLEDGE_UPDATER] 配置加载失败: {e}")
    
    def extract_new_knowledge(self, feedback_details: str, category: str) -> List[Dict]:
        """
        从反馈中提取新知识点
        
        Args:
            feedback_details: 反馈详情
            category: 知识点分类 (scifi/xuanhuan/general)
            
        Returns:
            新知识点列表
        """
        if not self.api_key:
            logger.warning("[KNOWLEDGE_UPDATER] API Key未配置，无法提取知识点")
            return []
        
        prompt = f"""从以下用户反馈中提取可能缺失的专业知识点，适合{category}小说创作参考:

反馈内容: {feedback_details}

要求:
1. 提取1-3个新知识点
2. 每个知识点包含:
   - title: 简洁的标题（10-20字）
   - content: 详细内容（200-300字）
   - keywords: 关键词（5-8个）
3. 知识点应具体且有价值，能为小说创作提供灵感
4. 内容要专业准确，符合科学常识或文学传统

输出格式(JSON数组):
[
  {{
    "title": "知识点标题",
    "content": "知识点详细内容...",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
  }}
]

只输出JSON数组，不要其他内容。"""

        try:
            from openai import OpenAI
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=f"{self.base_url}/v1"
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个小说创作知识库专家，擅长从用户反馈中提取专业知识点。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            result = response.choices[0].message.content
            
            # 解析JSON
            json_match = re.search(r'\[\s*\{.*?\}\s*\]', result, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                knowledge_points = json.loads(json_str)
                logger.info(f"[KNOWLEDGE_UPDATER] 成功提取 {len(knowledge_points)} 个新知识点")
                return knowledge_points
            else:
                logger.warning("[KNOWLEDGE_UPDATER] 未找到JSON数组")
                return []
                
        except Exception as e:
            logger.error(f"[KNOWLEDGE_UPDATER] 提取知识点失败: {e}")
            return []
    
    def validate_and_add(self, knowledge_point: Dict, category: str, domain: str) -> bool:
        """
        验证并添加到知识库
        
        Args:
            knowledge_point: 知识点
            category: 分类
            domain: 领域
            
        Returns:
            是否成功添加
        """
        # 1. 验证格式
        required_fields = ['title', 'content', 'keywords']
        if not all(field in knowledge_point for field in required_fields):
            logger.warning(f"[KNOWLEDGE_UPDATER] 知识点格式不完整: {knowledge_point}")
            return False
        
        # 2. 验证内容长度
        if len(knowledge_point.get('content', '')) < 100:
            logger.warning(f"[KNOWLEDGE_UPDATER] 内容过短，跳过: {knowledge_point.get('title', '')}")
            return False
        
        # 3. 检查重复
        if self._is_duplicate(knowledge_point, category):
            logger.info(f"[KNOWLEDGE_UPDATER] 知识点已存在，跳过: {knowledge_point['title']}")
            return False
        
        # 4. 保存到JSON文件
        try:
            self._save_to_json(knowledge_point, category, domain)
            logger.info(f"[KNOWLEDGE_UPDATER] 成功添加知识点: {knowledge_point['title']}")
            return True
        except Exception as e:
            logger.error(f"[KNOWLEDGE_UPDATER] 保存知识点失败: {e}")
            return False
    
    def _is_duplicate(self, knowledge_point: Dict, category: str) -> bool:
        """检查知识点是否重复"""
        title = knowledge_point.get('title', '').lower()
        
        category_dir = self.knowledge_dir / category
        if not category_dir.exists():
            return False
        
        for json_file in category_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for existing_kp in data.get('knowledge_points', []):
                        existing_title = existing_kp.get('title', '').lower()
                        # 完全匹配或高度相似
                        if title == existing_title:
                            return True
                        # 检查是否包含关系
                        if title in existing_title or existing_title in title:
                            return True
            except:
                pass
        
        return False
    
    def _save_to_json(self, knowledge_point: Dict, category: str, domain: str):
        """保存到JSON文件"""
        # 构建文件路径
        json_file = self.knowledge_dir / category / f"{domain}.json"
        json_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取现有数据
        if json_file.exists():
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {
                "category": category,
                "domain": domain,
                "total_count": 0,
                "knowledge_points": []
            }
        
        # 生成知识点ID
        kp_id = f"{category}-{domain}-{uuid.uuid4().hex[:8]}"
        
        # 构建完整知识点
        full_kp = {
            "knowledge_id": kp_id,
            "category": category,
            "domain": domain,
            "title": knowledge_point['title'],
            "content": knowledge_point['content'],
            "keywords": knowledge_point['keywords'],
            "references": ["用户反馈提取", "AI生成"],
            "created_at": datetime.now().isoformat(),
            "source": "feedback_extraction"
        }
        
        # 添加到列表
        data['knowledge_points'].append(full_kp)
        data['total_count'] = len(data['knowledge_points'])
        data['last_updated'] = datetime.now().isoformat()
        
        # 保存
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def process_feedback_batch(self, feedbacks: List[Dict]) -> Dict:
        """
        批量处理反馈并提取知识点
        
        Args:
            feedbacks: 反馈列表
            
        Returns:
            处理结果统计
        """
        result = {
            "total_feedbacks": len(feedbacks),
            "extracted_knowledge": 0,
            "added_knowledge": 0,
            "failed": 0,
            "details": []
        }
        
        for feedback in feedbacks:
            try:
                details = feedback.get('details', '')
                if not details or len(details) < 20:
                    continue
                
                # 推断分类
                category = self._infer_category(details)
                domain = self._infer_domain(details)
                
                # 提取新知识点
                new_kps = self.extract_new_knowledge(details, category)
                
                result['extracted_knowledge'] += len(new_kps)
                
                # 验证并添加
                for kp in new_kps:
                    if self.validate_and_add(kp, category, domain):
                        result['added_knowledge'] += 1
                        result['details'].append({
                            "title": kp['title'],
                            "category": category,
                            "domain": domain
                        })
                        
            except Exception as e:
                logger.error(f"[KNOWLEDGE_UPDATER] 处理反馈失败: {e}")
                result['failed'] += 1
        
        return result
    
    def _infer_category(self, text: str) -> str:
        """从文本中推断知识点分类"""
        # 科幻关键词
        scifi_keywords = ["科幻", "未来", "太空", "科技", "宇宙", "飞船", "机器人", 
                         "人工智能", "基因", "量子", "时间旅行", "外星"]
        
        # 玄幻关键词
        xuanhuan_keywords = ["玄幻", "魔法", "修仙", "神话", "仙侠", "武侠", 
                            "法术", "咒语", "灵力", "仙界"]
        
        # 检查匹配
        text_lower = text.lower()
        
        scifi_count = sum(1 for kw in scifi_keywords if kw in text_lower)
        xuanhuan_count = sum(1 for kw in xuanhuan_keywords if kw in text_lower)
        
        if scifi_count > xuanhuan_count:
            return "scifi"
        elif xuanhuan_count > scifi_count:
            return "xuanhuan"
        else:
            return "general"
    
    def _infer_domain(self, text: str) -> str:
        """从文本中推断知识点领域"""
        domain_keywords = {
            "physics": ["物理", "力学", "光学", "相对论", "量子", "引力", "光速"],
            "biology": ["生物", "基因", "进化", "DNA", "细胞", "生命"],
            "space": ["太空", "宇宙", "星系", "行星", "恒星", "黑洞"],
            "technology": ["科技", "技术", "人工智能", "机器人", "纳米"],
            "magic": ["魔法", "法术", "咒语", "魔力"],
            "mythology": ["神话", "传说", "神", "仙"],
            "cultivation": ["修仙", "修炼", "境界", "功法"],
            "writing": ["写作", "叙事", "描写", "风格"],
            "narrative": ["叙事", "情节", "结构", "节奏"],
            "character": ["人物", "角色", "性格", "心理"]
        }
        
        text_lower = text.lower()
        
        for domain, keywords in domain_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return domain
        
        return "general"


# 全局实例
_updater_instance: Optional[KnowledgeUpdater] = None


def get_knowledge_updater(workspace_root: Optional[Path] = None) -> KnowledgeUpdater:
    """
    获取知识库更新器实例
    
    Args:
        workspace_root: 工作区根目录
        
    Returns:
        KnowledgeUpdater实例
    """
    global _updater_instance
    
    if _updater_instance is None:
        if workspace_root is None:
            workspace_root = Path.cwd()
        _updater_instance = KnowledgeUpdater(workspace_root)
    
    return _updater_instance
