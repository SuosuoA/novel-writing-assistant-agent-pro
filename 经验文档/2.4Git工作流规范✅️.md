# Git 工作流规范

> 适用于 Novel Writing Assistant-Agent Pro 项目
> 版本：V1.0
> 日期：2026-03-21

---

## 一、分支模型

本项目采用 **简化的 Git Flow** 分支模型：

```
main (生产分支)
  │
  └─→ develop (开发分支)
        │
        ├─→ feature/* (功能分支)
        ├─→ bugfix/*  (修复分支)
        └─→ release/* (发布分支)
```

### 1.1 分支类型

| 分支类型 | 命名格式 | 说明 | 生命周期 |
|---------|---------|------|---------|
| main | `main` | 生产环境代码，始终稳定可发布 | 永久 |
| develop | `develop` | 开发集成分支，包含下一版本功能 | 永久 |
| feature | `feature/<功能名>` | 新功能开发 | 临时 |
| bugfix | `bugfix/<问题描述>` | Bug修复 | 临时 |
| release | `release/<版本号>` | 发布准备 | 临时 |
| hotfix | `hotfix/<版本号>` | 紧急生产修复 | 临时 |

### 1.2 分支命名规范

```bash
# 功能分支
feature/agent-system
feature/plugin-interface

# 修复分支
bugfix/memory-leak
bugfix/gui-crash

# 发布分支
release/v1.0.0
release/v2.0.0-beta

# 热修复分支
hotfix/v1.0.1
```

### 1.3 分支保护规则

#### main 分支（强制保护）
- ✅ PR 必须审核（至少 1 人批准）
- ✅ 必须通过 CI 检查（lint + test）
- ✅ 禁止强制推送
- ✅ 禁止直接提交

#### develop 分支（标准保护）
- ✅ PR 必须通过 CI 检查
- ⚠️ 可选择是否需要审核
- ✅ 禁止强制推送

---

## 二、提交信息规范

本项目采用 **Conventional Commits** 规范。

### 2.1 提交格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 2.2 类型（type）

| 类型 | 说明 | 示例 |
|-----|------|------|
| feat | 新功能 | feat(agent): add MasterAgent scheduler |
| fix | Bug修复 | fix(gui): resolve null pointer exception |
| docs | 文档更新 | docs: update API documentation |
| style | 代码格式（不影响逻辑） | style: format with black |
| refactor | 重构（不新增功能或修复bug） | refactor: extract common logic |
| perf | 性能优化 | perf: reduce memory usage |
| test | 测试相关 | test: add unit tests for EventBus |
| build | 构建系统 | build: update dependencies |
| ci | CI配置 | ci: add GitHub Actions workflow |
| chore | 其他杂项 | chore: update .gitignore |
| revert | 回滚提交 | revert: revert feat(agent) |

### 2.3 范围（scope）

根据项目模块划分：

- `core` - 核心模块（models, event_bus, config）
- `agent` - Agent 系统
- `plugin` - 插件系统
- `gui` - GUI 界面
- `api` - API 接口
- `db` - 数据库
- `test` - 测试相关

### 2.4 提交示例

```bash
# 简单提交
feat(agent): implement MasterAgent task scheduler

# 带 scope 的修复
fix(gui): resolve theme loading issue on Windows

# 带 body 的复杂提交
feat(plugin): implement plugin hot-reload mechanism

- Add PluginRegistry.unload() method
- Support plugin dependency tracking
- Add reload API endpoint

Closes #123

# 破坏性变更
refactor(core)!: change EventBus to async pattern

BREAKING CHANGE: EventBus.publish() now requires await

Migration guide:
- Before: event_bus.publish(event)
- After: await event_bus.publish(event)
```

### 2.5 提交检查清单

- [ ] 类型正确（feat/fix/docs等）
- [ ] 范围准确（可选但推荐）
- [ ] 主题简洁（50字符以内）
- [ ] 使用祈使语气（"add" 而非 "added"）
- [ ] 不以句号结尾
- [ ] 如有破坏性变更，使用 `!` 标记

---

## 三、Pull Request 规范

### 3.1 PR 标题格式

与提交信息格式一致：

```
<type>(<scope>): <subject>
```

示例：
```
feat(agent): add retry mechanism for LLM calls
fix(gui): resolve memory leak in chapter list
docs: update plugin development guide
```

### 3.2 PR 模板

项目已配置 PR 模板（`.github/pull_request_template.md`），提交时需填写：

1. **变更类型** - feat/fix/refactor/docs/其他
2. **关联Issue** - 如 `Closes #123`
3. **变更内容** - 新增/修改/删除的内容
4. **测试情况** - 单元测试/集成测试/手动测试
5. **文档更新** - 是否需要文档更新
6. **破坏性变更** - 是否有 Breaking Changes

### 3.3 PR 流程

```
1. 从 develop 创建功能分支
   git checkout develop
   git pull origin develop
   git checkout -b feature/my-feature

2. 开发并提交
   git add .
   git commit -m "feat: implement feature"

3. 推送到远程
   git push origin feature/my-feature

4. 创建 Pull Request
   - 目标分支：develop
   - 填写 PR 模板
   - 等待 CI 检查通过

5. Code Review
   - 代码审核
   - 处理评论

6. 合并
   - Squash and merge（推荐）
   - 或 Merge commit
   - 删除功能分支
```

### 3.4 合并策略

| 场景 | 合并方式 | 说明 |
|-----|---------|------|
| 功能分支 → develop | Squash and merge | 保持历史清晰 |
| develop → main | Merge commit | 保留发布记录 |
| hotfix → main | Merge commit | 紧急修复可追溯 |

