# Novel Writing Assistant - Agent Pro

<p align="center">
  <strong>AI驱动的智能小说创作助手 | AI-Powered Intelligent Novel Writing Assistant</strong>
</p>

<p align="center">
  一款基于微内核架构的模块化小说创作工具，集成AI生成、评分反馈、知识库检索、长期记忆等核心能力，实现"越用越聪明"的创作体验。
</p>

---

## 📖 项目简介

**Novel Writing Assistant - Agent Pro** 是一款面向小说作者和内容创作者的智能写作工具。通过AI大模型驱动，结合多维度评分反馈机制，帮助用户高效创作高质量小说内容。

### 核心特性

- 🎯 **评分反馈循环生成**：8维度评分 → 自动反馈 → 迭代优化，确保生成质量
- 🧠 **越用越聪明架构**：Claw化学习闭环，从用户反馈中持续进化
- 📚 **本地知识库**：1130+条知识点，向量检索秒级召回
- 💾 **长期记忆系统**：OpenClaw mem9五层架构，长篇连贯性保障
- 🔌 **插件化架构**：16个功能插件，热插拔无重启
- 🤖 **Agent智能增强**：推理/优化/验证/规划四专家Agent协同

---

## 🚀 快速开始

### 环境要求

- **Python**: 3.12.x
- **操作系统**: Windows 10/11、macOS 10.15+、Ubuntu 20.04+
- **内存**: ≥8GB RAM
- **存储**: ≥2GB 可用空间

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/novel-writing-assistant-agent-pro.git
cd novel-writing-assistant-agent-pro

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置API密钥
cp config.yaml.example config.yaml
# 编辑config.yaml，填入你的API密钥

# 5. 启动程序
python gui_main.py
```

### 配置API

支持多种AI服务商：

| 服务商 | 模型 | 价格（输入/输出） | 推荐 |
|--------|------|------------------|------|
| DeepSeek | deepseek-chat | ¥0.14/¥0.28/百万token | ⭐ 推荐 |
| OpenAI | gpt-4o | $5/$15/百万token | 高端选择 |
| Anthropic | claude-3.5-sonnet | $3/$15/百万token | 高端选择 |
| 本地Ollama | qwen2.5:14b | 免费 | 隐私优先 |

---

## 🏗️ 项目架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户界面层 (Tkinter + sv_ttk)                                                                                                       │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────┐                   │
│  │         热榜页面            │ │           工作台             │ │           项目管理          │ │    插件管理      │                   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────┘                   │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      应用层 (MasterAgent)                                                                                                                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                                                     │
│  │    Thinker       │ │    Optimizer   │ │    Validator     │ │         Planner  │                                                    │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘                                                    │
└─────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌───────────────────────┐ ┌───────────────┐ ┌───────────────────────┐
│          微内核核心 (Kernel)                    │ │          插件系统               │ │                服务层 (Services)                  │
│  ┌──────────────────┐ │ │ ┌───────────┐ │ │  ┌─────────────────┐                  │
│  │              EventBus                   │ │ │  │       16个插件       │ │ │  │             AI API服务               │                  │
│  │         PluginRegistry              │ │ │ │          热插拔          │ │ │  └─────────────────┘                 │
│  │        ServiceLocator              │ │ │ └───────────┘ │ │  ┌─────────────────┐                  │
│  │        ConfigManager              │ │ │                                    │ │  │              文件服务                  │                  │
│  └──────────────────┘ │ │                                     │ │  └─────────────────┘                  │
└───────────────────────┘ └───────────────┘ └───────────────────────┘
```

### 核心模块（已部署）

