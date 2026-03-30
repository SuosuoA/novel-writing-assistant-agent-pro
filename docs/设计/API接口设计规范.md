# API接口设计规范 - Novel Writing Assistant-Agent Pro

> **版本**: V1.0  
> **更新日期**: 2026-03-26  
> **设计原则**: RESTful + 事件驱动

---

## 一、API架构

### 1.1 API类型

| API类型 | 用途 | 实现 |
|--------|------|------|
| 内部API | 模块间通信 | Python函数调用 |
| 插件API | 插件与核心通信 | BasePlugin接口 |
| LLM API | AI服务调用 | openai SDK |
| 向量API | 向量检索 | LanceDB API |

### 1.2 API设计原则

**RESTful原则**：
- 资源命名：名词而非动词
- HTTP方法：GET查询、POST创建、PUT更新、DELETE删除
- 状态码：正确使用HTTP状态码

**事件驱动**：
- 解耦模块通信
- 异步处理耗时操作
- 发布订阅模式

---

## 二、核心API设计

### 2.1 EventBus API

**事件发布**：
```python
# 发布事件
event_bus.publish(
    event_type="chapter.generated",
    data={
        "chapter_id": "chapter-001",
        "word_count": 3000,
        "generation_time": 2.5
    },
    source="NovelGenerationAgent"
)
```

**事件订阅**：
```python
# 订阅事件
event_bus.subscribe(
    event_type="chapter.generated",
    callback=on_chapter_generated
)

def on_chapter_generated(event_type, data, source):
    print(f"章节生成完成: {data['chapter_id']}")
```

**事件格式**：
```json
{
    "type": "chapter.generated",
    "source": "NovelGenerationAgent",
    "data": {
        "chapter_id": "chapter-001",
        "word_count": 3000,
        "generation_time": 2.5
    },
    "timestamp": "2026-03-26T10:00:00.000000"
}
```

### 2.2 PluginRegistry API

**注册插件**：
```python
# 注册插件
registry.register(plugin_metadata)
```

**获取插件**：
```python
# 获取插件实例
plugin = registry.get_plugin("outline-parser-v3")
```

**执行插件**：
```python
# 执行插件操作
result = registry.execute_plugin(
    plugin_id="outline-parser-v3",
    operation="parse",
    payload={"outline_text": "..."}
)
```

**激活/停用插件**：
```python
# 激活插件
registry.activate("outline-parser-v3")

# 停用插件
registry.deactivate("outline-parser-v3")
```

### 2.3 ServiceLocator API

**注册服务**：
```python
# 注册单例服务
locator.register_singleton(EventBus, event_bus)
locator.register_singleton(PluginRegistry, registry)
```

**获取服务**：
```python
# 获取服务实例
event_bus = locator.get_service(EventBus)
registry = locator.get_service(PluginRegistry)
```

### 2.4 ConfigManager API

**读取配置**：
```python
# 读取配置值
api_key = config.get("api_key")
model = config.get("model", default="deepseek-chat")
```

**更新配置**：
```python
# 更新配置值
config.set("model", "gpt-4")
config.save()  # 持久化到文件
```

**监听配置变更**：
```python
# 添加监听器
config.add_listener(on_config_changed)

def on_config_changed(key, old_value, new_value):
    print(f"配置变更: {key} = {new_value}")
```

---

## 三、LLM API设计

### 3.1 AIProvider接口

**抽象基类**：
```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable

class AIProvider(ABC):
    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        config: GenerationConfig,
        messages: Optional[List[Dict]] = None
    ) -> GenerationResult:
        """生成文本"""
        pass
    
    @abstractmethod
    def generate_text_stream(
        self,
        prompt: str,
        config: GenerationConfig,
        callback: Callable[[str], None],
        messages: Optional[List[Dict]] = None
    ) -> GenerationResult:
        """流式生成文本"""
        pass
    
    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """估算Token数量"""
        pass
    
    @abstractmethod
    def get_model_info(self) -> AIModelInfo:
        """获取模型信息"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查服务可用性"""
        pass
```