---

## 四、工作流程

### 4.1 功能开发流程

```
develop ──── feature/new-feature ────→ develop
             (开发分支)
```

```bash
# 1. 更新本地 develop
git checkout develop
git pull origin develop

# 2. 创建功能分支
git checkout -b feature/new-feature

# 3. 开发提交
git commit -m "feat: add new feature"

# 4. 推送并创建 PR
git push origin feature/new-feature

# 5. 合并后删除分支
git branch -d feature/new-feature
git push origin --delete feature/new-feature
```

### 4.2 Bug 修复流程

```
develop ──── bugfix/issue-name ────→ develop
```

```bash
# 从 develop 创建修复分支
git checkout -b bugfix/issue-123

# 修复提交
git commit -m "fix: resolve issue #123"

# 创建 PR 到 develop
```

### 4.3 发布流程

```
develop ──── release/v1.0.0 ────→ main
                │
                └──→ develop (回合并更新版本号)
```

```bash
# 1. 创建发布分支
git checkout -b release/v1.0.0 develop

# 2. 版本准备
# - 更新版本号
# - 更新 CHANGELOG
# - 最终测试

git commit -m "chore: prepare release v1.0.0"

# 3. 合并到 main
git checkout main
git merge --no-ff release/v1.0.0
git tag -a v1.0.0 -m "Release v1.0.0"

# 4. 合并回 develop
git checkout develop
git merge --no-ff release/v1.0.0

# 5. 清理
git branch -d release/v1.0.0
```

### 4.4 热修复流程

```
main ──── hotfix/v1.0.1 ────→ main (打标签)
                │
                └──→ develop
```

```bash
# 1. 从 main 创建热修复分支
git checkout -b hotfix/v1.0.1 main

# 2. 修复并提交
git commit -m "fix: critical security patch"

# 3. 合并到 main
git checkout main
git merge --no-ff hotfix/v1.0.1
git tag -a v1.0.1 -m "Hotfix v1.0.1"

# 4. 合并到 develop
git checkout develop
git merge --no-ff hotfix/v1.0.1

# 5. 清理
git branch -d hotfix/v1.0.1
```

---

## 五、GitHub Actions CI 配置

项目已配置自动化 CI 检查（`.github/workflows/ci.yml`）：

### 5.1 触发条件

- Push 到 `main` 或 `develop` 分支
- Pull Request 到 `main` 或 `develop` 分支

### 5.2 检查项

| Job | 说明 | 工具 |
|-----|------|------|
| lint | 代码格式检查 | black, flake8 |
| test | 单元测试 | pytest |

### 5.3 本地预检查

提交前建议运行：

```bash
# 格式化代码
black .

# 代码检查
flake8 . --exclude=.git,__pycache__,.github,经验文档,tests

# 运行测试
pytest tests/ -v
```

---

## 六、最佳实践

### 6.1 提交粒度

- ✅ 每个提交只做一件事
- ✅ 提交可以独立回滚
- ❌ 避免巨型提交（>500行变更）
- ❌ 避免"修复上一个提交"的提交

### 6.2 PR 粒度

- ✅ 一个 PR 解决一个问题
- ✅ 变更控制在可 Review 的范围
- ✅ 完成后立即合并，避免长期存活
- ❌ 避免跨多个功能的 PR

### 6.3 分支管理

- ✅ 从最新的 develop 创建分支
- ✅ 合并前 rebase 或 merge 目标分支
- ✅ 合并后删除临时分支
- ❌ 避免在 feature 分支上长期开发

### 6.4 冲突解决

```bash
# 方法1：Rebase（推荐）
git checkout feature/my-feature
git fetch origin
git rebase origin/develop
# 解决冲突
git rebase --continue

# 方法2：Merge
git checkout feature/my-feature
git fetch origin
git merge origin/develop
# 解决冲突
git commit
```

---

## 七、工具配置

### 7.1 Git Hooks（可选）

使用 pre-commit 自动检查：

```bash
# 安装 pre-commit
pip install pre-commit

# 配置 .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black
        language_version: python3.12

  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: [--exclude=.git,__pycache__,经验文档]

# 安装 hooks
pre-commit install
```

### 7.2 Commit Message 检查（可选）

使用 commitlint 自动检查提交信息：

```bash
# 安装
npm install -g @commitlint/cli @commitlint/config-conventional

# 配置 commitlint.config.js
module.exports = {
  extends: ['@commitlint/config-conventional']
};
```

---

## 八、附录

### 8.1 常用命令速查

```bash
# 查看状态
git status

# 查看分支
git branch -a

# 创建并切换分支
git checkout -b feature/name

# 推送新分支
git push -u origin feature/name

# 拉取最新代码
git pull origin develop

# 查看提交历史
git log --oneline --graph --all

# 撤销未提交的修改
git restore <file>

# 撤销最后一次提交（保留修改）
git reset --soft HEAD~1

# 暂存当前修改
git stash
git stash pop
```

### 8.2 问题排查

| 问题 | 解决方案 |
|-----|---------|
| 推送被拒绝 | `git pull --rebase origin develop` 后再推送 |
| CI 检查失败 | 本地运行 `black . && flake8 . && pytest` |
| 合并冲突 | 手动解决后 `git add <resolved-files>` |
| 误删分支 | `git reflog` 找到提交，重新创建分支 |

---

**文档版本**: V1.0  
**最后更新**: 2026-03-21  
**维护者**: Agent Pro Team
