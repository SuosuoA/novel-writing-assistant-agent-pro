# CLAUDE.md — Novel Writing Assistant-Agent Pro

本文件供 Claude Code 在本仓库工作时加载。**本项目是一款自动创作超长篇小说的桌面软件**：用户给出大纲/人设/世界观/风格要求，软件通过「评分反馈循环」逐章生成并自我优化，直到达标。

---

## 🔴 最高优先级规则（每次动手前必读）

1. **修复/改动前，必须先读对应设计文档**（这是项目的铁律）。流程：
   1. 查索引 → [经验文档/0.1✅️AgentPRO最全经验文档✅️.md](经验文档/0.1✅️AgentPRO最全经验文档✅️.md) 定位相关设计文档
   2. 读设计文档 → 了解架构意图、接口规范、实现逻辑
   3. 查修复记录 → [经验文档/12.人工验证与修复记录✅️.md](经验文档/12.人工验证与修复记录✅️.md) 参考同类问题
   4. 按架构规范执行修复，保持代码风格一致
   5. 记录修复 → 回写 `经验文档/12.人工验证与修复记录✅️.md`
2. **每次只改指定部分**，不顺手重构、不扩大改动范围。
3. **不执行破坏性 git 命令**（`restore` / `reset` / `checkout --` / 强推等），除非用户明确要求。
4. **不生成要求以外的总结/报告**。修复完成后打开测试界面供用户验证即可。
5. **不可修改的核心资产**：见下文「V5 受保护核心模块」与「九维度评分」——修改前需架构评审，保持向后兼容。
6. 中文标点写入 JSON 时用 `【】《》` 替代中文引号，统一用 `json.dump()` 序列化（中文引号会导致解析问题）。

---

## 技术栈（已锁定，不要擅自更换/升级）

| 层级 | 选择 | 说明 |
|------|------|------|
| 语言 | **Python 3.12.x** | 不升级 3.13+ |
| GUI | **Tkinter + sv-ttk** | 不更换框架 |
| Agent | 自研 **MasterAgent** | 零额外依赖 |
| LLM 客户端 | `openai` SDK | 统一接口兼容多provider |
| 向量库 | **LanceDB** (≥0.12) | L2 温记忆 |
| 数据库 | **SQLite + WAL** | 嵌入式并发 |
| 打包 | **Nuitka** 4.0.5 | 编译为 C，非 PyInstaller |
| 数据验证 | Pydantic v2 | |

**API 策略**：默认 **DeepSeek**（`deepseek-chat` / `deepseek-reasoner`）。配置在 [config.yaml](config.yaml)，API Key 加密存于 `.secrets/`（**严禁明文硬编码密钥**）。也支持本地模型：Ollama（`http://localhost:11434/v1`）、本地 Qwen。

依赖见 [requirements.txt](requirements.txt)。

---

## 运行 / 测试

```bash
# 启动 GUI（开发模式，允许加载非官方插件）
set DEV_MODE=1            # PowerShell: $env:DEV_MODE=1
python gui_main.py
# 或直接运行根目录的 "Novel Writing Assistant-Agent Pro启动.bat"（已自动设 DEV_MODE=1）

# 运行测试
python tests/run_tests.py
```

- 主程序入口 [gui_main.py](gui_main.py)（**约 1.3 万行的巨型文件**，改动需谨慎、精准定位）。
- 测试写在 `tests/`，临时测试文件验证后删除。
- 若知识库界面卡死或 HuggingFace 超时：设置环境变量 `HF_HUB_OFFLINE=1`（入口处已处理）。

---

## 架构总览（微内核 + 插件化 + Agent + 五层记忆）

```
用户界面层 (Tkinter + sv-ttk)
    ↓
应用层 (MasterAgent: Thinker / Optimizer / Validator / Planner)
    ↓
微内核核心 (EventBus + PluginRegistry + ServiceLocator + ConfigManager)
    ↓
插件层 (16 个插件)
    ↓
基础设施层 (日志 / 指标 / 熔断器 / SQLite WAL / 向量库)
```

**关键目录**：

| 目录 | 内容 |
|------|------|
| `core/` | 微内核与核心服务（EventBus、插件加载、记忆、AI provider 等，~65 个模块） |
| `agents/` | 自研 Agent 系统（MasterAgent、流水线编排、一致性检查 Agent 等） |
| `plugins/` | 16 个插件（每个含 `plugin.py` + `manifest`） |
| `infrastructure/` | 日志/监控/熔断器/`vector_store.py`/`security.py` |
| `services/` | 服务层（`project_manager.py`、带容错的 LLM 客户端） |
| `scripts/` | V5 核心模块（`context_builder.py`、`enhanced_weighted_validator.py` 等） |
| `data/` | `knowledge/`（JSON 源）+ `knowledge_base/`（LanceDB 向量库） |
| `config/` | `expert_weights.yaml`、`validator_weights.yaml` |
| `经验文档/` | **全部设计文档与修复记录**（动手前必查） |
| `小说作品/` | 生成的小说项目数据 |

**已部署插件（16）**：ai-service-router-v1、api-config-manager-v1、character-manager-v1、context-builder-v1、continuation-generator-v1、expert-novel-v1、hot-ranking-v1、iterative-generator-v2、knowledge-validator、local-service-v1、novel-generator-v3、outline-parser-v3、quality-validator-v1、quick-creator-v1、style-learner-v5、worldview-parser-v1。

