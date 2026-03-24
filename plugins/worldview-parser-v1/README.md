# 世界观解析器 V1

> **插件ID**: `worldview-parser-v1`
> **版本**: 1.0.0
> **类型**: 分析器插件 (Analyzer)

---

## 用途

通用世界观解析器，解析小说世界观设定文件，提取并结构化世界观信息，为生成提供背景支撑。

### 核心功能

- **多格式支持**: 支持Markdown、YAML、JSON格式
- **自动分类**: 自动识别时间线、地理、势力、规则等类别
- **关系提取**: 提取世界观元素之间的关系
- **一致性验证**: 验证世界观设定的内部一致性

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `default_format` | string | "markdown" | 默认解析格式 |
| `validate` | bool | true | 是否验证一致性 |
| `cache_enabled` | bool | true | 是否缓存解析结果 |

### 配置示例

```yaml
plugins:
  worldview-parser-v1:
    default_format: "markdown"
    validate: true
    cache_enabled: true
```

---

## 使用示例

### 1. 解析世界观文件

```python
from core.service_locator import ServiceLocator
from core.plugin_registry import PluginRegistry

# 获取插件
registry = ServiceLocator.get(PluginRegistry)
parser = registry.get_plugin("worldview-parser-v1")

# 解析世界观文件
worldview = parser.parse("世界观/玄幻世界设定.md")

print(f"世界名称: {worldview.name}")
print(f"时代背景: {worldview.era}")
print(f"势力数量: {len(worldview.factions)}")
```

### 2. 获取世界观数据

```python
# 获取地理信息
geography = parser.get_geography(worldview.id)
print(f"大陆数量: {len(geography.continents)}")

# 获取势力信息
factions = parser.get_factions(worldview.id)
for faction in factions:
    print(f"势力: {faction.name}, 关系: {faction.relations}")

# 获取时间线
timeline = parser.get_timeline(worldview.id)
for event in timeline.events:
    print(f"{event.year}年: {event.description}")
```

### 3. 查询世界观数据

```python
# 按类别查询
magic_system = parser.query(worldview.id, category="魔法体系")

# 按关键词搜索
results = parser.search(worldview.id, keyword="剑法")

# 按关系查询
related = parser.get_related(worldview.id, element_id="门派-昆仑")
```

### 4. 一致性验证

```python
# 验证世界观一致性
validation = parser.validate(worldview.id)

if validation.is_valid:
    print("世界观设定一致")
else:
    for issue in validation.issues:
        print(f"问题: {issue.description}")
        print(f"严重程度: {issue.severity}")
```

---

## 输入输出

### 输入

Markdown格式的世界观文件：

```markdown
# 世界观设定

## 基本信息

- 世界名称: 玄灵大陆
- 时代背景: 上古修真时代
- 主要种族: 人族、妖族、灵族

## 地理设定

### 东域

- 地形: 山脉为主
- 气候: 温和湿润
- 主要势力: 昆仑派、剑宗

## 势力设定

### 昆仑派

- 等级: 一流宗门
- 特色: 道法自然
- 关系: 与剑宗交好

## 规则设定

### 修炼体系

- 境界: 炼气→筑基→金丹→元婴→化神
- 资源: 灵石、丹药、功法
```

### 输出

```python
@dataclass
class Worldview:
    id: str
    name: str
    era: str
    geography: GeographyInfo
    factions: List[FactionInfo]
    rules: List[RuleInfo]
    timeline: TimelineInfo
    races: List[str]
    is_valid: bool

@dataclass
class FactionInfo:
    id: str
    name: str
    level: str
    specialty: str
    relations: Dict[str, str]  # 势力名 -> 关系类型
```

---

## 依赖

- 无外部插件依赖

---

## 冲突

- 无

---

## 权限要求

- `file.read`

---

## 注意事项

1. 世界观文件建议使用Markdown格式
2. 不同类别的设定使用二级标题分隔
3. 解析结果缓存在 `cache/worldview/` 目录
4. 验证问题分为error和warning两个级别

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-03-21 | 初始版本 |