### 3.2 GenerationConfig

**配置模型**：
```python
from pydantic import BaseModel, Field

class GenerationConfig(BaseModel):
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(4096, ge=1, le=128000)
    top_p: float = Field(0.9, ge=0.0, le=1.0)
    frequency_penalty: float = Field(0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(0.0, ge=-2.0, le=2.0)
    stop: Optional[List[str]] = None
    stream: bool = False
    timeout: int = Field(120, ge=1, le=600)
```

### 3.3 GenerationResult

**结果模型**：
```python
from pydantic import BaseModel
from typing import Optional, Dict, Any

class GenerationResult(BaseModel):
    success: bool
    text: Optional[str] = None
    error: Optional[str] = None
    usage: Optional[Dict[str, int]] = None  # {"prompt_tokens": 100, "completion_tokens": 500}
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
```

### 3.4 AIServiceManager

**统一管理器**：
```python
class AIServiceManager:
    def __init__(self):
        self._provider: Optional[AIProvider] = None
        self._config_hash: Optional[str] = None
        self._provider_lock = threading.RLock()
    
    def generate_text(self, prompt: str, config: GenerationConfig, messages: Optional[List[Dict]] = None) -> GenerationResult:
        """生成文本"""
        provider = self._get_or_create_provider()
        return provider.generate_text(prompt, config, messages)
    
    def generate_text_stream(self, prompt: str, config: GenerationConfig, callback: Callable[[str], None], messages: Optional[List[Dict]] = None) -> GenerationResult:
        """流式生成文本"""
        provider = self._get_or_create_provider()
        return provider.generate_text_stream(prompt, config, callback, messages)
    
    def get_provider_type(self) -> AIProviderType:
        """获取当前Provider类型"""
        return self._provider.provider_type if self._provider else None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_calls": self._total_calls,
            "total_errors": self._total_errors,
            "provider_switch_count": self._provider_switch_count,
            "provider_type": self.get_provider_type()
        }
```

---

## 四、向量检索API设计

### 4.1 VectorStore API

**添加章节向量**：
```python
# 添加单个章节
vector_store.add_chapter(
    chapter_id="chapter-001",
    content="第一章内容...",
    metadata={"title": "开篇", "word_count": 3000}
)

# 批量添加章节
vector_store.add_chapters_batch([
    {"chapter_id": "chapter-001", "content": "...", "metadata": {...}},
    {"chapter_id": "chapter-002", "content": "...", "metadata": {...}}
])
```

**召回相似章节**：
```python
# 召回top-10相似章节
results = vector_store.recall_similar_chapters(
    query="星际飞船穿越虫洞",
    top_k=10
)

# 结果格式
# [
#     VectorSearchResult(id="chapter-005", content="...", score=0.95, metadata={...}),
#     VectorSearchResult(id="chapter-003", content="...", score=0.89, metadata={...}),
#     ...
# ]
```

**添加知识向量**：
```python
# 添加知识点
vector_store.add_knowledge(
    knowledge_id="scifi-physics-001",
    category="scifi",
    domain="physics",
    title="时间膨胀效应",
    content="根据狭义相对论...",
    keywords=["相对论", "时间", "光速"]
)
```

**召回知识**：
```python
# 召回相关知识
results = vector_store.recall_knowledge(
    query="飞船接近光速会发生什么",
    category="scifi",
    domain="physics",
    top_k=10
)
```

### 4.2 KnowledgeRetriever API

**向量检索**：
```python
# 向量检索
results = retriever.recall_knowledge(
    query="时间膨胀效应",
    category="scifi",
    top_k=10
)
```

**混合检索**：
```python
# 混合检索（向量+关键词）
results = retriever.hybrid_search(
    query="时间膨胀效应",
    category="scifi",
    domain="physics",
    top_k=10
)
```