---

## 核心业务：评分反馈循环（强制保护机制）

```
1.上下文构建 → 2.AI生成 → 3.九维度评分 → 4.达标判断
                                              ↓ 不达标
                              5.反馈生成 → 6.迭代优化(≤5次) → 回到2
                                              ↓ 达标
                                          7.完成并沉淀记忆
```

**5 大不可破坏规则**：
1. 每章必须出现 `【本章完】` 标记（缺失则自动补充并强制检查）。
2. 评分阈值 **0.8**，低于则继续迭代。
3. 迭代上限 **5 次**。
4. 九维度权重不可修改。
5. 上下文记忆前 5 章。

**权重归属原则（ADR-010/011，必须遵守）**：评分权重定义与加权计算**只在插件层**完成，**GUI 不硬编码权重、不计算评分、不判断达标**。
- `novel-generator-v3` → 返回 `weighted_total_score` + `passed`
- `expert-novel-v1` → 返回 `ValidationScores.total_score`
- `quality-validator-v1` → 提供 `get_dimension_display_map()` / `get_dimension_attr_map()`（维度映射唯一真值来源）
- GUI 只读取与显示，降级路径用简单平均兜底。

### 九维度评分权重（锁定）

| 维度 | 权重 | 维度 | 权重 |
|------|:--:|------|:--:|
| 人设一致性 | 19% | 写作技巧 | 8% |
| 风格一致性 | 19% | 字数符合性 | 8% |
| 大纲符合性 | 13% | 上下文衔接 | 8% |
| 世界观一致性 | 12% | AI 感 | 5% |
| 知识库引用 | 8% | | |

> 数据为空 = 数据流断裂 → 应报错（不可用默认高分掩盖）；用户未配置该维度 → 给中性分 0.85（V6.3 治理原则）。

---

## V5 受保护核心模块（改动前需架构评审）

大纲解析 `outline-parser-v3`、风格学习 `style-learner-v5`、人物管理 `character-manager-v1`（含关系图谱）、世界观解析 `worldview-parser-v1`、上下文构建 `context-builder-v1`、迭代生成 `iterative-generator-v2`、加权验证 `quality-validator-v1`、生成入口 `novel-generator-v3`、热榜 `hot-ranking-v1`。

**专家模式 7 步学习闭环**（`plugins/expert-novel-v1/`）：数据打包(回读历史经验) → API 请求 → 九维度评分 → 带反馈重试 → 输出最佳 → 沉淀到 ExpertMemory，下次回读 → **越用越聪明**。核心方法：`generate()`（主循环）、`_build_iteration_feedback()`、`_enhance_request()`、`memory.py:ExpertMemory`。

---

## 记忆系统（注意区分两套）

| 系统 | 路径 | 用途 |
|------|------|------|
| **AI 构建记忆** | `.workbuddy/memory/` | Claude 构建本软件时的工作记忆（含 `MEMORY.md` 总记忆 + 各身份 `MEMORY.md`） |
| **软件运行记忆** | `Memory-Novel Writing Assistant-Agent Pro/` | 软件运行时的智能记忆 |

**软件运行时的五层记忆（OpenClaw mem9）**：
- L1 热记忆 `core/session_state.py` ｜ L2 温记忆 `infrastructure/vector_store.py`(LanceDB) ｜ L3 冷记忆 `core/git_notes_manager.py` ｜ L4 档案 `Memory-*/MEMORY.md` ｜ L5 云备份。WAL 写入：`core/wal_manager.py`。

> 修复后维护：详细设计思路写入 `经验文档/`；小改动写身份记忆；大改动更新 `.workbuddy/memory/MEMORY.md`。

---

## 文档导航（按任务找文档）

| 任务 | 推荐文档 |
|------|----------|
| 理解架构 | `经验文档/0.2✅️…程序框架方案_V3.0✅️.md` → `1.1项目总体架构设计说明书…✅️.md` |
| 修 BUG | `经验文档/12.人工验证与修复记录✅️.md` → `12.x` 系列 |
| 开发/迁移插件 | `经验文档/2.2 插件接口定义✅️.md` → `7.2插件开发规范…` |
| Agent 开发 | `经验文档/1.3Agent系统详细设计文档✅️.md` |
| 改 UI | `经验文档/4.1UI搭建说明✅️.md` |
| API 安全 / 记忆系统 | `经验文档/11.2API安全使用方案✅️.md` / `11.4Claw化实际运行说明✅️.md` |

当前进度参考：根 [README.md](README.md) 与 `.workbuddy/memory/MEMORY.md`（最近版本约 V1.49.45，2026-04-13）。

---

## 编码约定

- 风格遵循 PEP 8；函数 < 50 行，文件尽量 < 800 行（`gui_main.py` 是历史巨型文件，逐步外迁，不要再往里堆逻辑）。
- 业务逻辑下沉到插件/服务层，GUI 只做展示与编排（见技术债 P0-V3：`GenerationDataService` 数据加工下沉）。
- 全面处理错误，不静默吞异常；系统边界校验输入。
- 不可变优先；命名清晰；魔法数字提取为常量。
- 异步统一走 `ThreadPoolManager`（单例），避免多套线程池冲突；新增异步方法用「新增不改旧」模式。
