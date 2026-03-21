"""
Hello World插件 - 示例ToolPlugin实现

版本: 1.0.0
创建日期: 2026-03-21
作者: Agent Pro团队

功能:
- 实现greet操作，返回问候语
- 演示ToolPlugin接口的正确实现
- 验证插件系统发现、加载、初始化和执行流程

参考文档:
- 《项目总体架构设计说明书V1.3》第四章
- 《插件接口定义V2.1》
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

# 添加项目根目录到sys.path（支持直接运行测试）
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.plugin_interface import ToolPlugin, PluginMetadata, PluginType, PluginContext


class HelloWorldPlugin(ToolPlugin):
    """Hello World工具插件

    实现ToolPlugin接口，提供greet操作。

    操作列表:
    - greet: 返回问候语
        参数:
        - name: str - 用户名（可选，默认"World"）
        - language: str - 语言（可选，默认"zh"，支持"zh"/"en"）

    示例:
        >>> plugin = HelloWorldPlugin()
        >>> result = plugin.execute("greet", {"name": "Alice", "language": "en"})
        >>> print(result["message"])
        "Hello, Alice! Welcome to Agent Pro."
    """

    # 类常量
    PLUGIN_ID = "hello-world"
    PLUGIN_NAME = "Hello World"
    PLUGIN_VERSION = "1.0.0"

    def __init__(self):
        """初始化插件"""
        metadata = PluginMetadata(
            id=self.PLUGIN_ID,
            name=self.PLUGIN_NAME,
            version=self.PLUGIN_VERSION,
            description="示例ToolPlugin插件，提供问候功能",
            author="Agent Pro团队",
            plugin_type=PluginType.TOOL,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=[],
            permissions=[],
            min_platform_version="1.0.0",
            entry_class="HelloWorldPlugin",
        )
        super().__init__(metadata)
        self._greet_count = 0  # 统计问候次数

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据（类方法）

        Returns:
            插件元数据对象
        """
        return PluginMetadata(
            id=cls.PLUGIN_ID,
            name=cls.PLUGIN_NAME,
            version=cls.PLUGIN_VERSION,
            description="示例ToolPlugin插件，提供问候功能",
            author="Agent Pro团队",
            plugin_type=PluginType.TOOL,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=[],
            permissions=[],
            min_platform_version="1.0.0",
            entry_class="HelloWorldPlugin",
        )

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件

        Args:
            context: 插件上下文（包含EventBus、ConfigManager等）

        Returns:
            是否初始化成功
        """
        # 调用父类初始化
        if not super().initialize(context):
            return False

        # 订阅事件（示例：监听插件加载事件）
        if self._context and self._context.event_bus:
            self._context.event_bus.subscribe(
                "plugin.loaded",
                self._on_plugin_loaded,
                handler_id=f"{self.PLUGIN_ID}.plugin_loaded",
            )

        # 记录初始化成功
        self._greet_count = 0
        return True

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具操作

        Args:
            action: 操作名称
            params: 操作参数

        Returns:
            执行结果字典

        Raises:
            ValueError: 不支持的操作
        """
        if action == "greet":
            return self._greet(params)
        else:
            raise ValueError(f"不支持的操作: {action}")

    def _greet(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行问候操作

        Args:
            params: 操作参数
                - name: 用户名（可选，默认"World"）
                - language: 语言（可选，默认"zh"，支持"zh"/"en"）

        Returns:
            结果字典:
                - success: bool - 是否成功
                - message: str - 问候语
                - greet_count: int - 问候次数
        """
        # 提取参数
        name = params.get("name", "World")
        language = params.get("language", "zh")

        # 参数验证
        if not isinstance(name, str) or not name.strip():
            name = "World"

        if language not in ["zh", "en"]:
            language = "zh"

        # 生成问候语
        if language == "zh":
            message = f"你好，{name}！欢迎使用 Agent Pro。"
        else:
            message = f"Hello, {name}! Welcome to Agent Pro."

        # 更新计数
        self._greet_count += 1

        # 返回结果
        return {
            "success": True,
            "message": message,
            "greet_count": self._greet_count,
            "language": language,
            "plugin_id": self.PLUGIN_ID,
            "plugin_version": self.PLUGIN_VERSION,
        }

    def _on_plugin_loaded(self, event):
        """处理插件加载事件

        Args:
            event: 事件对象
        """
        plugin_id = event.data.get("plugin_id") if event.data else None
        if plugin_id and plugin_id != self.PLUGIN_ID:
            if self._context and self._context.logger:
                self._context.logger.info(
                    f"[{self.PLUGIN_ID}] 检测到插件加载: {plugin_id}"
                )

    def shutdown(self) -> bool:
        """关闭插件 - 优雅关闭

        Returns:
            是否关闭成功
        """
        # 取消事件订阅
        if self._context and self._context.event_bus:
            self._context.event_bus.unsubscribe(f"{self.PLUGIN_ID}.plugin_loaded")

        # 记录统计信息
        if self._context and self._context.logger:
            self._context.logger.info(
                f"[{self.PLUGIN_ID}] 插件关闭，累计问候次数: {self._greet_count}"
            )

        return super().shutdown()

    def get_supported_actions(self) -> list[str]:
        """获取支持的操作列表

        Returns:
            操作名称列表
        """
        return ["greet"]

    def get_action_schema(self, action: str) -> Optional[Dict[str, Any]]:
        """获取操作的参数模式

        Args:
            action: 操作名称

        Returns:
            参数模式字典，不支持的操作返回None
        """
        if action == "greet":
            return {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "用户名",
                        "default": "World",
                    },
                    "language": {
                        "type": "string",
                        "description": "语言",
                        "enum": ["zh", "en"],
                        "default": "zh",
                    },
                },
                "required": [],
            }
        return None


# ============================================================================
# 模块级函数（供插件加载器使用）
# ============================================================================


def get_plugin_class():
    """获取插件类（供插件加载器调用）

    Returns:
        插件类
    """
    return HelloWorldPlugin


def register_plugin():
    """注册插件（供插件加载器调用）

    Returns:
        插件类
    """
    return HelloWorldPlugin


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    # 简单测试
    print("=" * 60)
    print("Hello World 插件测试")
    print("=" * 60)

    # 创建插件实例
    plugin = HelloWorldPlugin()
    print(f"\n1. 插件元数据:")
    print(f"   ID: {plugin.metadata.id}")
    print(f"   名称: {plugin.metadata.name}")
    print(f"   版本: {plugin.metadata.version}")
    print(f"   类型: {plugin.metadata.plugin_type.value}")

    # 测试execute方法
    print(f"\n2. 测试greet操作:")

    result1 = plugin.execute("greet", {"name": "Alice", "language": "en"})
    print(f"   结果1: {result1['message']}")

    result2 = plugin.execute("greet", {"name": "张三", "language": "zh"})
    print(f"   结果2: {result2['message']}")

    result3 = plugin.execute("greet", {})
    print(f"   结果3: {result3['message']}")

    # 测试不支持的操作
    print(f"\n3. 测试不支持的操作:")
    try:
        plugin.execute("unknown", {})
    except ValueError as e:
        print(f"   预期错误: {e}")

    # 测试状态
    print(f"\n4. 插件状态:")
    print(f"   状态: {plugin.state.value}")
    print(f"   已初始化: {plugin.is_initialized}")
    print(f"   问候次数: {plugin._greet_count}")

    print(f"\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
