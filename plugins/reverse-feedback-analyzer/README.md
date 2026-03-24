# 逆向反馈分析器插件

> **版本**: V1.0  
> **创建日期**: 2026-03-24  
> **作者**: 项目组  
> **类型**: AnalyzerPlugin  
> **依赖**: outline-parser-v3, character-manager-v1, worldview-parser-v1

---

## 功能概述

逆向反馈分析器插件用于分析已生成的小说章节内容与项目设定（大纲、人物、世界观）的一致性，检测冲突并生成修正建议。

### 核心能力

1. **设定一致性保障**: 确保后续生成内容与已有章节保持一致
2. **冲突自动检测**: 识别角色行为、情节发展、世界观设定的矛盾
3. **智能修正建议**: 为每个冲突提供可执行的修正方案
4. **AI深度分析**: 利用大模型（DeepSeek/OpenAI）进行语义层面的深度比对
5. **结果缓存**: 缓存分析结果，避免重复调用AI

### 分析维度

- **大纲冲突**: 章节标题不在大纲中、情节偏离大纲
- **人物设定冲突**: 角色性格偏离、能力设定矛盾、关系设定不一致
- **世界观冲突**: 违背世界观设定、术语使用不一致

---

## 使用方式

### 1. 单章节一致性分析

```python
from core.plugin_interface import ReverseFeedbackAnalyzerPlugin, ConsistencyReport

# 获取插件实例
plugin = plugin_registry.get_plugin("reverse-feedback-analyzer")

# 准备数据
chapter_text = """
林逸拔出长剑，施展御剑术冲向敌营...
"""

current_settings = {
    "project_name": "修仙传奇",
    "chapter_title": "第三章 首战",
    "outline": "第一章：主角觉醒\n第二章：入门修炼\n第三章：首战",
    "characters": [
        {
            "name": "林逸",
            "personality": "坚毅、勇敢、重情义",
            "ability": "基础剑法",
            "background": "孤儿，被师傅收养"
        }
    ],
    "worldview": "这是一个修仙世界，凡人通过修炼获得灵力..."
}

# 执行分析
report = plugin.analyze_chapter_vs_settings(
    chapter_text=chapter_text,
    current_settings=current_settings,
    chapter_id="chap_003"
)

# 查看结果
print(f"发现 {len(report.issues)} 个冲突")
for issue in report.issues:
    print(f"[{issue.severity.value.upper()}] {issue.description}")
    print(f"建议: {issue.suggested_fix}\n")
```

### 2. 项目整体分析

```python
# 加载项目数据
project_data = {
    "project_name": "修仙传奇",
    "chapters": [
        {
            "id": "chap_001",
            "title": "第一章 启程",
            "content": "林逸从小村庄出发..."
        },
        {
            "id": "chap_002",
            "title": "第二章 入门",
            "content": "林逸拜入青云宗..."
        },
        {
            "id": "chap_003",
            "title": "第三章 首战",
            "content": "林逸拔出长剑..."
        }
    ],
    "outline": "第一章：主角觉醒\n第二章：入门修炼\n第三章：首战",
    "characters": [...],
    "worldview": "修仙世界..."
}

# 执行全项目分析
report = plugin.analyze_project(
    project_data=project_data,
    options={"include_low_severity": True}
)

print(f"分析完成: {report.chapters_analyzed} 章节")
print(f"发现冲突: 高优先级 {report.high_priority_count} 个")
```

### 3. 生成修正建议

```python
# 根据分析报告生成修正方案
corrections = plugin.generate_corrections(
    report=report,
    current_settings=current_settings,
    options={
        "auto_fix_low": True,
        "preserve_original": True
    }
)

# 查看建议
for suggestion in corrections["suggestions"]:
    print(suggestion)

# 应用修正（可选）
project_data["outline"] = corrections["updated_outline"]
project_data["characters"] = corrections["updated_characters"]
project_data["worldview"] = corrections["updated_worldview"]

# 保存备份
if corrections["backup"]:
    save_backup(corrections["backup"])
```

---

## 分析流程

插件采用两阶段分析方法：

### 第一阶段: 基础规则分析（快速）

1. **人物姓名一致性检查**
   - 检测章节中出现的所有人物名称
   - 对比人物设定中定义的角色
   - 发现未定义的新角色

2. **世界观术语一致性检查**
   - 提取章节中的世界观术语（引号中的内容）
   - 对比世界观设定中的已知术语
   - 发现未定义的新术语

3. **大纲章节顺序检查**
   - 验证章节标题是否在大纲中存在
   - 检查章节顺序是否符合大纲

### 第二阶段: 深度语义分析（AI辅助）