**上下文召回**：
```python
# 为上下文召回知识（格式化文本）
context = retriever.recall_for_context(
    context="星际战争爆发，人类舰队需要穿越虫洞",
    category="scifi",
    top_k=3
)

# 返回格式：
# """
# 【知识1：时间膨胀效应】
# 根据狭义相对论，当物体接近光速时，时间流逝会变慢...
# 
# 【知识2：虫洞理论】
# 虫洞是连接时空两个点的理论通道...
# """
```

---

## 五、Agent API设计

### 5.1 BaseAgent接口

**抽象基类**：
```python
from abc import ABC, abstractmethod

class BaseAgent(ABC):
    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Agent类型标识"""
        pass
    
    @property
    @abstractmethod
    def capabilities(self) -> List[AgentCapability]:
        """Agent能力列表"""
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """初始化Agent"""
        pass
    
    @abstractmethod
    def execute(self, task_id: str, payload: Dict[str, Any], context: AgentContext) -> AgentResult:
        """执行任务"""
        pass
    
    @abstractmethod
    def can_handle(self, task_type: str, payload: Dict[str, Any]) -> bool:
        """判断是否能处理任务"""
        pass
    
    @abstractmethod
    def cleanup(self) -> bool:
        """清理资源"""
        pass
```

### 5.2 AgentContext

**上下文模型**：
```python
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

class AgentContext(BaseModel):
    task_id: str
    session_id: Optional[str] = None
    conversation_history: List[Dict[str, str]] = []
    shared_memory: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
```

### 5.3 AgentResult

**结果模型**：
```python
from pydantic import BaseModel
from typing import Dict, Any, Optional

class AgentResult(BaseModel):
    success: bool
    task_id: str
    agent_type: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}
    confidence: Optional[float] = None
```

### 5.4 MasterAgent API

**任务提交**：
```python
# 提交任务
task_id = master_agent.submit_task(
    task_type="novel_generation",
    payload={
        "chapter_number": 1,
        "outline": "...",
        "characters": [...],
        "worldview": "..."
    },
    priority=TaskPriority.NORMAL
)
```

**任务查询**：
```python
# 查询任务状态
status = master_agent.get_task_status(task_id)

# 获取任务结果
result = master_agent.get_task_result(task_id)
```

**任务取消**：
```python
# 取消任务
success = master_agent.cancel_task(task_id)
```

---

## 六、事件类型定义

### 6.1 核心事件

| 事件类型 | 数据格式 | 发布者 | 订阅者 |
|---------|---------|--------|--------|
| `core.initialized` | `{"version": "V1.10.0"}` | BootstrapService | UI、Agent |
| `core.shutdown` | `{}` | MainWindow | 所有模块 |
| `config.changed` | `{"key": "model", "old": "deepseek-chat", "new": "gpt-4"}` | ConfigManager | AIServiceManager |

### 6.2 插件事件

| 事件类型 | 数据格式 | 发布者 | 订阅者 |
|---------|---------|--------|--------|
| `plugin.loaded` | `{"plugin_id": "outline-parser-v3"}` | PluginRegistry | UI |
| `plugin.activated` | `{"plugin_id": "outline-parser-v3"}` | PluginRegistry | UI |
| `plugin.deactivated` | `{"plugin_id": "outline-parser-v3"}` | PluginRegistry | UI |
| `plugin.error` | `{"plugin_id": "...", "error": "..."}` | PluginRegistry | 监控系统 |

### 6.3 Agent事件

| 事件类型 | 数据格式 | 发布者 | 订阅者 |
|---------|---------|--------|--------|
| `agent.task.submitted` | `{"task_id": "...", "task_type": "..."}` | MasterAgent | UI |
| `agent.task.started` | `{"task_id": "...", "agent_type": "..."}` | Agent | UI |
| `agent.task.completed` | `{"task_id": "...", "success": true}` | Agent | UI |
| `agent.task.failed` | `{"task_id": "...", "error": "..."}` | Agent | UI |

### 6.4 生成事件

