"""
MEMORY.md 维护工具（OpenClaw L4 精选档案）

参考 OpenClaw mem9 框架设计：
- 每日冥想：自动提炼当日重要事件到 MEMORY.md
- 每周大冥想：深度精简 MEMORY.md，归档旧日记
- 精简原则：每条记录问"6个月后还有用吗？"

文件位置：tools/memory_maintenance.py

作者：高级开发工程师
日期：2026-03-25
版本：V1.0
"""

import os
import re
import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import threading
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MemoryEvent:
    """记忆事件数据模型"""
    date: str  # 日期 YYYY-MM-DD
    title: str  # 事件标题
    content: str  # 事件内容
    importance: str  # 重要性：high/medium/low
    category: str  # 分类：feature/bugfix/refactor/doc/decision
    source_file: str  # 来源文件路径
    preserve: bool = False  # 是否保留（6个月后还有用）


@dataclass
class MemorySection:
    """MEMORY.md 章节结构"""
    title: str
    content: str
    lines: List[str] = field(default_factory=list)


class MemoryMaintenanceTool:
    """
    MEMORY.md 维护工具
    
    核心功能：
    1. 每日冥想：提炼当日重要事件
    2. 每周大冥想：深度精简，归档旧日记
    3. 自动归档：将旧日记归档到 memory/archive/
    4. 大小控制：确保 MEMORY.md < 50KB
    """
    
    # 重要性关键词（用于自动判断事件重要性）
    HIGH_IMPORTANCE_KEYWORDS = [
        'ADR-', '决策', '锁定', '保护', '修复', '完成', '实现',
        '重大', '关键', '核心', '架构', '安全', 'P0', 'P1'
    ]
    
    MEDIUM_IMPORTANCE_KEYWORDS = [
        '优化', '更新', '新增', '集成', '测试', '验证', '评审'
    ]
    
    # 类别关键词
    CATEGORY_KEYWORDS = {
        'feature': ['实现', '新增', '集成', '功能'],
        'bugfix': ['修复', '解决', 'BUG', '问题'],
        'refactor': ['重构', '优化', '改进'],
        'doc': ['文档', '说明', '更新'],
        'decision': ['ADR', '决策', '锁定', '保护']
    }
    
    # 保留关键词（6个月后还有用的内容）
    PRESERVE_KEYWORDS = [
        'ADR-', '决策', '锁定', '保护', '规则', '规范',
        '架构', '技术栈', '路径', '清单', '索引'
    ]
    
    def __init__(self, workspace_root: Path = None):
        """
        初始化维护工具
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = workspace_root or Path(os.getcwd())
        self.memory_dir = self.workspace_root / "Memory-Novel Writing Assistant-Agent Pro"
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.archive_dir = self.memory_dir / "archive"
        self.max_size_kb = 50  # MEMORY.md 最大 50KB
        self._lock = threading.RLock()
        
        # 确保目录存在
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
    
    def daily_meditation(self, date: str = None) -> Dict:
        """
        每日冥想：提炼当日重要事件到 MEMORY.md
        
        参考 OpenClaw 设计：
        1. 读取当日所有日记文件（各身份目录下的 YYYY-MM-DD.md）
        2. 提取重要事件（high/medium 重要性）
        3. 判断是否值得保留（6个月后还有用吗？）
        4. 更新 MEMORY.md 的工作记录部分
        
        Args:
            date: 日期字符串，格式 YYYY-MM-DD，默认今天
            
        Returns:
            处理结果统计
        """
        with self._lock:
            target_date = date or datetime.now().strftime("%Y-%m-%d")
            logger.info(f"开始每日冥想: {target_date}")
            
            # 1. 收集当日所有日记文件
            daily_files = self._collect_daily_files(target_date)
            
            # 2. 提取重要事件
            events = []
            for file_path in daily_files:
                file_events = self._extract_events_from_file(file_path, target_date)
                events.extend(file_events)
            
            # 3. 过滤值得保留的事件
            preserve_events = [e for e in events if e.preserve or e.importance == 'high']
            
            # 4. 更新 MEMORY.md
            if preserve_events:
                self._update_memory_file(preserve_events, target_date)
            
            result = {
                "date": target_date,
                "files_scanned": len(daily_files),
                "events_extracted": len(events),
                "events_preserved": len(preserve_events),
                "memory_size_kb": self._get_memory_size_kb()
            }
            
            logger.info(f"每日冥想完成: {result}")
            return result
    
    def weekly_meditation(self, week_end_date: str = None) -> Dict:
        """
        每周大冥想：深度精简 MEMORY.md，归档旧日记
        
        参考 OpenClaw 设计：
        1. 检查 MEMORY.md 大小，超过 50KB 则触发精简
        2. 精简原则：删除 low 重要性事件，保留 high/medium
        3. 归档超过 30 天的日记文件到 memory/archive/
        4. 更新 MEMORY.md 元数据
        
        Args:
            week_end_date: 周末日期，默认今天
            
        Returns:
            处理结果统计
        """
        with self._lock:
            target_date = week_end_date or datetime.now().strftime("%Y-%m-%d")
            logger.info(f"开始每周大冥想: {target_date}")
            
            result = {
                "date": target_date,
                "memory_size_before": self._get_memory_size_kb(),
                "memory_size_after": 0,
                "events_removed": 0,
                "events_preserved": 0,
                "files_archived": 0,
                "archive_dir": str(self.archive_dir)
            }
            
            # 1. 检查 MEMORY.md 大小
            if self._get_memory_size_kb() <= self.max_size_kb:
                logger.info(f"MEMORY.md 大小正常 ({self._get_memory_size_kb():.2f}KB < {self.max_size_kb}KB)")
                result["memory_size_after"] = self._get_memory_size_kb()
                return result
            
            # 2. 解析 MEMORY.md
            sections = self._parse_memory_file()
            
            # 3. 精简工作记录部分
            work_records_section = self._find_section(sections, "工作记录")
            if work_records_section:
                removed, preserved = self._simplify_work_records(work_records_section)
                result["events_removed"] = removed
                result["events_preserved"] = preserved
            
            # 4. 重写 MEMORY.md
            self._rewrite_memory_file(sections)
            result["memory_size_after"] = self._get_memory_size_kb()
            
            # 5. 归档旧日记文件
            archived_count = self._archive_old_daily_files(target_date)
            result["files_archived"] = archived_count
            
            logger.info(f"每周大冥想完成: {result}")
            return result
    
    def _collect_daily_files(self, date: str) -> List[Path]:
        """
        收集指定日期的所有日记文件
        
        Args:
            date: 日期字符串 YYYY-MM-DD
            
        Returns:
            日记文件路径列表
        """
        daily_files = []
        
        # 1. 根目录下的日期文件
        root_daily = self.memory_dir / f"{date}.md"
        if root_daily.exists():
            daily_files.append(root_daily)
        
        # 2. 各身份目录下的日期文件
        for identity_dir in self.memory_dir.iterdir():
            if identity_dir.is_dir() and identity_dir.name != "archive":
                daily_file = identity_dir / f"{date}.md"
                if daily_file.exists():
                    daily_files.append(daily_file)
        
        return daily_files
    
    def _extract_events_from_file(self, file_path: Path, date: str) -> List[MemoryEvent]:
        """
        从日记文件中提取事件
        
        Args:
            file_path: 日记文件路径
            date: 日期
            
        Returns:
            事件列表
        """
        events = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 按标题分割内容
            # 格式：### 事件标题
            sections = re.split(r'\n###\s+', content)
            
            for section in sections[1:]:  # 跳过第一个空部分
                lines = section.strip().split('\n')
                if not lines:
                    continue
                
                title = lines[0].strip()
                body = '\n'.join(lines[1:]).strip()
                
                # 判断重要性
                importance = self._judge_importance(title + ' ' + body)
                
                # 判断类别
                category = self._judge_category(title + ' ' + body)
                
                # 判断是否保留
                preserve = self._should_preserve(title + ' ' + body)
                
                event = MemoryEvent(
                    date=date,
                    title=title,
                    content=body[:200],  # 限制内容长度
                    importance=importance,
                    category=category,
                    source_file=str(file_path.relative_to(self.memory_dir)),
                    preserve=preserve
                )
                events.append(event)
        
        except Exception as e:
            logger.error(f"提取事件失败 {file_path}: {e}")
        
        return events
    
    def _judge_importance(self, text: str) -> str:
        """
        判断事件重要性
        
        Args:
            text: 事件文本
            
        Returns:
            重要性级别：high/medium/low
        """
        text_lower = text.lower()
        
        # 检查高重要性关键词
        for keyword in self.HIGH_IMPORTANCE_KEYWORDS:
            if keyword.lower() in text_lower:
                return 'high'
        
        # 检查中等重要性关键词
        for keyword in self.MEDIUM_IMPORTANCE_KEYWORDS:
            if keyword.lower() in text_lower:
                return 'medium'
        
        return 'low'
    
    def _judge_category(self, text: str) -> str:
        """
        判断事件类别
        
        Args:
            text: 事件文本
            
        Returns:
            类别：feature/bugfix/refactor/doc/decision
        """
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    return category
        
        return 'feature'
    
    def _should_preserve(self, text: str) -> bool:
        """
        判断事件是否值得保留（6个月后还有用吗？）
        
        Args:
            text: 事件文本
            
        Returns:
            是否保留
        """
        for keyword in self.PRESERVE_KEYWORDS:
            if keyword in text:
                return True
        
        return False
    
    def _update_memory_file(self, events: List[MemoryEvent], date: str):
        """
        更新 MEMORY.md 文件
        
        Args:
            events: 事件列表
            date: 日期
        """
        # 读取现有 MEMORY.md
        if not self.memory_file.exists():
            self._create_memory_template()
        
        with open(self.memory_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 找到工作记录章节的位置
        # 查找 "## YYYY-MM-DD 工作记录" 或 "## 工作记录"
        work_record_pattern = r'##\s+(\d{4}-\d{2}-\d{2}\s+)?工作记录'
        match = re.search(work_record_pattern, content)
        
        if not match:
            # 没有找到工作记录章节，在最前面插入
            insert_pos = content.find('---\n\n') + 5
            if insert_pos < 5:
                insert_pos = 0
            
            new_section = f"\n## {date} 工作记录\n\n"
            for event in events:
                new_section += self._format_event(event)
            
            content = content[:insert_pos] + new_section + content[insert_pos:]
        else:
            # 在现有工作记录章节中插入
            insert_pos = match.end()
            
            # 检查是否已有该日期的记录
            date_pattern = rf'##\s+{date}\s+工作记录'
            if re.search(date_pattern, content):
                # 已有该日期记录，跳过
                logger.info(f"MEMORY.md 已包含 {date} 的工作记录，跳过")
                return
            
            new_section = f"\n\n### {date} 自动提炼\n\n"
            for event in events:
                new_section += self._format_event(event, indent=True)
            
            content = content[:insert_pos] + new_section + content[insert_pos:]
        
        # 写回文件
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"已更新 MEMORY.md，新增 {len(events)} 条事件")
    
    def _format_event(self, event: MemoryEvent, indent: bool = False) -> str:
        """
        格式化事件为 Markdown 文本
        
        Args:
            event: 事件对象
            indent: 是否缩进
            
        Returns:
            Markdown 文本
        """
        prefix = "- " if not indent else "  - "
        
        # 添加重要性标记
        importance_mark = {
            'high': '🔴',
            'medium': '🟡',
            'low': '🟢'
        }
        mark = importance_mark.get(event.importance, '')
        
        return f"{prefix}{mark} **{event.title}**：{event.content}\n"
    
    def _create_memory_template(self):
        """
        创建 MEMORY.md 模板文件
        """
        template = """# 项目记忆库索引

