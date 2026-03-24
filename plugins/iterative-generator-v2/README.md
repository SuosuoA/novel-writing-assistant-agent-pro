# 迭代生成器 V2

> **插件ID**: `iterative-generator-v2`
> **版本**: 2.0.0
> **类型**: 生成器插件 (Generator)

---

## 用途

迭代优化的章节生成器，通过评分反馈循环机制不断优化生成内容，直到达到质量阈值。

### 核心功能

- **迭代生成**: 基于评分反馈的循环优化
- **多维度评分**: 6维度加权评分（字数/大纲/风格/人设/世界观/自然度）
- **自动重试**: 不达标自动重试（最多5次）
- **进度追踪**: 实时追踪迭代进度

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `model_name` | string | "deepseek-chat" | LLM模型名称 |
| `target_word_count` | int | 3000 | 目标字数 |
| `quality_threshold` | float | 0.8 | 质量阈值 |
| `max_iterations` | int | 5 | 最大迭代次数 |
| `temperature` | float | 0.7 | 生成温度 |

### 配置示例

```yaml
plugins:
  iterative-generator-v2:
    model_name: "deepseek-chat"
    target_word_count: 3000
    quality_threshold: 0.8
    max_iterations: 5
    temperature: 0.7
```

---

## 使用示例

### 1. 基本用法

```python
from core.service_locator import ServiceLocator
from core.plugin_registry import PluginRegistry

# 获取插件
registry = ServiceLocator.get(PluginRegistry)
generator = registry.get_plugin("iterative-generator-v2")

# 生成章节
result = generator.generate(
    chapter_number=1,
    outline="第一章 序章: 少年初入修真界",
    context="...",  # 上下文（由context-builder提供）
    style_profile={...}  # 风格画像（可选）
)

if result.success:
    print(f"生成成功，字数: {result.word_count}")
    print(f"迭代次数: {result.iterations}")
    print(f"最终评分: {result.final_score:.2f}")
else:
    print(f"生成失败: {result.error}")
```

### 2. 带进度回调

```python
def on_progress(iteration: int, score: float, content: str):
    print(f"第{iteration}次迭代，评分: {score:.2f}")

result = generator.generate(
    chapter_number=1,
    outline="...",
    context="...",
    progress_callback=on_progress
)
```

### 3. 获取评分详情

```python
# 生成后获取评分详情
scores = generator.get_score_details(result.generation_id)

print(f"字数评分: {scores.word_count:.2f} (权重10%)")
print(f"大纲评分: {scores.outline:.2f} (权重15%)")
print(f"风格评分: {scores.style:.2f} (权重25%)")
print(f"人设评分: {scores.character:.2f} (权重25%)")
print(f"世界观评分: {scores.worldview:.2f} (权重20%)")
print(f"自然度评分: {scores.naturalness:.2f} (权重5%)")
print(f"综合评分: {scores.overall:.2f}")
```

### 4. 配置运行时参数

```python
# 运行时设置配置
generator.set_config({
    "target_word_count": 5000,
    "quality_threshold": 0.85,
    "max_iterations": 3
})

# 生成
result = generator.generate(...)
```

---

## 输入输出

### 输入

```python
{
    "chapter_number": 1,
    "outline": "第一章 序章: 少年初入修真界",
    "context": "...",  # 由context-builder构建
    "style_profile": {...},  # 可选
    "characters": ["李明", "王芳"],  # 可选
    "worldview": {...}  # 可选
}
```

### 输出

```python
@dataclass
class GenerationResult:
    success: bool
    content: str                    # 生成的内容
    word_count: int                 # 实际字数
    iterations: int                 # 迭代次数
    final_score: float              # 最终评分
    generation_id: str              # 生成ID
    error: Optional[str]            # 错误信息

@dataclass
class ScoreDetails:
    word_count: float      # 字数评分 (权重10%)
    outline: float         # 大纲评分 (权重15%)
    style: float           # 风格评分 (权重25%)
    character: float       # 人设评分 (权重25%)
    worldview: float       # 世界观评分 (权重20%)
    naturalness: float     # 自然度评分 (权重5%)
    overall: float         # 综合评分
```

---

## 依赖

- `quality-validator-v1` (质量验证器)

---

## 冲突

- 无

---

## 权限要求

- `ai.call`
- `file.write`

---

## 评分维度说明

| 维度 | 权重 | 说明 |
|------|------|------|
| 字数 | 10% | 是否达到目标字数 |
| 大纲 | 15% | 是否符合大纲设定 |
| 风格 | 25% | 是否符合风格画像 |
| 人设 | 25% | 人物行为是否符合设定 |
| 世界观 | 20% | 是否遵循世界观规则 |
| 自然度 | 5% | 文笔是否自然流畅 |

---

## 注意事项

1. 质量阈值默认0.8，可根据需求调整
2. 最大迭代5次，避免无限循环
3. 历史记录限制50条，超过自动截断
4. 生成内容缓存在 `cache/generations/` 目录

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 2.0.0 | 2026-03-21 | 重构版本，优化迭代算法 |
