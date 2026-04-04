"""
世界观解析器适配器

V3.1版本
创建日期: 2026-03-21
更新日期: 2026-04-04（新增parse_for_display方法，支持GUI显示解析）
"""

import json
import re
import importlib
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..agent_adapter import AgentAdapter, AgentState
from ..priority import AgentTask

logger = logging.getLogger(__name__)


class WorldviewParserAdapter(AgentAdapter):
    """
    世界观解析器适配器

    包装 plugins.worldview-parser-v1.plugin.WorldviewParserPlugin

    注意：该插件不需要PluginContext初始化，直接调用analyze方法
    """

    def __init__(self):
        # 不传递module_path和class_name，因为我们会手动处理
        super().__init__(
            agent_type="worldview_parser",
            module_path="",
            class_name="",
        )
        self._plugin_instance: Optional[Any] = None

    def initialize(self) -> bool:
        """初始化适配器"""
        try:
            self._set_state(AgentState.LOADED)

            # 使用importlib动态导入插件（支持带连字符的目录名）
            plugin_module = importlib.import_module("plugins.worldview-parser-v1.plugin")
            WorldviewParserPlugin = getattr(plugin_module, "WorldviewParserPlugin")

            # 创建插件实例（不调用initialize方法，因为插件不需要PluginContext）
            self._plugin_instance = WorldviewParserPlugin()

            self._wrapped_instance = self._plugin_instance
            self._set_state(AgentState.ACTIVE)
            self._initialized = True
            logger.info(f"Agent适配器初始化成功: {self.agent_type}")
            return True

        except Exception as e:
            self._set_state(AgentState.ERROR)
            logger.error(f"Agent适配器初始化失败 {self.agent_type}: {e}", exc_info=True)
            return False

    def execute(self, task: AgentTask) -> Dict[str, Any]:
        """
        执行世界观解析

        Args:
            task: 任务对象

        Returns:
            解析结果
        """
        if not self._initialized or not self._wrapped_instance:
            raise RuntimeError(f"Agent {self.agent_type} 未初始化")

        payload = task.payload

        try:
            # 调用插件的analyze方法
            worldview_content = payload.get("worldview_content")
            options = payload.get("options", {})

            result = self._wrapped_instance.analyze(worldview_content, options)

            # 更新状态
            self._increment_completed()

            return {
                "task_id": task.task_id,
                "result": result,
                "metadata": {
                    "elements_count": result.get("total_elements", 0),
                    "categories": result.get("categories", {}),
                },
            }

        except Exception as e:
            self._increment_failed()
            logger.error(f"世界观解析失败: {e}", exc_info=True)
            raise

    def parse_for_display(self, worldview_content: Any) -> List[Dict[str, Any]]:
        """
        解析世界观内容为GUI显示格式

        将各种格式的世界观数据转换为统一的显示格式。
        支持格式：
        1. 字典列表格式：[{"name": "...", "category": "...", "description": "..."}]
        2. JSON字符串格式
        3. Markdown格式

        Args:
            worldview_content: 世界观内容（字符串、列表或字典）

        Returns:
            标准化的世界观条目列表，每个条目包含：
            - name: 名称
            - category: 分类
            - description: 描述
            - elements: 要素（截断显示用）
            - status: 状态
            - modified: 修改时间
        """
        entries = []

        try:
            # 格式1：已经是列表
            if isinstance(worldview_content, list):
                entries = self._parse_list_format(worldview_content)

            # 格式2：字符串
            elif isinstance(worldview_content, str):
                # 尝试JSON解析
                try:
                    parsed_data = json.loads(worldview_content)
                    if isinstance(parsed_data, list):
                        entries = self._parse_list_format(parsed_data)
                    elif isinstance(parsed_data, dict) and 'elements' in parsed_data:
                        entries = self._parse_list_format(parsed_data['elements'])
                except (json.JSONDecodeError, TypeError):
                    # 不是JSON，尝试Markdown解析
                    entries = self._parse_markdown_format(worldview_content)

            # 格式3：字典（带elements字段）
            elif isinstance(worldview_content, dict):
                if 'elements' in worldview_content:
                    entries = self._parse_list_format(worldview_content['elements'])

            return entries

        except Exception as e:
            logger.error(f"解析世界观内容失败: {e}")
            return []

    def _parse_list_format(self, data: List[Dict]) -> List[Dict[str, Any]]:
        """解析列表格式数据"""
        entries = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')

        for entry in data:
            if not isinstance(entry, dict):
                continue

            # 提取名称（兼容多种字段名）
            name = entry.get('name', entry.get('title', '未命名'))

            # 提取分类（兼容多种字段名）
            category = entry.get('category', entry.get('type', '世界观设定'))

            # 提取描述（兼容多种字段名）
            description = entry.get('description', entry.get('content', ''))

            # 提取要素
            elements = entry.get('elements', '')

            # 如果没有elements，使用description作为elements
            if not elements and description:
                elements = description[:100] + '...' if len(description) > 100 else description

            # 如果没有description，使用elements作为description
            if not description and elements:
                description = elements

            # 提取状态和修改时间
            status = entry.get('status', '已保存')
            modified = entry.get('modified', current_time)

            entries.append({
                'name': name,
                'category': category,
                'description': description,
                'elements': elements,
                'status': status,
                'modified': modified
            })

        return entries

    def _parse_markdown_format(self, content: str) -> List[Dict[str, Any]]:
        """解析Markdown格式"""
        entries = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')

        lines = content.split('\n')
        current_entry = None

        for line in lines:
            line = line.strip()

            # 检测条目标题（##或###开头）
            if line.startswith('##') or line.startswith('###'):
                # 保存上一个条目
                if current_entry:
                    entries.append(current_entry.copy())

                # 解析新条目
                title = re.sub(r'^#+\s*', '', line).strip()
                current_entry = {
                    'name': title,
                    'category': '世界观设定',
                    'description': '',
                    'elements': '',
                    'status': '已保存',
                    'modified': current_time
                }
            elif current_entry and line:
                # 添加条目内容
                if current_entry['elements']:
                    current_entry['elements'] += '\n' + line
                else:
                    current_entry['elements'] = line
                current_entry['description'] = current_entry['elements']

        # 保存最后一个条目
        if current_entry:
            entries.append(current_entry)

        return entries
