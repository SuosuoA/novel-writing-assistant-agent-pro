# 人物管理器 V1

> **插件ID**: `character-manager-v1`
> **版本**: 1.0.0
> **类型**: 分析器插件 (Analyzer)

---

## 用途

人物设定管理器，提供人物创建、一致性检查、关系管理等功能，确保小说人物设定的一致性和完整性。

### 核心功能

- **人物创建**: 创建详细的人物档案（外貌、性格、背景等）
- **一致性检查**: 检测人物设定是否存在矛盾
- **关系管理**: 管理人物之间的关系网络
- **人设评分**: 评估人物设定的完整度和吸引力

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `auto_save` | bool | true | 自动保存人物设定 |
| `check_consistency` | bool | true | 自动检查一致性 |
| `max_characters` | int | 100 | 最大人物数量 |
| `storage_path` | string | "人物设定/" | 存储路径 |

### 配置示例

```yaml
plugins:
  character-manager-v1:
    auto_save: true
    check_consistency: true
    max_characters: 100
    storage_path: "人物设定/"
```

---

## 使用示例

### 1. 创建人物

```python
from core.service_locator import ServiceLocator
from core.plugin_registry import PluginRegistry

# 获取插件
registry = ServiceLocator.get(PluginRegistry)
manager = registry.get_plugin("character-manager-v1")

# 创建人物
character = manager.create_character(
    name="李明",
    gender="男",
    age=25,
    appearance="身材高大，眉目清秀",
    personality="性格开朗，待人真诚",
    background="出生于书香世家，自幼酷爱读书"
)

print(f"人物ID: {character.id}")
print(f"人设评分: {character.profile_score}")
```

### 2. 更新人物设定

```python
# 添加人物特征
manager.add_trait(
    character_id=character.id,
    trait_type="技能",
    trait_value="精通书法"
)

# 添加人物关系
manager.add_relationship(
    character_id=character.id,
    related_name="王芳",
    relationship="青梅竹马"
)
```

### 3. 一致性检查

```python
# 检查人物设定一致性
issues = manager.check_consistency(character.id)

if issues:
    for issue in issues:
        print(f"发现矛盾: {issue.description}")
        print(f"位置: {issue.location}")
else:
    print("人物设定一致性检查通过")
```

### 4. 获取人物信息

```python
# 获取人物完整信息
info = manager.get_character(character.id)

# 获取所有人物列表
all_characters = manager.list_characters()

# 按条件筛选
protagonists = manager.filter_characters(role="主角")
```

### 5. 人设评分

```python
# 评估人物设定
score = manager.evaluate_profile(character.id)

print(f"人设评分: {score.overall:.2f}")
print(f"完整性: {score.completeness:.2f}")
print(f"吸引力: {score.attractiveness:.2f}")
print(f"一致性: {score.consistency:.2f}")
```

---

## 输入输出

### 输入

人物设定数据（字典或Pydantic模型）：

```python
{
    "name": "李明",
    "gender": "男",
    "age": 25,
    "appearance": "身材高大，眉目清秀",
    "personality": "性格开朗，待人真诚",
    "background": "出生于书香世家",
    "skills": ["书法", "诗词"],
    "relationships": [
        {"name": "王芳", "type": "青梅竹马"}
    ]
}
```

### 输出

```python
@dataclass
class Character:
    id: str
    name: str
    gender: str
    age: int
    appearance: str
    personality: str
    background: str
    skills: List[str]
    relationships: List[Relationship]
    profile_score: float
    created_at: datetime
    updated_at: datetime

@dataclass
class ConsistencyIssue:
    character_id: str
    description: str
    location: str
    severity: str  # "error" / "warning"
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
- `file.write`

---

## 注意事项

1. 人物设定保存在 `人物设定/` 目录下
2. 每个人物一个独立的JSON文件
3. 修改人物后会自动触发一致性检查
4. 人设评分低于0.5时会有警告提示

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-03-21 | 初始版本 |
