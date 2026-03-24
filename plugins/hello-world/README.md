# Hello World

> **插件ID**: `hello-world`
> **版本**: 1.0.0
> **类型**: 工具插件 (Tool)

---

## 用途

示例ToolPlugin插件，提供基础问候功能，用于验证插件系统流程和作为开发参考模板。

### 核心功能

- **问候功能**: 返回问候消息
- **状态查询**: 查询插件状态
- **配置演示**: 演示配置读取

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `greeting` | string | "Hello" | 问候语 |
| `language` | string | "zh" | 语言 |

### 配置示例

```yaml
plugins:
  hello-world:
    greeting: "你好"
    language: "zh"
```

---

## 使用示例

### 1. 基本用法

```python
from core.service_locator import ServiceLocator
from core.plugin_registry import PluginRegistry

# 获取插件
registry = ServiceLocator.get(PluginRegistry)
hello = registry.get_plugin("hello-world")

# 执行问候
result = hello.say_hello(name="World")
print(result)  # "Hello, World!"
```

### 2. 获取状态

```python
# 获取插件状态
status = hello.get_status()
print(status)
# {
#     "id": "hello-world",
#     "name": "Hello World",
#     "version": "1.0.0",
#     "enabled": True,
#     "initialized": True
# }
```

### 3. 配置演示

```python
# 设置配置
hello.set_config({"greeting": "你好", "language": "zh"})

# 使用新配置
result = hello.say_hello(name="世界")
print(result)  # "你好, 世界!"
```

---

## 输入输出

### 输入

```python
{
    "name": "World"  # 名字
}
```

### 输出

```python
@dataclass
class HelloResult:
    message: str        # 问候消息
    timestamp: datetime # 时间戳
    config: dict        # 使用的配置
```

---

## 依赖

- 无

---

## 冲突

- 无

---

## 权限要求

- 无

---

## 作为开发模板

此插件可作为新插件开发的参考模板：

```
plugins/
└── hello-world/
    ├── plugin.json      # 插件清单
    ├── __init__.py      # 包初始化
    ├── plugin.py        # 插件实现
    └── README.md        # 说明文档
```

### 最小实现

```python
# plugin.py
from core.base_plugin import BasePlugin
from core.plugin_context import PluginContext
from core.plugin_metadata import PluginMetadata

class HelloWorldPlugin(BasePlugin):
    """Hello World示例插件"""
    
    @staticmethod
    def get_metadata() -> PluginMetadata:
        return PluginMetadata(
            id="hello-world",
            name="Hello World",
            version="1.0.0",
            description="示例ToolPlugin插件",
            author="Agent Pro团队",
            plugin_type=PluginType.TOOL
        )
    
    def initialize(self, context: PluginContext) -> bool:
        """初始化插件"""
        self._config = {"greeting": "Hello"}
        return True
    
    def shutdown(self) -> None:
        """关闭插件"""
        pass
    
    def say_hello(self, name: str) -> str:
        """问候"""
        return f"{self._config['greeting']}, {name}!"
```

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-03-21 | 初始版本 |
