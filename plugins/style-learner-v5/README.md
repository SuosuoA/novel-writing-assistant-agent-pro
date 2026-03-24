# 风格学习器 V5

> **插件ID**: `style-learner-v5`
> **版本**: 5.0.0
> **类型**: 分析器插件 (Analyzer)

---

## 用途

深度风格分析器，从参考文本中学习作者写作风格，为后续生成提供风格指导。

### 核心功能

- **词汇特征分析**: 分析词汇选择偏好、频率、多样性
- **句式模式识别**: 识别常用句式结构、长短句分布
- **修辞手法检测**: 检测比喻、拟人、排比等修辞手法
- **情感色彩分析**: 分析情感倾向、基调
- **语言风格画像**: 生成完整的风格画像

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `sample_size` | int | 50000 | 分析样本字数 |
| `cache_enabled` | bool | true | 是否缓存风格画像 |
| `min_samples` | int | 10000 | 最小样本字数 |
| `detail_level` | string | "full" | 分析详细程度 (basic/normal/full) |

### 配置示例

```yaml
plugins:
  style-learner-v5:
    sample_size: 50000
    cache_enabled: true
    min_samples: 10000
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
learner = registry.get_plugin("style-learner-v5")

# 学习文本风格
style_profile = learner.learn_from_text("""
    参考文本内容...
    至少需要10000字以上的样本
""")

print(f"风格画像: {style_profile.style_name}")
print(f"词汇多样性: {style_profile.vocabulary_diversity}")
```

### 2. 从文件学习

```python
# 从文件学习风格
style_profile = learner.learn_from_file("参考文本/作者作品.txt")

# 获取风格特征
features = style_profile.get_features()

# features 结构
# {
#     "vocabulary": {
#         "diversity": 0.85,
#         "average_word_length": 2.3,
#         "unique_ratio": 0.42
#     },
#     "sentence": {
#         "average_length": 25,
#         "short_ratio": 0.35,
#         "long_ratio": 0.15
#     },
#     "rhetoric": {
#         "metaphor_count": 12,
#         "personification_count": 5,
#         "parallelism_count": 8
#     },
#     "emotion": {
#         "positive_ratio": 0.6,
#         "negative_ratio": 0.2,
#         "neutral_ratio": 0.2
#     }
# }
```

### 3. 风格对比

```python
# 对比两个风格
profile_a = learner.learn_from_file("作者A.txt")
profile_b = learner.learn_from_file("作者B.txt")

similarity = learner.compare_styles(profile_a, profile_b)
print(f"风格相似度: {similarity:.2%}")
```

### 4. 应用风格指导生成

```python
# 将风格画像传递给生成器
generator = registry.get_plugin("novel-generator-v3")

generator.generate_chapter(
    chapter_number=1,
    style_profile=style_profile  # 应用学习到的风格
)
```

---

## 输入输出

### 输入

参考文本文件，建议：
- 样本量：10000字以上
- 格式：纯文本或Markdown
- 编码：UTF-8

### 输出

```python
@dataclass
class StyleProfile:
    style_id: str
    style_name: str
    vocabulary: VocabularyFeatures
    sentence: SentenceFeatures
    rhetoric: RhetoricFeatures
    emotion: EmotionFeatures
    overall_score: float
    created_at: datetime

@dataclass
class VocabularyFeatures:
    diversity: float          # 词汇多样性 0-1
    average_word_length: float
    unique_ratio: float       # 独特词比例
    frequent_words: List[str] # 高频词列表

@dataclass
class SentenceFeatures:
    average_length: float     # 平均句长
    short_ratio: float        # 短句比例
    long_ratio: float         # 长句比例
    patterns: List[str]       # 常用句式模式
```

---

## 依赖

- 无外部插件依赖

---

## 冲突

- `style-learner-v1`
- `style-learner-v2`

---

## 性能说明

| 样本量 | 分析时间 | 内存占用 |
|--------|---------|---------|
| 10K字 | ~2秒 | ~50MB |
| 50K字 | ~5秒 | ~100MB |
| 100K字 | ~10秒 | ~150MB |

---

## 注意事项

1. 样本量越大，风格画像越准确
2. 建议使用同一作者/风格的作品作为样本
3. 风格画像缓存在 `cache/styles/` 目录
4. 可同时保存多个风格画像供选择

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 5.0.0 | 2026-03-21 | 重构版本，增强修辞检测和情感分析 |