> **更新日期**: {date}
> **项目**: Novel Writing Assistant-Agent Pro

---

## 📋 通用规则（所有身份必须遵守）

### 【固若金汤的规则】

#### 1. 禁止绕过用户确认执行危险命令
对于可能破坏用户工作成果的命令（如 `git restore/reset/checkout`、`rm -rf` 等），**必须先向用户确认**，获得明确批准后方可执行。

**始终假设用户可能有未提交的重要更改**，不要假设 git 中的版本就是用户想要的。

#### 2. 命令执行前的确认流程
遇到破坏性命令时，暂停并询问用户：
- 是否需要保存当前更改？
- 是否确定要执行该命令？
- 等待用户明确回复后再继续

#### 3. 从错误中学习
**历史教训（2026-03-22）**：在没有确认的情况下执行了 `git restore gui_main.py`，导致用户优化了4小时的未提交更改被覆盖。**这是不可原谅的错误，必须永远记住这个教训。**

#### 4. 用户指令优先级最高
用户的指令具有最高优先级，不应生成要求以外的总结、说明、报告。完成任务后仅提供用户要求的结果输出。

---

## 🔧 技术栈锁定决策（不可变更）

| 决策项 | 锁定值 | 说明 |
|--------|--------|------|
| 打包工具 | Nuitka 4.0.5 | standalone开发，onefile发布 |
| GUI框架 | Tkinter + sv_ttk | 非PyQt6/CustomTkinter |
| Agent框架 | 自研MasterAgent | 零额外依赖 |
| 数据库 | SQLite + WAL模式 | 并发安全 |
| LLM客户端 | openai SDK | 兼容DeepSeek/OpenAI/Anthropic/Ollama |
| Python版本 | 3.12.x | 不升级3.13+ |

