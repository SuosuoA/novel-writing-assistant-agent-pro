#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强加权验证器 - 支持动态配置和热更新

版本: V1.1（8维度评分体系）
创建日期: 2026-03-25
更新日期: 2026-03-26
作者: 后端架构师 / 软件架构师

功能:
- 支持从YAML配置文件动态加载评分权重
- 支持运行时热更新权重配置
- 支持权重校验和归一化
- 向后兼容V5原有接口
- 支持V1.7版本8维度评分体系

权重配置文件: config/validator_weights.yaml

核心规则:
1. 权重总和必须为1.0（允许±10%误差，自动归一化）
2. 权重值范围: 0.0-1.0
3. 必须包含8个维度（V1.7版本新增知识点引用、逆向反馈维度）

版本历史:
- V1.0 (2026-03-25): 初始版本，7维度评分体系
- V1.1 (2026-03-26): 升级为8维度评分体系
  - 新增 knowledge_reference（知识点引用）维度
  - 新增 reverse_feedback（逆向反馈）维度
  - 移除 knowledge_consistency 维度（合并到 knowledge_reference）

参考文档:
- 《10.升级方案✅️.md》Sprint 5-6
- 《10.13 扩展ValidationScores维度说明✅️.md》
- 《11.1生成和评分完善计划✅️.md》
"""

import logging
import yaml
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field
import copy

logger = logging.getLogger(__name__)


@dataclass
class WeightConfig:
    """权重配置数据类（V1.1版本 - 8维度）

    权重分配（V1.7版本）：
    - 字数: 8%
    - 知识点引用: 8%
    - 大纲: 13%
    - 风格: 19%
    - 人设: 19%
    - 世界观: 12%
    - 逆向反馈: 11%
    - 自然度: 10%
    总计: 100%
    """
    # V1.7版本8维度权重
    word_count: float = 0.08
    knowledge_reference: float = 0.08
    outline: float = 0.13
    style: float = 0.19
    character: float = 0.19
    worldview: float = 0.12
    reverse_feedback: float = 0.11
    naturalness: float = 0.10

    # 元数据
    config_version: str = "1.1"
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_by: str = "system"

    def to_dict(self) -> Dict[str, float]:
        """转换为权重字典"""
        return {
            'word_count': self.word_count,
            'knowledge_reference': self.knowledge_reference,
            'outline': self.outline,
            'style': self.style,
            'character': self.character,
            'worldview': self.worldview,
            'reverse_feedback': self.reverse_feedback,
            'naturalness': self.naturalness,
        }

    def validate(self) -> bool:
        """校验权重配置"""
        weights = self.to_dict()

        # 检查所有权重值范围
        for name, weight in weights.items():
            if not 0.0 <= weight <= 1.0:
                logger.error(f"权重值超出范围: {name}={weight}")
                return False

        # 检查权重总和（允许±10%误差）
        total = sum(weights.values())
        if not 0.9 <= total <= 1.1:
            logger.error(f"权重总和超出范围: {total:.2f}（期望1.0±0.1）")
            return False

        return True

    def normalize(self) -> 'WeightConfig':
        """归一化权重配置"""
        weights = self.to_dict()
        total = sum(weights.values())

        if total == 0:
            logger.warning("权重总和为0，使用默认配置")
            return WeightConfig()

        # 归一化
        normalized = {k: v / total for k, v in weights.items()}

        return WeightConfig(
            word_count=normalized['word_count'],
            knowledge_reference=normalized['knowledge_reference'],
            outline=normalized['outline'],
            style=normalized['style'],
            character=normalized['character'],
            worldview=normalized['worldview'],
            reverse_feedback=normalized['reverse_feedback'],
            naturalness=normalized['naturalness'],
            config_version=self.config_version,
            last_updated=datetime.now().isoformat(),
            updated_by=self.updated_by,
        )


class EnhancedWeightedValidator:
    """
    增强加权验证器 - 支持动态配置和热更新

    核心功能:
    1. 从YAML配置文件加载权重
    2. 运行时热更新权重配置
    3. 权重校验和归一化
    4. 向后兼容V5接口
    5. 支持V1.7版本8维度评分体系
    """

    # 默认权重配置（V1.7版本 - 8维度）
    DEFAULT_WEIGHTS = WeightConfig()

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化验证器

        Args:
            config_path: 配置文件路径，默认为 config/validator_weights.yaml
        """
        self._lock = threading.RLock()  # 线程安全锁
        self._config_path = Path(config_path) if config_path else None
        self._weights = copy.deepcopy(self.DEFAULT_WEIGHTS)
        self._config_mtime = None  # 配置文件修改时间（用于检测热更新）

        # 如果未指定配置文件路径，尝试从项目根目录查找
        if not self._config_path:
            project_root = Path(__file__).parent.parent
            default_config = project_root / "config" / "validator_weights.yaml"
            if default_config.exists():
                self._config_path = default_config
                logger.info(f"使用默认配置文件: {default_config}")

        # 加载配置
        if self._config_path and self._config_path.exists():
            self.load_weights_from_file()
        else:
            logger.warning("未找到权重配置文件，使用默认配置")

    @property
    def weights(self) -> Dict[str, float]:
        """获取当前权重配置（线程安全）"""
        with self._lock:
            return self._weights.to_dict()

    @property
    def weight_config(self) -> WeightConfig:
        """获取完整权重配置对象（线程安全）"""
        with self._lock:
            return copy.deepcopy(self._weights)

    def load_weights_from_file(self, config_path: Optional[str] = None) -> bool:
        """
        从YAML文件加载权重配置

        Args:
            config_path: 配置文件路径（可选，默认使用初始化时的路径）

        Returns:
            是否加载成功
        """
        with self._lock:
            target_path = Path(config_path) if config_path else self._config_path

            if not target_path or not target_path.exists():
                logger.error(f"配置文件不存在: {target_path}")
                return False

            try:
                with open(target_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)

                # 解析权重配置
                weights_section = config_data.get('weights', {})

                new_weights = WeightConfig(
                    word_count=weights_section.get('word_count', self._weights.word_count),
                    knowledge_reference=weights_section.get('knowledge_reference', self._weights.knowledge_reference),
                    outline=weights_section.get('outline', self._weights.outline),
                    style=weights_section.get('style', self._weights.style),
                    character=weights_section.get('character', self._weights.character),
                    worldview=weights_section.get('worldview', self._weights.worldview),
                    reverse_feedback=weights_section.get('reverse_feedback', self._weights.reverse_feedback),
                    naturalness=weights_section.get('naturalness', self._weights.naturalness),
                    config_version=config_data.get('version', '1.1'),
                    last_updated=datetime.now().isoformat(),
                    updated_by=config_data.get('updated_by', 'file_load'),
                )

                # 校验配置
                if not new_weights.validate():
                    logger.error("权重配置校验失败，保持原配置")
                    return False

                # 归一化
                normalized = new_weights.normalize()

                # 更新配置
                self._weights = normalized
                self._config_path = target_path
                self._config_mtime = target_path.stat().st_mtime

                logger.info(f"成功加载权重配置: {target_path}")
                logger.info(f"当前权重: {normalized.to_dict()}")

                return True

            except Exception as e:
                logger.error(f"加载权重配置失败: {e}", exc_info=True)
                return False

    def update_weights(self, new_weights: Dict[str, float], updated_by: str = "api") -> bool:
        """
        热更新权重配置

        Args:
            new_weights: 新的权重配置字典
            updated_by: 更新来源标识

        Returns:
            是否更新成功
        """
        with self._lock:
            try:
                # 构建新的配置对象
                weight_config = WeightConfig(
                    word_count=new_weights.get('word_count', self._weights.word_count),
                    knowledge_reference=new_weights.get('knowledge_reference', self._weights.knowledge_reference),
                    outline=new_weights.get('outline', self._weights.outline),
                    style=new_weights.get('style', self._weights.style),
                    character=new_weights.get('character', self._weights.character),
                    worldview=new_weights.get('worldview', self._weights.worldview),
                    reverse_feedback=new_weights.get('reverse_feedback', self._weights.reverse_feedback),
                    naturalness=new_weights.get('naturalness', self._weights.naturalness),
                    config_version=self._weights.config_version,
                    last_updated=datetime.now().isoformat(),
                    updated_by=updated_by,
                )

                # 校验配置
                if not weight_config.validate():
                    logger.error("权重配置校验失败，更新拒绝")
                    return False

                # 归一化
                normalized = weight_config.normalize()

                # 更新配置
                self._weights = normalized

                logger.info(f"成功热更新权重配置（来源: {updated_by}）")
                logger.info(f"新权重: {normalized.to_dict()}")

                return True

            except Exception as e:
                logger.error(f"热更新权重配置失败: {e}", exc_info=True)
                return False

    def check_and_reload_if_modified(self) -> bool:
        """
        检查配置文件是否被修改，如果修改则自动重新加载

        Returns:
            是否触发了重新加载
        """
        if not self._config_path or not self._config_path.exists():
            return False

        with self._lock:
            try:
                current_mtime = self._config_path.stat().st_mtime

                if self._config_mtime is None or current_mtime > self._config_mtime:
                    logger.info("检测到配置文件修改，触发热更新")
                    return self.load_weights_from_file()

                return False

            except Exception as e:
                logger.error(f"检查配置文件修改失败: {e}")
                return False

    def get_weight(self, dimension: str) -> float:
        """
        获取指定维度的权重

        Args:
            dimension: 维度名称

        Returns:
            权重值
        """
        with self._lock:
            return self._weights.to_dict().get(dimension, 0.0)

    def validate_content(self, content: str, **kwargs) -> Dict[str, Any]:
        """
        验证内容（向后兼容V5接口）

        Args:
            content: 待验证内容
            **kwargs: 其他参数

        Returns:
            验证结果字典
        """
        # 检查配置文件是否修改
        self.check_and_reload_if_modified()

        # 返回当前权重配置
        weights = self.weights

        # 这里只返回权重配置，实际验证逻辑由插件实现
        # 保持向后兼容
        return {
            'weights': weights,
            'config_version': self._weights.config_version,
            'last_updated': self._weights.last_updated,
        }

    def get_config_info(self) -> Dict[str, Any]:
        """
        获取配置信息

        Returns:
            配置信息字典
        """
        with self._lock:
            return {
                'config_path': str(self._config_path) if self._config_path else None,
                'config_version': self._weights.config_version,
                'last_updated': self._weights.last_updated,
                'updated_by': self._weights.updated_by,
                'weights': self._weights.to_dict(),
                'total_weight': sum(self._weights.to_dict().values()),
            }

    def save_weights_to_file(self, config_path: Optional[str] = None) -> bool:
        """
        保存权重配置到YAML文件

        Args:
            config_path: 配置文件路径（可选）

        Returns:
            是否保存成功
        """
        with self._lock:
            target_path = Path(config_path) if config_path else self._config_path

            if not target_path:
                logger.error("未指定配置文件路径")
                return False

            try:
                # 确保目录存在
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # 构建配置数据
                config_data = {
                    'version': self._weights.config_version,
                    'updated_by': self._weights.updated_by,
                    'last_updated': self._weights.last_updated,
                    'weights': self._weights.to_dict(),
                }

                # 写入文件
                with open(target_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False)

                logger.info(f"成功保存权重配置: {target_path}")

                return True

            except Exception as e:
                logger.error(f"保存权重配置失败: {e}", exc_info=True)
                return False


