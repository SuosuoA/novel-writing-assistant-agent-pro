# 质量验证器 V1

> **插件ID**: `quality-validator-v1`
> **版本**: 1.0.0
> **类型**: 验证器插件 (Validator)

---

## 用途

6维度加权评分验证器，用于评估章节内容质量，为迭代生成提供反馈依据。

### 核心功能

- **6维度评分**: 字数/大纲/风格/人设/世界观/自然度
- **加权计算**: 根据权重计算综合评分
- **详细反馈**: 提供各项评分的详细说明
- **对比分析**: 对比不同版本的质量差异

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `weights` | dict | 见下文 | 各维度权重 |
| `threshold` | float | 0.8 | 通过阈值 |
| `detail_level` | string | "full" | 反馈详细程度 |

### 默认权重

```python
{
    "word_count": 0.10,    # 字数权重 10%
    "outline": 0.15,       # 大纲权重 15%
    "style": 0.25,         # 风格权重 25%
    "character": 0.25,     # 人设权重 25%
    "worldview": 0.20,     # 世界观权重 20%
    "naturalness": 0.05    # 自然度权重 5%
}
```

### 配置示例

```yaml
plugins:
  quality-validator-v1:
    weights:
      word_count: 0.10
      outline: 0.15
      style: 0.25
      character: 0.25
      worldview: 0.20
      naturalness: 0.05
    threshold: 0.8
    detail_level: "full"
```

---

## 使用示例

### 1. 基本用法

```python
from core.service_locator import ServiceLocator
from core.plugin_registry import PluginRegistry

# 获取插件
registry = ServiceLocator.get(PluginRegistry)
validator = registry.get_plugin("quality-validator-v1")

# 验证内容
result = validator.validate(
    content="生成的章节内容...",
    outline="第一章: 序章...",
    style_profile={...},
    characters=["李明", "王芳"],
    worldview={...},
    target_word_count=3000
)

print(f"综合评分: {result.overall_score:.2f}")
print(f"是否通过: {'是' if result.passed else '否'}")
```

### 2. 获取详细评分

```python
# 获取各维度评分
for dimension, score in result.dimension_scores.items():
    print(f"{dimension}: {score:.2f}")

# 输出:
# word_count: 0.85
# outline: 0.90
# style: 0.78
# character: 0.82
# worldview: 0.88
# naturalness: 0.92
```

### 3. 获取改进建议

```python
# 获取改进建议
if not result.passed:
    for suggestion in result.suggestions:
        print(f"建议: {suggestion.description}")
        print(f"影响维度: {suggestion.dimension}")
        print(f"预计提升: +{suggestion.expected_improvement:.2f}")
```

### 4. 批量验证

```python
# 批量验证多个章节
results = validator.validate_batch([
    {"content": "第一章内容...", "outline": "...", ...},
    {"content": "第二章内容...", "outline": "...", ...},
    {"content": "第三章内容...", "outline": "...", ...},
])

for chapter_num, result in results.items():
    print(f"第{chapter_num}章: {result.overall_score:.2f} ({'通过' if result.passed else '未通过'})")
```

---

## 输入输出

### 输入

```python
{
    "content": "生成的章节内容...",
    "outline": "第一章: 序章...",
    "style_profile": {...},  # 风格画像
    "characters": ["李明", "王芳"],  # 人物列表
    "worldview": {...},  # 世界观设定
    "target_word_count": 3000,  # 目标字数
    "previous_chapters": [...]  # 前几章内容（可选）
}
```

### 输出

```python
@dataclass
class ValidationResult:
    passed: bool                        # 是否通过
    overall_score: float                # 综合评分
    dimension_scores: Dict[str, float]  # 各维度评分
    suggestions: List[Suggestion]       # 改进建议
    validation_time: float              # 验证耗时

@dataclass
class Suggestion:
    dimension: str           # 维度
    description: str         # 建议描述
    expected_improvement: float  # 预计提升
    priority: int           # 优先级 1-5
```

---

## 依赖

- 无外部插件依赖

---

## 冲突

- `quality-validator-v2`

---

## 权限要求

- `file.read`

---

## 评分维度说明

### 字数评分 (10%)
- 评估是否达到目标字数
- 过少或过多都会扣分
- 合理范围: 目标字数 ± 20%

### 大纲评分 (15%)
- 评估内容是否符合大纲
- 检查关键情节是否覆盖
- 检查章节主题是否一致

### 风格评分 (25%)
- 评估是否符合风格画像
- 词汇选择、句式结构、修辞手法
- 情感色彩、语言风格

### 人设评分 (25%)
- 评估人物行为是否符合设定
- 人物性格一致性
- 人物关系一致性

### 世界观评分 (20%)
- 评估是否遵循世界观规则
- 设定一致性检查
- 魔法/修炼体系合理

### 自然度评分 (5%)
- 评估文笔是否自然流畅
- 避免机械感、重复感
- 衔接自然、节奏合理

---

## 注意事项

1. 阈值默认0.8，可根据需求调整
2. 权重总和必须为1.0
3. 评分基于规则+LLM混合评估
4. 建议与迭代生成器配合使用

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-03-21 | 初始版本 |