| 目录 | 模块数量 | 说明 |
|------|---------|------|
| **core/** | 51个 | 核心框架模块（EventBus、PluginRegistry、ServiceLocator等） |
| **agents/** | 38个 | Agent系统模块（MasterAgent、专家Agent、协调器等） |
| **infrastructure/** | 9个 | 基础设施模块（VectorStore、DatabasePool、LLMClient等） |
| **tools/** | 30个 | 工具类模块（知识库管理、评分分析、反馈处理等） |
| **plugins/** | 16个 | 功能插件模块（热插拔，无需重启） |

---

## 🔌 插件生态

### 已部署插件（16个）

| 插件名称 | 类型 | 功能描述 |
|----------|------|----------|
| **ai-service-router-v1** | Protocol | AI服务路由器，支持多API切换 |
| **api-config-manager-v1** | Tool | API配置管理器，加密存储密钥 |
| **character-manager-v1** | Analyzer | 人物管理器，角色档案与一致性检查 |
| **context-builder-v1** | Generator | 上下文构建器，智能提示词优化 |
| **continuation-generator-v1** | Generator | 续写生成器，智能续写与多版本管理 |
| **hello-world** | Tool | 测试插件，开发示例 |
| **hot-ranking-v1** | Tool | 热榜插件，实时抓取创作灵感 |
| **iterative-generator-v2** | Generator | 迭代生成器，评分反馈循环 |
| **knowledge-validator** | Validator | 知识验证器，知识点引用检查 |
| **novel-generator-v3** | Generator | 小说生成器，核心生成流程 |
| **outline-parser-v3** | Analyzer | 大纲解析器，支持多格式导入 |
| **quality-validator-v1** | Validator | 质量验证器，8维度评分系统 |
| **quick-creator-v1** | Generator | 快捷创作器，快速生成设定 |
| **reverse-feedback-analyzer** | Analyzer | 逆向反馈分析器，章节反向修正设定 |
| **style-learner-v5** | Analyzer | 风格学习器，7维度风格分析 |
| **worldview-parser-v1** | Analyzer | 世界观解析器，元素分类管理 |

### 插件开发

开发者可基于 `BasePlugin` 接口开发自定义插件：

```python
from core.plugin_interface import BasePlugin, PluginMetadata, PluginType

class MyCustomPlugin(BasePlugin):
    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            id="my-custom-plugin",
            name="我的自定义插件",
            version="1.0.0",
            description="插件功能描述",
            author="Your Name",
            plugin_type=PluginType.TOOL,
            api_version="1.0"
        )
    
    def initialize(self, context: PluginContext) -> bool:
        # 初始化逻辑
        return True
    
    def execute(self, action: str, params: dict) -> dict:
        # 执行逻辑
        return {"success": True}
```

---

## 🎯 核心功能

### 1. 评分反馈循环生成

**流程**：
```
用户请求 → 上下文构建 → AI生成 → 8维度评分 → 反馈优化 → 迭代生成 → 达标输出
```

**8维度评分权重（V1.7）**：

| 维度 | 权重 | 说明 |
|------|------|------|
| 字数符合性 | 8% | 字数是否接近目标 |
| 知识点引用 | 8% | 是否正确引用知识库知识点 |
| 大纲符合性 | 13% | 是否符合大纲设定 |
| 风格一致性 | 19% | 是否符合风格样本 |
| 人设一致性 | 19% | 是否符合人物设定 |
| 世界观一致性 | 12% | 是否符合世界观设定 |
| 逆向反馈 | 11% | 上下文衔接一致性 |
| 自然度 | 10% | 语言流畅自然程度 |

**评分阈值**：≥ 0.8 才能输出，最多迭代5次

### 2. 本地知识库

**双层架构**：
- **向量数据库**（LanceDB）：运行时检索，1355条向量
- **JSON源文件**：手动编辑和备份

**知识分类**：
- 科幻（physics:209, biology:150, space:100, technology:100）- 559条
- 玄幻（mythology:163, religion:171）- 334条
- 通用（logic:112, philosophy:102, basic_knowledge:12, economics:6, mathematics:5）- 237条
- **总计：1130条知识点**

**检索方式**：
- 向量检索（优先）：余弦相似度 top-10 召回
- 关键词匹配（回退）：TF-IDF 关键词搜索

### 3. 长期记忆系统（OpenClaw mem9）

**五层架构**：

| 层级 | 名称 | 存储方式 | 用途 |
|------|------|----------|------|
| L1 | 热记忆 | SESSION-STATE.md | 当前会话状态 |
| L2 | 温记忆 | LanceDB向量库 | 语义检索 |
| L3 | 冷记忆 | Git-Notes | 永久决策 |
| L4 | 档案 | MEMORY.md | 精选长期记忆 |
| L5 | 云备份 | 云存储 | 灾难恢复 |

**WAL协议**：AI调用前持久化状态，确保中断恢复

### 4. Claw化"越用越聪明"架构

**10个核心组件**（全部测试通过）：

1. **学习闭环管理器**：收集生成数据、提取知识点、更新知识库
2. **评分历史分析器**：追踪评分趋势、识别薄弱维度
3. **冲突模式学习器**：学习冲突模式、预判风险
4. **AI感检测器**：检测AI痕迹、从用户修改学习
5. **反馈收集器**：收集用户反馈、存储到SQLite
6. **反馈提纯器**：NLP提取知识点、结构化存储
7. **策略调整器**：优化生成策略、调整权重
8. **报告生成器**：生成周报/月报、模块升级建议
9. **Prompt优化引擎**：优化Prompt、添加约束
10. **Fine-tuning数据积累器**：收集训练数据、导出JSONL

**预期效果**：
- 短期（1-2周）：评分 0.78 → 0.81，AI感降低16%
- 中期（1-2月）：评分 0.78 → 0.85，AI感降低30%
- 长期（3月+）：评分 0.78 → 0.88，AI感降低50%

---

## 📊 当前进度

### 模块部署状态

| 类型 | 数量 | 完成度 | 测试通过率 |
|------|------|--------|-----------|
| 核心模块 | 51个 | 100% | 100% |
| Agent模块 | 38个 | 100% | 100% |
| 基础设施 | 9个 | 100% | 100% |
| 工具模块 | 30个 | 100% | 100% |
| 插件模块 | 16个 | 100% | 100% |
| **总计** | **144个** | **100%** | **100%** |

### 知识库状态

| 分类 | 数量 | 状态 |
|------|------|------|
| 科幻 | 559条 | ✅ 完成 |
| 玄幻 | 334条 | ✅ 完成 |
| 通用 | 237条 | ✅ 完成 |
| **总计** | **1130条** | **✅ 100%** |

### 核心里程碑

- ✅ **2026-03-25**：OpenClaw mem9架构设计完成
- ✅ **2026-03-26**：知识库双层架构修复完成（1130条知识点）
- ✅ **2026-03-26**：Claw化"越用越聪明"10组件完成
- ✅ **2026-03-26**：API安全方案测试通过（100%）
- ✅ **2026-03-26**：代码审查验收通过（P0/P1全部修复）
- ✅ **2026-03-27**：144个核心模块部署完成

---

## 🛠️ 技术栈

| 层级 | 技术 | 版本 | 说明 |
|------|------|------|------|
| **编程语言** | Python | 3.12.x | 不升级3.13+ |
| **GUI框架** | Tkinter + sv_ttk | 内置 + 2.2+ | 零额外依赖 |
| **数据验证** | Pydantic | 2.10.6+ | V2锁定 |
| **LLM客户端** | openai SDK | 1.60+ | 统一接口 |
| **向量数据库** | LanceDB | 0.12.0+ | 零配置嵌入式 |
| **向量编码** | sentence-transformers | 2.2.2+ | 本地嵌入模型 |
| **关系数据库** | SQLite | 3.40+ | WAL模式并发 |
| **HTTP客户端** | requests | 2.32.0+ | API调用 |
| **加密库** | cryptography | 46.0.0+ | API密钥加密 |
| **打包工具** | Nuitka | 4.0.5 | 编译为C |

---

## 📚 文档资源

### 核心文档

| 文档名称 | 说明 |
|----------|------|
| [《0.1✅️AgentPRO最全经验文档✅️.md》](./经验文档/0.1✅️AgentPRO最全经验文档✅️.md) | 项目最全经验总结 |
| [《1.1项目总体架构设计说明书修订执行版✅️.md》](./经验文档/1.1项目总体架构设计说明书修订执行版✅️.md) | 微内核架构设计 |
| [《1.3Agent系统详细设计文档✅️.md》](./经验文档/1.3Agent系统详细设计文档✅️.md) | Agent系统设计 |
| [《2.2 插件接口定义✅️.md》](./经验文档/2.2%20插件接口定义✅️.md) | 插件开发规范 |
| [《4.5核心框架使用指南✅️.md》](./经验文档/4.5核心框架使用指南✅️.md) | 开发者快速上手 |

### 用户文档

| 文档名称 | 说明 |
|----------|------|
| [《9.8.1 Agent Pro 用户手册✅️.md》](./经验文档/9.8.1%20Agent%20Pro%20用户手册✅️.md) | 用户使用指南 |
| [《9.8.2Agent Pro 开发者指南✅️.md》](./经验文档/9.8.2Agent%20Pro%20开发者指南✅️.md) | 开发者文档 |
| [《10.32Claw化用户手册✅️.md》](./经验文档/10.32Claw化用户手册✅️.md) | Claw化功能说明 |

---

## 🤝 贡献指南

### 开发环境搭建

```bash
# 1. Fork仓库并克隆
git clone https://github.com/your-username/novel-writing-assistant-agent-pro.git

# 2. 创建开发分支
git checkout -b feature/your-feature-name

# 3. 安装开发依赖
pip install -r requirements-dev.txt

# 4. 运行测试
python -m pytest tests/

# 5. 提交代码
git commit -m "feat: 添加新功能"
git push origin feature/your-feature-name

# 6. 创建Pull Request
```

### 代码规范

- 遵循PEP8代码风格
- 使用Pydantic v2数据模型
- 所有公共方法添加类型注解
- 关键逻辑添加详细注释

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](./LICENSE) 文件。

---

## 🙏 致谢

感谢以下开源项目：

- [openai/openai-python](https://github.com/openai/openai-python) - OpenAI API客户端
- [pydantic/pydantic](https://github.com/pydantic/pydantic) - 数据验证库
- [lancedb/lancedb](https://github.com/lancedb/lancedb) - 向量数据库
- [UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers) - 嵌入模型
- [WorkBuddy](https://workbuddy.ai/) - AI辅助开发平台

---

## 📞 联系方式

**秒速五厘米** | 青海 西宁

![微信二维码](./经验文档/微信二维码.jpg)

---

<p align="center">
  <strong>项目版本**: V1.10.0 | <strong>最后更新</strong>: 2026-03-27 | <strong>维护状态</strong>: 活跃开发中 ✅
</p>

<p align="center">
  <sub>Built with AI assistance | 一场AI辅助开发的探索实验</sub>
</p>