# ============================================================================
# 模块级单例
# ============================================================================

_validator_instance: Optional[EnhancedWeightedValidator] = None
_instance_lock = threading.Lock()


def get_validator_instance(config_path: Optional[str] = None) -> EnhancedWeightedValidator:
    """
    获取验证器单例实例

    Args:
        config_path: 配置文件路径

    Returns:
        验证器实例
    """
    global _validator_instance

    with _instance_lock:
        if _validator_instance is None:
            _validator_instance = EnhancedWeightedValidator(config_path)

        return _validator_instance


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("增强加权验证器测试（V1.7版本 - 8维度评分体系）")
    print("=" * 60)

    # 创建验证器实例
    validator = EnhancedWeightedValidator()

    print("\n1. 默认权重配置（V1.7版本）:")
    print(f"   {validator.weights}")

    print("\n2. 配置信息:")
    info = validator.get_config_info()
    for key, value in info.items():
        print(f"   {key}: {value}")

    print("\n3. 测试热更新:")
    new_weights = {
        'word_count': 0.10,
        'knowledge_reference': 0.10,
        'outline': 0.12,
        'style': 0.18,
        'character': 0.18,
        'worldview': 0.12,
        'reverse_feedback': 0.10,
        'naturalness': 0.10,
    }
    success = validator.update_weights(new_weights, updated_by="test")
    print(f"   更新结果: {'成功' if success else '失败'}")
    print(f"   新权重: {validator.weights}")

    print("\n4. 测试权重校验:")
    invalid_weights = {
        'word_count': 2.0,  # 超出范围
        'knowledge_reference': 0.08,
        'outline': 0.13,
        'style': 0.19,
        'character': 0.19,
        'worldview': 0.12,
        'reverse_feedback': 0.11,
        'naturalness': 0.10,
    }
    success = validator.update_weights(invalid_weights, updated_by="test")
    print(f"   更新结果: {'成功（不应该）' if success else '失败（预期）'}")

    print("\n5. 测试保存配置:")
    success = validator.save_weights_to_file("config/validator_weights_test.yaml")
    print(f"   保存结果: {'成功' if success else '失败'}")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
