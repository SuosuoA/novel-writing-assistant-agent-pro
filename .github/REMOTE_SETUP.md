# GitHub 远程仓库配置指南

## 当前状态

本地仓库已配置完成，但尚未关联远程仓库。

## 配置步骤

### 1. 在 GitHub 创建仓库

访问 https://github.com/new，创建新仓库：
- 仓库名：`novel-writing-assistant-agent-pro`（或自定义）
- 描述：Novel Writing Assistant - Agent Pro 智能小说写作辅助工具
- 可见性：Public 或 Private
- ⚠️ **不要**勾选 "Initialize this repository with a README"（避免冲突）

### 2. 添加远程仓库

```bash
# 添加远程仓库（替换 YOUR_USERNAME 为你的 GitHub 用户名）
git remote add origin https://github.com/YOUR_USERNAME/novel-writing-assistant-agent-pro.git

# 或使用 SSH（推荐）
git remote add origin git@github.com:YOUR_USERNAME/novel-writing-assistant-agent-pro.git
```

### 3. 推送分支

```bash
# 推送 main 分支
git push -u origin main

# 推送 develop 分支
git push -u origin develop

# 推送所有分支
git push --all origin
```

### 4. 配置分支保护规则

进入仓库 Settings → Branches → Add branch protection rule

#### main 分支保护：
```
Branch name pattern: main

☑ Require a pull request before merging
  ☑ Require approvals: 1
☑ Require status checks to pass before merging
  ☑ lint
  ☑ test
☑ Require branches to be up to date before merging
☑ Do not allow bypassing the above settings
```

#### develop 分支保护：
```
Branch name pattern: develop

☑ Require a pull request before merging
☑ Require status checks to pass before merging
  ☑ lint
  ☑ test
```

### 5. 验证 CI 工作流

推送后，GitHub Actions 会自动运行：
1. 进入仓库的 "Actions" 标签页
2. 查看 "CI" 工作流运行状态
3. 确保 lint 和 test 两个 job 都通过

## CI 状态徽章

配置完成后，可在 README.md 中添加徽章：

```markdown
![CI](https://github.com/YOUR_USERNAME/novel-writing-assistant-agent-pro/workflows/CI/badge.svg)
```

## 验证清单

- [ ] GitHub 仓库已创建
- [ ] 远程仓库已添加（git remote -v 显示 origin）
- [ ] main 和 develop 分支已推送
- [ ] 分支保护规则已配置
- [ ] CI 工作流运行成功
- [ ] 团队成员已邀请（如适用）

## 常见问题

### Q: 推送时提示 "fatal: 'origin' already exists"
A: 运行 `git remote remove origin` 后重新添加

### Q: CI 检查失败
A: 查看 Actions 日志，通常是代码格式或测试问题：
```bash
# 本地预检查
black . && flake8 . --exclude=.git,__pycache__,经验文档 && pytest tests/
```

### Q: 如何查看远程仓库
A: `git remote -v`

---

**文档创建**: 2026-03-21
