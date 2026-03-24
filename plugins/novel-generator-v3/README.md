# 小说生成器 V3

> **插件ID**: `novel-generator-v3`
> **版本**: 3.0.0
> **类型**: 生成器插件 (Generator)

---

## 用途

小说章节生成器V3，整合上下文构建、迭代生成、加权验证的完整流程，是小说生成的核心入口插件。

### 核心功能

- **一站式生成**: 整合所有生成流程
- **依赖协调**: 自动协调context-builder、iterative-generator、quality-validator
- **批量生成**: 支持多章节批量生成
- **断点续传**: 支持中断后继续生成

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `model_name` | string | "deepseek-chat" | LLM模型名称 |
| `target_word_count` | int | 3000 | 目标字数 |
| `quality_threshold` | float | 0.8 | 质量阈值 |
| `max_iterations` | int | 5 | 最大迭代次数 |
| `auto_save` | bool | true | 自动保存生成结果 |

### 配置示例

```yaml
plugins:
  novel-generator-v3:
    model_name: "deepseek-chat"
    target_word_count: 3000
    quality_threshold: 0.8
    max_iterations: 5
    auto_save: true
```

---

## 使用示例

### 1. 单章生成

```python
from core.service_locator import ServiceLocator
from core.plugin_registry import PluginRegistry

# 获取插件
registry = ServiceLocator.get(PluginRegistry)
generator = registry.get_plugin("novel-generator-v3")

# 生成单章
result = generator.generate_chapter(
    chapter_number=1,
    outline_path="大纲/我的小说大纲.md",
    style_path="参考文本/作者作品.txt",
    characters_path="人物设定/",
    worldview_path="世界观/玄幻世界设定.md"
)

if result.success:
    print(f"生成成功: {result.word_count}字")
    print(f"保存路径: {result.output_path}")
```

### 2. 批量生成

```python
# 批量生成多章
results = generator.generate_chapters(
    start_chapter=1,
    end_chapter=10,
    outline_path="大纲/我的小说大纲.md",
    # ... 其他参数
)

for chapter_num, result in results.items():
    if result.success:
        print(f"第{chapter_num}章: 成功 ({result.word_count}字)")
    else:
        print(f"第{chapter_num}章: 失败 ({result.error})")
```

### 3. 带进度回调

```python
def on_progress(info: dict):
    print(f"正在生成第{info['chapter']}章")
    print(f"进度: {info['progress']:.0%}")
    print(f"当前阶段: {info['stage']}")

result = generator.generate_chapter(
    chapter_number=1,
    progress_callback=on_progress,
    # ... 其他参数
)
```

### 4. 断点续传

```python
# 检查是否有未完成的生成
pending = generator.get_pending_generations()

if pending:
    # 继续之前的生成
    result = generator.resume_generation(pending[0].generation_id)
```

### 5. 获取依赖状态

```python
# 检查依赖插件状态
deps = generator.check_dependencies()

print(f"ContextBuilder: {'可用' if deps['context-builder-v1'] else '不可用'}")
print(f"IterativeGenerator: {'可用' if deps['iterative-generator-v2'] else '不可用'}")
print(f"QualityValidator: {'可用' if deps['quality-validator-v1'] else '不可用'}")
```

---

## 输入输出

### 输入

```python
{
    "chapter_number": 1,
    "outline_path": "大纲/我的小说大纲.md",
    "style_path": "参考文本/作者作品.txt",  # 可选
    "characters_path": "人物设定/",  # 可选
    "worldview_path": "世界观/玄幻世界设定.md",  # 可选
    "context": "...",  # 可选，手动提供上下文
    "style_profile": {...}  # 可选，手动提供风格画像
}
```

### 输出

```python
@dataclass
class GenerationResult:
    success: bool
    chapter_number: int
    content: str                    # 生成的内容
    word_count: int                 # 实际字数
    output_path: str                # 保存路径
    iterations: int                 # 迭代次数
    final_score: float              # 最终评分
    score_details: ScoreDetails     # 评分详情
    generation_time: float          # 生成耗时
    error: Optional[str]            # 错误信息

@dataclass
class BatchResult:
    total: int                      # 总章节数
    success: int                    # 成功数
    failed: int                     # 失败数
    results: Dict[int, GenerationResult]  # 各章结果
```

---

## 依赖

- `context-builder-v1` (上下文构建器)
- `iterative-generator-v2` (迭代生成器)
- `quality-validator-v1` (质量验证器)

---

## 冲突

- 无

---

## 权限要求

- `ai.call`
- `file.read`
- `file.write`

---

## 生成流程

```
1. 加载大纲 → 解析章节信息
2. 加载风格 → 学习风格画像
3. 加载人物 → 获取人物设定
4. 加载世界观 → 获取背景信息
5. 构建上下文 → 调用context-builder
6. 迭代生成 → 调用iterative-generator
7. 质量验证 → 调用quality-validator
8. 保存结果 → 写入文件
```

---

## 注意事项

1. 确保所有依赖插件已加载
2. 大纲文件必须存在且格式正确
3. 生成结果保存在 `生成结果/` 目录
4. 支持中断后从断点继续
5. 历史记录限制为最近5章

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 3.0.0 | 2026-03-21 | 整合上下文构建、迭代生成、质量验证 |
