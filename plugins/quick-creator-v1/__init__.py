"""
快捷创作生成器插件 V1.3

快速生成世界观、大纲、人设、关键情节等设定。

V1.1新增：
- LLM调用超时保护机制
- 缓存持久化机制
- 自定义异常类型

V1.2新增：
- 参考文本解析模块
- 参考元素融合到生成Prompt

V1.3新增：
- 结果保存到新项目文件
- 导入到当前项目（冲突处理）
- JSON Schema定义
"""

from .plugin import (
    QuickCreationPlugin,
    CreationType,
    GenerationType,
    PromptTemplate,
    QuickCreationError,
    QuickCreationTimeoutError,
    QuickCreationAPIError,
    QuickCreationParseError
)

from .reference_parser import (
    ReferenceTextParser,
    ReferenceFusion,
    ReferenceType,
    WorldviewElements,
    CharacterElements,
    PlotElements,
    ParsedReference
)

from .result_storage import (
    ResultStorageManager,
    ConflictStrategy,
    ConflictInfo,
    ImportResult,
    StorageError,
    save_quick_creation_result,
    import_quick_creation_result,
    WORLDVIEW_SCHEMA,
    OUTLINE_SCHEMA,
    CHARACTER_SCHEMA,
    PLOT_SCHEMA,
    SCHEMA_VERSION
)

__all__ = [
    # 插件主类
    "QuickCreationPlugin",
    "CreationType",
    "GenerationType",
    "PromptTemplate",
    
    # 异常类型
    "QuickCreationError",
    "QuickCreationTimeoutError",
    "QuickCreationAPIError",
    "QuickCreationParseError",
    
    # 参考文本解析
    "ReferenceTextParser",
    "ReferenceFusion",
    "ReferenceType",
    "WorldviewElements",
    "CharacterElements",
    "PlotElements",
    "ParsedReference",
    
    # 结果存储
    "ResultStorageManager",
    "ConflictStrategy",
    "ConflictInfo",
    "ImportResult",
    "StorageError",
    "save_quick_creation_result",
    "import_quick_creation_result",
    
    # JSON Schema
    "WORLDVIEW_SCHEMA",
    "OUTLINE_SCHEMA",
    "CHARACTER_SCHEMA",
    "PLOT_SCHEMA",
    "SCHEMA_VERSION"
]