利用LLM进行深层语义分析：

1. **人物性格偏离检测**
   - 分析章节中角色的行为表现
   - 对比人物设定中的性格描述
   - 识别性格不一致

2. **世界观设定违背检测**
   - 识别章节中违背世界观设定的地方
   - 检查能力使用是否与设定匹配
   - 发现逻辑矛盾

3. **情节逻辑矛盾检测**
   - 检查情节发展是否符合大纲
   - 发现前后矛盾的情节
   - 识别逻辑漏洞

---

## 输出格式

### ConsistencyIssue（冲突项）

```python
{
    "issue_id": "issue-a1b2c3d4",
    "issue_type": "character",  # outline/character/worldview
    "severity": "high",        # low/medium/high
    "description": "角色'林逸'在第3章中使用了'御剑术'，但人物设定中其能力仅为'基础剑法'",
    "suggested_fix": "将人物设定中的能力修改为'御剑术'，或修改第3章内容",
    "original_content": "能力：基础剑法",
    "chapter_reference": "chap_003",
    "detected_at": "2026-03-24T10:30:00Z",
    "element_name": "林逸",
    "confidence": 0.92
}
```

### ConsistencyReport（分析报告）

```python
{
    "report_id": "report-e5f6g7h8",
    "project_name": "修仙传奇",
    "chapters_analyzed": 5,
    "issues": [...],  # ConsistencyIssue列表
    "summary": "发现12个冲突项，其中2个高优先级需要立即修正",
    "analyzed_at": "2026-03-24T10:35:00Z",
    "high_priority_count": 2,
    "medium_priority_count": 5,
    "low_priority_count": 5
}
```

---

## 缓存机制

插件会缓存分析结果以避免重复调用AI：

```python
# 清除缓存
plugin.clear_cache()

# 查看缓存统计
stats = plugin.get_cache_stats()
print(f"缓存的章节数: {stats['cached_chapters']}")
print(f"缓存大小: {stats['cache_size_bytes']} bytes")
```

---

## 事件订阅

插件订阅以下事件：

| 事件类型 | 说明 |
|----------|------|
| `chapter.generated` | 章节生成后自动进行一致性分析 |

分析完成后，如果发现问题，会发布事件：

| 事件类型 | 说明 |
|----------|------|
| `consistency.issue.detected` | 检测到设定冲突 |

---

## 配置要求

插件依赖配置文件中的以下参数：

```yaml
provider: DeepSeek  # 或 OpenAI
api_key: your-api-key
local_url: http://localhost:11434/v1  # 本地模型URL（可选）
model: deepseek-chat
temperature: 0.7
```

---

## 错误处理

| 错误场景 | 处理策略 |
|----------|----------|
| LLM调用超时 | 返回基础规则分析结果，标记未完成深度分析 |
| 依赖插件未找到 | 跳过对应类型的检测，记录警告日志 |
| 设定文件缺失 | 跳过对应类型的检测，记录警告日志 |
| 章节内容为空 | 记录警告，继续处理其他章节 |

---

## 性能考虑

- **缓存优先**: 已分析的章节直接返回缓存结果
- **异步分析**: 章节生成事件触发异步分析，不阻塞主流程
- **分阶段分析**: 先快速检查，再深度分析，减少LLM调用
- **内容截断**: 提示词中截断过长内容，避免Token超限

---

## 限制与注意事项

1. **LLM质量依赖**: 深度语义分析依赖LLM的理解能力，不同模型可能产生不同结果
2. **Token限制**: 长章节会被截断，可能遗漏部分冲突
3. **主观性**: 性格偏离等判断具有一定主观性
4. **缓存失效**: 设定变更后需要清除缓存重新分析

---

## 未来优化方向

1. **增量分析**: 仅分析新增或修改的章节
2. **机器学习**: 训练专门的冲突检测模型
3. **可视化展示**: 在UI中直观展示冲突分布和关系
4. **自动修正**: 实现低优先级冲突的自动修正
5. **历史追踪**: 记录设定变更历史，支持版本对比

---

## 参考文档

1. [项目总体架构设计说明书V1.4](../../经验文档/1.1项目总体架构设计说明书修订执行版✅️.md) - 第19.4节逆向反馈功能预设
2. [逆向反馈数据模型与API说明](../../经验文档/9.4.1%20设计逆向反馈数据模型与API说明✅️.md) - 详细设计文档
3. [插件接口定义](../../经验文档/2.2%20插件接口定义✅️.md) - 插件开发规范

---

**版本历史**

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| V1.0 | 2026-03-24 | 初始版本，实现基础规则分析+AI深度分析 |