| 事件类型 | 数据格式 | 发布者 | 订阅者 |
|---------|---------|--------|--------|
| `generation.started` | `{"chapter_id": "...", "iteration": 0}` | NovelGenerationAgent | UI |
| `generation.iteration` | `{"iteration": 1, "score": 0.75}` | IterativeGenerator | UI |
| `generation.completed` | `{"chapter_id": "...", "word_count": 3000}` | NovelGenerationAgent | UI |
| `generation.failed` | `{"chapter_id": "...", "error": "..."}` | NovelGenerationAgent | UI |

### 6.5 记忆事件

| 事件类型 | 数据格式 | 发布者 | 订阅者 |
|---------|---------|--------|--------|
| `session.state.updated` | `{"region": "active_task"}` | SessionStateManager | 监控系统 |
| `session.state.recovered` | `{"recovered": true}` | SessionStateManager | UI |
| `wal.write.success` | `{"record_id": "..."}` | WALManager | 监控系统 |
| `wal.write.failed` | `{"error": "..."}` | WALManager | 监控系统 |
| `knowledge.retrieval.completed` | `{"query": "...", "count": 10}` | KnowledgeRetriever | 监控系统 |
| `knowledge.consistency.checked` | `{"score": 0.9, "conflicts": 0}` | KnowledgeRecall | 监控系统 |

---

## 七、错误处理规范

### 7.1 错误类型

**错误分类**：
```python
from enum import Enum

class ErrorType(Enum):
    VALIDATION_ERROR = "validation_error"      # 输入验证错误
    NOT_FOUND_ERROR = "not_found_error"        # 资源未找到
    PERMISSION_ERROR = "permission_error"       # 权限错误
    RATE_LIMIT_ERROR = "rate_limit_error"       # 速率限制
    TIMEOUT_ERROR = "timeout_error"             # 超时错误
    CONNECTION_ERROR = "connection_error"       # 连接错误
    INTERNAL_ERROR = "internal_error"           # 内部错误
```

### 7.2 错误响应格式

**统一错误格式**：
```python
from pydantic import BaseModel
from typing import Optional, Dict, Any

class ErrorResponse(BaseModel):
    error_type: ErrorType
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: str
    request_id: Optional[str] = None
```

### 7.3 异常处理

**示例**：
```python
def execute_plugin(plugin_id: str, operation: str, payload: Dict[str, Any]) -> Any:
    try:
        plugin = registry.get_plugin(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(f"Plugin {plugin_id} not found")
        
        result = plugin.execute(operation, payload)
        
        if not result.success:
            raise PluginExecutionError(result.error)
        
        return result.data
    
    except PluginNotFoundError as e:
        logger.error(f"Plugin not found: {plugin_id}")
        event_bus.publish("plugin.error", {"plugin_id": plugin_id, "error": str(e)})
        raise
    
    except PluginExecutionError as e:
        logger.error(f"Plugin execution failed: {e}")
        raise
    
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        raise
```

---

## 八、性能优化

### 8.1 批量操作

**批量API**：
```python
# 批量添加章节向量
vector_store.add_chapters_batch(chapters_list)

# 批量导入知识点
knowledge_manager.import_from_json(json_file)
```

### 8.2 异步处理

**异步API**：
```python
# 异步生成文本
def generate_text_async(prompt: str, config: GenerationConfig, callback: Callable[[GenerationResult], None]):
    def task():
        result = ai_manager.generate_text(prompt, config)
        root.after(0, lambda: callback(result))
    
    threading.Thread(target=task, daemon=True).start()
```

### 8.3 缓存策略

**API缓存**：
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_plugin_metadata(plugin_id: str) -> PluginMetadata:
    return registry.get_metadata(plugin_id)
```

---

## 九、API版本控制

### 9.1 版本号格式

- **主版本**：重大变更，不兼容旧版本
- **次版本**：新增功能，向后兼容
- **修订版本**：Bug修复，向后兼容

### 9.2 版本废弃策略

**废弃流程**：
1. 标记为deprecated（保留6个月）
2. 发布迁移指南
3. 6个月后移除

---

**最后更新**: 2026-03-26  
**维护者**: 后端架构师、高级开发工程师
