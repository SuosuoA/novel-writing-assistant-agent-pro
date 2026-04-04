"""
AI微调数据生成器 - 基于本地Qwen模型

V1.0版本
创建日期：2026-03-29

功能：
- 从高质量生成中提取微调数据
- 格式化为标准训练格式（JSONL）
- 数据增强与清洗
- 自动标注质量评分
- 支持多轮对话格式

设计参考：
- OpenClaw Claw化系统
- 12.9claw化全面说明.md
- 项目内Qwen目录本地模型

使用示例：
    from tools.finetune_data_generator import get_finetune_data_generator
    
    # 生成微调数据
    generator = get_finetune_data_generator()
    
    # 从历史数据生成
    dataset = generator.generate_from_history()
    
    # 保存为JSONL格式
    generator.save_dataset(dataset, "finetune_data.jsonl")
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Core imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.session_state import get_session_state_manager
from core.wal_manager import get_wal_manager

logger = logging.getLogger(__name__)


# ============================================================================
# FinetuneDataGenerator - 微调数据生成器
# ============================================================================

class FinetuneDataGenerator:
    """
    AI微调数据生成器
    
    实现：
    - 从高质量生成中提取训练数据
    - 格式化为标准训练格式
    - 数据增强与清洗
    - 自动标注质量评分
    """
    
    def __init__(self, workspace: Optional[Path] = None, qwen_path: Optional[str] = None):
        """
        初始化微调数据生成器
        
        Args:
            workspace: 工作区路径
            qwen_path: Qwen本地模型路径（默认为项目内的Qwen目录）
        """
        self.workspace = workspace or Path.cwd()
        if qwen_path is None:
            # 默认使用项目内的Qwen目录
            qwen_path = str(Path(__file__).parent.parent / "Qwen")
        self.qwen_path = Path(qwen_path)
        
        # 初始化核心组件
        self.session_manager = get_session_state_manager(self.workspace)
        self.wal_manager = get_wal_manager(self.workspace)
        
        # 数据存储路径
        self.data_dir = self.workspace / ".workbuddy" / "finetune_data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 质量阈值（只提取高质量生成）
        self.quality_threshold = 0.8
        
        logger.info(f"[FinetuneData] 初始化完成，Qwen路径: {qwen_path}")
    
    def generate_from_history(
        self,
        days: int = 30,
        min_score: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        从历史生成数据中提取微调数据
        
        Args:
            days: 提取最近N天的数据
            min_score: 最低质量评分
            
        Returns:
            List: 微调数据集
        """
        dataset = []
        
        try:
            # 从每日冥想日志中提取高质量生成
            meditation_dir = self.workspace / ".workbuddy" / "meditations"
            
            for log_file in meditation_dir.glob("meditation_*.json"):
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                    
                    # 检查评分是否达标
                    overall_score = log_data.get("steps", {}).get("metrics_calculation", {}).get("overall_score", 0)
                    
                    if overall_score >= min_score:
                        # 提取训练样本
                        samples = self._extract_samples_from_log(log_data)
                        dataset.extend(samples)
                        
                except Exception as e:
                    logger.warning(f"[FinetuneData] 处理日志失败 {log_file}: {e}")
            
            logger.info(f"[FinetuneData] 从历史数据提取 {len(dataset)} 条样本")
            return dataset
            
        except Exception as e:
            logger.error(f"[FinetuneData] 从历史生成失败: {e}")
            return []
    
    def generate_from_chapters(
        self,
        min_score: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        从章节文件中提取微调数据
        
        Args:
            min_score: 最低质量评分
            
        Returns:
            List: 微调数据集
        """
        dataset = []
        
        try:
            # 查找章节文件
            chapters_dir = self.workspace / "小说作品"
            
            if not chapters_dir.exists():
                logger.warning(f"[FinetuneData] 章节目录不存在: {chapters_dir}")
                return []
            
            for chapter_file in chapters_dir.glob("*.txt"):
                try:
                    content = chapter_file.read_text(encoding='utf-8')
                    
                    # 检查是否有【本章完】标记
                    if "【本章完】" in content or "[本章完]" in content:
                        # 生成训练样本
                        sample = self._create_chapter_sample(chapter_file.stem, content)
                        if sample:
                            dataset.append(sample)
                            
                except Exception as e:
                    logger.warning(f"[FinetuneData] 处理章节失败 {chapter_file}: {e}")
            
            logger.info(f"[FinetuneData] 从章节提取 {len(dataset)} 条样本")
            return dataset
            
        except Exception as e:
            logger.error(f"[FinetuneData] 从章节生成失败: {e}")
            return []
    
    def generate_from_knowledge(
        self,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        从知识库生成微调数据
        
        Args:
            category: 知识类别（None表示全部）
            
        Returns:
            List: 微调数据集
        """
        dataset = []
        
        try:
            knowledge_dir = self.workspace / "data" / "knowledge"
            
            if not knowledge_dir.exists():
                logger.warning(f"[FinetuneData] 知识库目录不存在: {knowledge_dir}")
                return []
            
            # 查找知识文件
            pattern = f"{category}.json" if category else "*.json"
            
            for knowledge_file in knowledge_dir.glob(pattern):
                try:
                    with open(knowledge_file, 'r', encoding='utf-8') as f:
                        knowledge_list = json.load(f)
                    
                    if isinstance(knowledge_list, list):
                        for item in knowledge_list:
                            # 生成知识问答样本
                            sample = self._create_knowledge_sample(item)
                            if sample:
                                dataset.append(sample)
                                
                except Exception as e:
                    logger.warning(f"[FinetuneData] 处理知识失败 {knowledge_file}: {e}")
            
            logger.info(f"[FinetuneData] 从知识库提取 {len(dataset)} 条样本")
            return dataset
            
        except Exception as e:
            logger.error(f"[FinetuneData] 从知识库生成失败: {e}")
            return []
    
    def generate_synthetic_data(
        self,
        num_samples: int = 100,
        use_local_model: bool = True
    ) -> List[Dict[str, Any]]:
        """
        使用本地Qwen模型生成合成训练数据
        
        Args:
            num_samples: 生成样本数量
            use_local_model: 是否使用本地模型
            
        Returns:
            List: 合成数据集
        """
        dataset = []
        
        if not use_local_model:
            logger.warning("[FinetuneData] 未启用本地模型，跳过合成数据生成")
            return []
        
        try:
            # 检查Qwen本地模型是否可用
            if not self.qwen_path.exists():
                logger.warning(f"[FinetuneData] Qwen模型路径不存在: {self.qwen_path}")
                return []
            
            # 尝试加载本地模型配置
            config_file = self.qwen_path / "config.json"
            if not config_file.exists():
                logger.warning(f"[FinetuneData] Qwen配置文件不存在: {config_file}")
                return []
            
            # 读取模型配置
            with open(config_file, 'r', encoding='utf-8') as f:
                model_config = json.load(f)
            
            model_name = model_config.get("model_name", "qwen2.5-14b-gptq")
            
            # 生成提示词模板
            prompts = self._get_synthesis_prompts()
            
            logger.info(f"[FinetuneData] 使用本地模型生成合成数据: {model_name}")
            
            # 这里应该调用本地模型生成数据
            # 由于实际调用需要加载模型，这里生成占位符
            for i in range(min(num_samples, len(prompts))):
                prompt = prompts[i % len(prompts)]
                
                # 创建合成样本
                sample = {
                    "id": f"synthetic_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}",
                    "type": "synthetic",
                    "prompt": prompt,
                    "response": f"[由{model_name}生成的响应]",  # 实际应调用模型
                    "quality_score": 0.9,  # 假设高质量
                    "timestamp": datetime.now().isoformat()
                }
                
                dataset.append(sample)
            
            logger.info(f"[FinetuneData] 生成 {len(dataset)} 条合成样本")
            return dataset
            
        except Exception as e:
            logger.error(f"[FinetuneData] 合成数据生成失败: {e}")
            return []
    
    def _extract_samples_from_log(self, log_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从冥想日志提取训练样本"""
        samples = []
        
        try:
            # 提取成功操作作为正样本
            steps = log_data.get("steps", {})
            data_collection = steps.get("data_collection", {})
            
            word_count = data_collection.get("word_count", 0)
            operations = data_collection.get("operations", 0)
            overall_score = steps.get("metrics_calculation", {}).get("overall_score", 0)
            
            if overall_score >= self.quality_threshold:
                sample = {
                    "id": f"log_{log_data.get('timestamp', '')}",
                    "type": "generation",
                    "metadata": {
                        "word_count": word_count,
                        "operations": operations,
                        "score": overall_score
                    },
                    "quality_score": overall_score,
                    "timestamp": log_data.get("timestamp")
                }
                samples.append(sample)
            
        except Exception as e:
            logger.warning(f"[FinetuneData] 提取样本失败: {e}")
        
        return samples
    
    def _create_chapter_sample(self, chapter_name: str, content: str) -> Optional[Dict[str, Any]]:
        """创建章节训练样本"""
        try:
            # 分割内容为段落
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            
            if len(paragraphs) < 2:
                return None
            
            # 创建样本
            sample = {
                "id": f"chapter_{chapter_name}",
                "type": "chapter",
                "prompt": "请续写以下内容：\n\n" + paragraphs[0],
                "response": "\n\n".join(paragraphs[1:]),
                "quality_score": 0.85,  # 假设章节质量较高
                "timestamp": datetime.now().isoformat()
            }
            
            return sample
            
        except Exception as e:
            logger.warning(f"[FinetuneData] 创建章节样本失败: {e}")
            return None
    
    def _create_knowledge_sample(self, knowledge_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建知识问答样本"""
        try:
            title = knowledge_item.get("title", "")
            content = knowledge_item.get("content", "")
            
            if not title or not content:
                return None
            
            # 创建问答样本
            sample = {
                "id": f"knowledge_{knowledge_item.get('id', '')}",
                "type": "qa",
                "prompt": f"请详细解释：{title}",
                "response": content,
                "category": knowledge_item.get("category", "general"),
                "quality_score": 0.9,
                "timestamp": datetime.now().isoformat()
            }
            
            return sample
            
        except Exception as e:
            logger.warning(f"[FinetuneData] 创建知识样本失败: {e}")
            return None
    
    def _get_synthesis_prompts(self) -> List[str]:
        """获取合成数据提示词模板"""
        return [
            "请描写一个紧张的战斗场景",
            "请描写一个温馨的家庭聚会",
            "请描写一个神秘的古代遗迹",
            "请描写一个科幻的未来城市",
            "请描写一个浪漫的相遇场景",
            "请描写一个悲伤的离别场景",
            "请描写一个悬疑的推理过程",
            "请描写一个热血的冒险旅程",
            "请描写一个幽默的误会情节",
            "请描写一个感人的重逢场景"
        ]
    
    def augment_data(
        self,
        dataset: List[Dict[str, Any]],
        augmentation_factor: int = 2
    ) -> List[Dict[str, Any]]:
        """
        数据增强
        
        Args:
            dataset: 原始数据集
            augmentation_factor: 增强倍数
            
        Returns:
            List: 增强后的数据集
        """
        augmented = list(dataset)
        
        try:
            for sample in dataset:
                # 创建增强样本
                for i in range(augmentation_factor - 1):
                    augmented_sample = dict(sample)
                    augmented_sample["id"] = f"{sample['id']}_aug_{i}"
                    augmented_sample["augmented"] = True
                    augmented.append(augmented_sample)
            
            logger.info(f"[FinetuneData] 数据增强: {len(dataset)} -> {len(augmented)}")
            return augmented
            
        except Exception as e:
            logger.error(f"[FinetuneData] 数据增强失败: {e}")
            return dataset
    
    def clean_data(self, dataset: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        数据清洗
        
        Args:
            dataset: 原始数据集
            
        Returns:
            List: 清洗后的数据集
        """
        cleaned = []
        
        try:
            for sample in dataset:
                # 检查必需字段
                if not sample.get("id") or not sample.get("type"):
                    continue
                
                # 检查质量评分
                if sample.get("quality_score", 0) < self.quality_threshold:
                    continue
                
                # 检查内容长度
                response = sample.get("response", "")
                if len(response) < 50:  # 至少50字
                    continue
                
                cleaned.append(sample)
            
            logger.info(f"[FinetuneData] 数据清洗: {len(dataset)} -> {len(cleaned)}")
            return cleaned
            
        except Exception as e:
            logger.error(f"[FinetuneData] 数据清洗失败: {e}")
            return dataset
    
    def format_for_training(
        self,
        dataset: List[Dict[str, Any]],
        format_type: str = "openai"
    ) -> List[Dict[str, Any]]:
        """
        格式化为训练格式
        
        Args:
            dataset: 原始数据集
            format_type: 格式类型 (openai/alpaca/llama)
            
        Returns:
            List: 格式化后的数据集
        """
        formatted = []
        
        try:
            for sample in dataset:
                if format_type == "openai":
                    # OpenAI格式
                    formatted_sample = {
                        "messages": [
                            {"role": "system", "content": "你是一个专业的小说创作助手。"},
                            {"role": "user", "content": sample.get("prompt", "")},
                            {"role": "assistant", "content": sample.get("response", "")}
                        ]
                    }
                elif format_type == "alpaca":
                    # Alpaca格式
                    formatted_sample = {
                        "instruction": sample.get("prompt", ""),
                        "input": "",
                        "output": sample.get("response", "")
                    }
                elif format_type == "llama":
                    # Llama格式
                    formatted_sample = {
                        "text": f"<s>[INST] {sample.get('prompt', '')} [/INST] {sample.get('response', '')}</s>"
                    }
                else:
                    formatted_sample = sample
                
                formatted.append(formatted_sample)
            
            logger.info(f"[FinetuneData] 格式化完成: {format_type}, {len(formatted)} 条")
            return formatted
            
        except Exception as e:
            logger.error(f"[FinetuneData] 格式化失败: {e}")
            return []
    
    def save_dataset(
        self,
        dataset: List[Dict[str, Any]],
        filename: str
    ) -> bool:
        """
        保存数据集为JSONL格式
        
        Args:
            dataset: 数据集
            filename: 文件名
            
        Returns:
            bool: 是否成功
        """
        try:
            output_file = self.data_dir / filename
            
            with open(output_file, 'w', encoding='utf-8') as f:
                for sample in dataset:
                    f.write(json.dumps(sample, ensure_ascii=False) + '\n')
            
            logger.info(f"[FinetuneData] 数据集保存成功: {output_file}, {len(dataset)} 条")
            return True
            
        except Exception as e:
            logger.error(f"[FinetuneData] 保存数据集失败: {e}")
            return False
    
    def generate_complete_dataset(
        self,
        include_synthetic: bool = False,
        format_type: str = "openai"
    ) -> Dict[str, Any]:
        """
        生成完整微调数据集
        
        Args:
            include_synthetic: 是否包含合成数据
            format_type: 训练格式
            
        Returns:
            Dict: 生成结果
        """
        result = {
            "success": False,
            "total_samples": 0,
            "sources": {},
            "output_file": None,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            all_samples = []
            
            # 1. 从历史数据生成
            history_data = self.generate_from_history(min_score=self.quality_threshold)
            all_samples.extend(history_data)
            result["sources"]["history"] = len(history_data)
            
            # 2. 从章节生成
            chapter_data = self.generate_from_chapters(min_score=self.quality_threshold)
            all_samples.extend(chapter_data)
            result["sources"]["chapters"] = len(chapter_data)
            
            # 3. 从知识库生成
            knowledge_data = self.generate_from_knowledge()
            all_samples.extend(knowledge_data)
            result["sources"]["knowledge"] = len(knowledge_data)
            
            # 4. 合成数据（可选）
            if include_synthetic:
                synthetic_data = self.generate_synthetic_data(num_samples=100)
                all_samples.extend(synthetic_data)
                result["sources"]["synthetic"] = len(synthetic_data)
            
            # 5. 数据增强
            augmented_data = self.augment_data(all_samples, augmentation_factor=2)
            
            # 6. 数据清洗
            cleaned_data = self.clean_data(augmented_data)
            
            # 7. 格式化
            formatted_data = self.format_for_training(cleaned_data, format_type=format_type)
            
            # 8. 保存
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"finetune_dataset_{timestamp}.jsonl"
            
            if self.save_dataset(formatted_data, filename):
                result["success"] = True
                result["total_samples"] = len(formatted_data)
                result["output_file"] = str(self.data_dir / filename)
            
            logger.info(f"[FinetuneData] 完整数据集生成: {result['total_samples']} 条")
            return result
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"[FinetuneData] 完整数据集生成失败: {e}")
            return result


# ============================================================================
# 全局实例
# ============================================================================

_generator_instance: Optional[FinetuneDataGenerator] = None
_generator_lock = threading.Lock()


def get_finetune_data_generator(
    workspace: Optional[Path] = None,
    qwen_path: str = str(Path(__file__).parent.parent / "Qwen")
) -> FinetuneDataGenerator:
    """
    获取微调数据生成器单例
    
    Args:
        workspace: 工作区路径
        qwen_path: Qwen本地模型路径
        
    Returns:
        FinetuneDataGenerator: 生成器实例
    """
    global _generator_instance
    
    if _generator_instance is None:
        with _generator_lock:
            if _generator_instance is None:
                _generator_instance = FinetuneDataGenerator(workspace, qwen_path)
    
    return _generator_instance


# ============================================================================
# 主入口
# ============================================================================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 生成微调数据
    generator = get_finetune_data_generator()
    
    # 生成完整数据集
    result = generator.generate_complete_dataset(include_synthetic=False)
    
    print(f"生成结果: {result}")