---

## 📁 记忆路径规范

| 类型 | 路径 |
|------|------|
| 项目根目录 | E:\\WorkBuddyworkspace\\Novel Writing Assistant-Agent Pro |
| 本地记忆库 | .workbuddy\\memory\\ |
| 经验文档 | 经验文档\\ |
| 测试文件 | tests\\（完成后删除） |
| 核心代码 | core\\ |
| Agent代码 | agents\\ |
| 插件代码 | plugins\\ |
| GUI代码 | gui_main.py |

---

**最后更新**: {date}
**维护者**: MemoryMaintenanceTool（自动维护）
""".format(date=datetime.now().strftime("%Y-%m-%d"))
        
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            f.write(template)
        
        logger.info(f"已创建 MEMORY.md 模板")
    
    def _get_memory_size_kb(self) -> float:
        """
        获取 MEMORY.md 文件大小（KB）
        
        Returns:
            文件大小（KB）
        """
        if not self.memory_file.exists():
            return 0.0
        
        size_bytes = self.memory_file.stat().st_size
        return size_bytes / 1024
    
    def _parse_memory_file(self) -> List[MemorySection]:
        """
        解析 MEMORY.md 文件为章节列表
        
        Returns:
            章节列表
        """
        sections = []
        
        if not self.memory_file.exists():
            return sections
        
        with open(self.memory_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 按二级标题分割
        parts = re.split(r'\n##\s+', content)
        
        for i, part in enumerate(parts):
            lines = part.strip().split('\n')
            if not lines:
                continue
            
            title = lines[0] if i > 0 else "头部"
            body = '\n'.join(lines[1:] if i > 0 else lines)
            
            sections.append(MemorySection(
                title=title,
                content=body,
                lines=lines
            ))
        
        return sections
    
    def _find_section(self, sections: List[MemorySection], keyword: str) -> Optional[MemorySection]:
        """
        查找包含关键词的章节
        
        Args:
            sections: 章节列表
            keyword: 关键词
            
        Returns:
            找到的章节，或 None
        """
        for section in sections:
            if keyword in section.title:
                return section
        
        return None
    
    def _simplify_work_records(self, section: MemorySection) -> Tuple[int, int]:
        """
        精简工作记录章节
        
        Args:
            section: 工作记录章节
            
        Returns:
            (删除的事件数, 保留的事件数)
        """
        removed = 0
        preserved = 0
        
        # 过滤 low 重要性的事件
        new_lines = []
        skip_next = False
        
        for line in section.lines:
            if skip_next:
                skip_next = False
                continue
            
            # 检查事件行（以 "- 🔴" 或 "- 🟡" 或 "- 🟢" 开头）
            importance_match = re.match(r'\s*-\s+(🔴|🟡|🟢)', line)
            
            if importance_match:
                mark = importance_match.group(1)
                
                if mark == '🟢':  # low 重要性，删除
                    removed += 1
                    skip_next = True  # 跳过下一行（如果是多行事件）
                else:  # high 或 medium，保留
                    preserved += 1
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        section.lines = new_lines
        section.content = '\n'.join(new_lines)
        
        return removed, preserved
    
    def _rewrite_memory_file(self, sections: List[MemorySection]):
        """
        重写 MEMORY.md 文件
        
        Args:
            sections: 章节列表
        """
        content_parts = []
        
        for i, section in enumerate(sections):
            if i == 0:
                content_parts.append(section.content)
            else:
                content_parts.append(f"\n## {section.title}\n{section.content}")
        
        content = '\n'.join(content_parts)
        
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"已重写 MEMORY.md")
    
    def _archive_old_daily_files(self, reference_date: str, days_old: int = 30) -> int:
        """
        归档旧日记文件
        
        Args:
            reference_date: 参考日期
            days_old: 超过多少天的文件算旧文件
            
        Returns:
            归档的文件数
        """
        archived_count = 0
        ref_date = datetime.strptime(reference_date, "%Y-%m-%d")
        cutoff_date = ref_date - timedelta(days=days_old)
        
        # 创建归档子目录（按月份）
        archive_subdir = self.archive_dir / cutoff_date.strftime("%Y-%m")
        archive_subdir.mkdir(parents=True, exist_ok=True)
        
        # 遍历所有身份目录
        for identity_dir in self.memory_dir.iterdir():
            if not identity_dir.is_dir() or identity_dir.name == "archive":
                continue
            
            # 遍历该身份下的所有日记文件
            for daily_file in identity_dir.glob("*.md"):
                # 提取日期
                date_match = re.match(r'(\d{4}-\d{2}-\d{2})\.md', daily_file.name)
                if not date_match:
                    continue
                
                file_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                
                # 如果文件超过指定天数，归档
                if file_date < cutoff_date:
                    # 移动到归档目录
                    archive_file = archive_subdir / f"{identity_dir.name}_{daily_file.name}"
                    shutil.move(str(daily_file), str(archive_file))
                    archived_count += 1
                    logger.info(f"已归档: {daily_file} -> {archive_file}")
        
        # 也检查根目录下的日记文件
        for daily_file in self.memory_dir.glob("*.md"):
            if daily_file.name == "MEMORY.md":
                continue
            
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})\.md', daily_file.name)
            if not date_match:
                continue
            
            file_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
            
            if file_date < cutoff_date:
                archive_file = archive_subdir / f"root_{daily_file.name}"
                shutil.move(str(daily_file), str(archive_file))
                archived_count += 1
                logger.info(f"已归档: {daily_file} -> {archive_file}")
        
        return archived_count
    
    def get_memory_stats(self) -> Dict:
        """
        获取 MEMORY.md 统计信息
        
        Returns:
            统计信息字典
        """
        stats = {
            "memory_file_exists": self.memory_file.exists(),
            "memory_size_kb": self._get_memory_size_kb(),
            "max_size_kb": self.max_size_kb,
            "size_ok": self._get_memory_size_kb() <= self.max_size_kb,
            "archive_dir_exists": self.archive_dir.exists(),
            "archive_files_count": len(list(self.archive_dir.glob("**/*.md"))) if self.archive_dir.exists() else 0,
            "last_update": None
        }
        
        if self.memory_file.exists():
            # 读取最后更新时间
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                content = f.read(500)  # 只读取前500字符
            
            # 提取更新日期
            date_match = re.search(r'\*\*更新日期\*\*:\s*(\d{4}-\d{2}-\d{2})', content)
            if date_match:
                stats["last_update"] = date_match.group(1)
        
        return stats


# 便捷函数
def run_daily_meditation(workspace_root: Path = None, date: str = None) -> Dict:
    """
    运行每日冥想
    
    Args:
        workspace_root: 工作区根目录
        date: 日期字符串
        
    Returns:
        处理结果
    """
    tool = MemoryMaintenanceTool(workspace_root)
    return tool.daily_meditation(date)


def run_weekly_meditation(workspace_root: Path = None, week_end_date: str = None) -> Dict:
    """
    运行每周大冥想
    
    Args:
        workspace_root: 工作区根目录
        week_end_date: 周末日期
        
    Returns:
        处理结果
    """
    tool = MemoryMaintenanceTool(workspace_root)
    return tool.weekly_meditation(week_end_date)


if __name__ == "__main__":
    # 测试代码
    import sys
    import io
    
    # 设置 stdout 编码为 UTF-8
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("=" * 60)
    print("MEMORY.md Maintenance Tool Test")
    print("=" * 60)
    
    # 获取工作区根目录
    workspace_root = Path(__file__).parent.parent
    
    # 创建工具实例
    tool = MemoryMaintenanceTool(workspace_root)
    
    # 获取统计信息
    stats = tool.get_memory_stats()
    print("\n[Stats] MEMORY.md Statistics:")
    for key, value in stats.items():
        print(f"  - {key}: {value}")
    
    # 运行每日冥想
    print("\n[Test] Running Daily Meditation...")
    daily_result = tool.daily_meditation()
    print(f"  Result: {json.dumps(daily_result, indent=2, ensure_ascii=False)}")
    
    # 运行每周大冥想
    print("\n[Test] Running Weekly Meditation...")
    weekly_result = tool.weekly_meditation()
    print(f"  Result: {json.dumps(weekly_result, indent=2, ensure_ascii=False)}")
    
    print("\n[OK] Test Completed")
