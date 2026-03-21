"""
plugin.json Schema定义

V2.0最终版
创建日期：2026-03-21

用途：
- 插件清单文件的JSON Schema验证
- 与PluginMetadata类保持一致
- 符合架构设计说明书V1.2 4.4节
"""

from typing import Any, Dict, List, Optional

# plugin.json JSON Schema定义
PLUGIN_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://novel-writing-assistant-agent-pro.local/schemas/plugin.json",
    "title": "Plugin Manifest",
    "description": "Novel Writing Assistant-Agent Pro 插件清单Schema",
    "type": "object",
    "required": ["id", "name", "version", "plugin_type", "entry_class"],
    "properties": {
        "id": {
            "type": "string",
            "description": "插件唯一标识符（如：outline-parser-v3）",
            "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$",
            "minLength": 1,
            "maxLength": 64,
        },
        "name": {
            "type": "string",
            "description": "插件显示名称",
            "minLength": 1,
            "maxLength": 128,
        },
        "version": {
            "type": "string",
            "description": "版本号（语义化版本）",
            "pattern": "^\\d+\\.\\d+\\.\\d+(-[a-zA-Z0-9]+)?$",
            "examples": ["1.0.0", "2.1.0-beta", "3.0.0-rc1"],
        },
        "description": {
            "type": "string",
            "description": "插件功能描述",
            "default": "",
            "maxLength": 512,
        },
        "author": {
            "type": "string",
            "description": "插件作者",
            "default": "",
            "maxLength": 64,
        },
        "plugin_type": {
            "type": "string",
            "description": "插件类型",
            "enum": [
                "protocol",
                "ai",
                "storage",
                "analyzer",
                "generator",
                "validator",
                "tool",
            ],
        },
        "api_version": {
            "type": "string",
            "description": "API版本",
            "default": "1.0",
            "pattern": "^\\d+\\.\\d+$",
        },
        "priority": {
            "type": "integer",
            "description": "加载优先级（数值越小越先加载）",
            "default": 100,
            "minimum": 1,
            "maximum": 1000,
        },
        "enabled": {
            "type": "boolean",
            "description": "是否启用",
            "default": True,
        },
        "dependencies": {
            "type": "array",
            "description": "依赖插件ID列表",
            "items": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
            "default": [],
        },
        "conflicts": {
            "type": "array",
            "description": "冲突插件ID列表",
            "items": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
            "default": [],
        },
        "permissions": {
            "type": "array",
            "description": "所需权限列表",
            "items": {
                "type": "string",
                "enum": [
                    "file.read",
                    "file.write",
                    "network.request",
                    "database.read",
                    "database.write",
                    "system.execute",
                    "ai.call",
                ],
            },
            "default": [],
        },
        "min_platform_version": {
            "type": "string",
            "description": "最低平台版本",
            "default": "6.0.0",
            "pattern": "^\\d+\\.\\d+\\.\\d+$",
        },
        "entry_class": {
            "type": "string",
            "description": "入口类名",
            "minLength": 1,
            "maxLength": 128,
        },
    },
    "additionalProperties": False,
}

# 插件目录结构Schema
PLUGIN_DIR_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://novel-writing-assistant-agent-pro.local/schemas/plugin-directory.json",
    "title": "Plugin Directory Structure",
    "description": "插件目录结构验证",
    "type": "object",
    "required": ["plugin.json", "__init__.py"],
    "properties": {
        "plugin.json": {"type": "string", "description": "插件清单（必需）"},
        "__init__.py": {"type": "string", "description": "插件入口（必需）"},
        "plugin.py": {"type": "string", "description": "插件主类（推荐）"},
        "config_schema.json": {"type": "string", "description": "配置模式定义（可选）"},
        "requirements.txt": {"type": "string", "description": "依赖清单（可选）"},
        "README.md": {"type": "string", "description": "插件文档（推荐）"},
        "core": {"type": "string", "description": "核心实现目录"},
        "ui": {"type": "string", "description": "UI组件目录"},
        "assets": {"type": "string", "description": "静态资源目录"},
        "tests": {"type": "string", "description": "测试代码目录"},
    },
}


def validate_plugin_json(data: Dict[str, Any]) -> tuple[bool, List[str]]:
    """验证plugin.json数据

    Args:
        data: plugin.json解析后的字典

    Returns:
        (是否有效, 错误消息列表)
    """
    import jsonschema
    from jsonschema import ValidationError

    errors: List[str] = []

    try:
        jsonschema.validate(instance=data, schema=PLUGIN_JSON_SCHEMA)
    except ValidationError as e:
        errors.append(
            f"验证失败: {e.message} (path: {'.'.join(str(p) for p in e.path)})"
        )
        return False, errors

    # 额外业务逻辑验证
    plugin_id = data.get("id", "")

    # 检查V5保护模块ID冲突
    from .plugin_interface import V5_PROTECTED_MODULES, is_v5_protected_module

    if plugin_id in V5_PROTECTED_MODULES:
        errors.append(f"插件ID '{plugin_id}' 是V5保护模块，不可使用")

    # 检查依赖是否存在
    dependencies = data.get("dependencies", [])
    for dep in dependencies:
        if dep == plugin_id:
            errors.append(f"插件不能依赖自身: {plugin_id}")

    # 检查冲突列表是否包含自身
    conflicts = data.get("conflicts", [])
    if plugin_id in conflicts:
        errors.append(f"插件不能与自身冲突: {plugin_id}")

    return len(errors) == 0, errors


# 示例plugin.json
PLUGIN_JSON_EXAMPLE: Dict[str, Any] = {
    "id": "outline-parser-v3",
    "name": "大纲解析器 V3",
    "version": "3.0.0",
    "description": "基于LangChain的智能大纲解析",
    "author": "项目组",
    "plugin_type": "analyzer",
    "api_version": "1.0",
    "priority": 100,
    "enabled": True,
    "dependencies": [],
    "conflicts": [],
    "permissions": ["file.read"],
    "min_platform_version": "6.0.0",
    "entry_class": "OutlineParserPlugin",
}
