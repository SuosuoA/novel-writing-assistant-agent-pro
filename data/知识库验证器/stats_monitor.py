#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统计监控器 - 清理统计看板

提供知识库清理功能的统计和监控能力：
- 清理历史记录
- 统计看板数据
- 定期清理任务调度

P3优化：监控增强
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class CleanupStats:
    """单次清理统计"""
    
    def __init__(self,
                 timestamp: str,
                 total_knowledge: int,
                 dedup_removed: int,
                 quality_removed: int,
                 removed_count: int,
                 final_count: int,
                 duration_seconds: float = 0.0):
        self.timestamp = timestamp
        self.total_knowledge = total_knowledge
        self.dedup_removed = dedup_removed
        self.quality_removed = quality_removed
        self.removed_count = removed_count
        self.final_count = final_count
        self.duration_seconds = duration_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "total_knowledge": self.total_knowledge,
            "dedup_removed": self.dedup_removed,
            "quality_removed": self.quality_removed,
            "removed_count": self.removed_count,
            "final_count": self.final_count,
            "duration_seconds": self.duration_seconds
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CleanupStats':
        return cls(
            timestamp=data.get("timestamp", ""),
            total_knowledge=data.get("total_knowledge", 0),
            dedup_removed=data.get("dedup_removed", 0),
            quality_removed=data.get("quality_removed", 0),
            removed_count=data.get("removed_count", 0),
            final_count=data.get("final_count", 0),
            duration_seconds=data.get("duration_seconds", 0.0)
        )


class StatsMonitor:
    """统计监控器"""
    
    def __init__(self, workspace_root: Path):
        """
        初始化统计监控器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = Path(workspace_root)
        self.stats_dir = self.workspace_root / "data" / "知识库验证器" / "stats"
        self.stats_file = self.stats_dir / "cleanup_history.json"
        self.stats_dir.mkdir(parents=True, exist_ok=True)
        
        # P3优化：从配置读取统计保留天数
        try:
            from .config_loader import get_config_loader
            config = get_config_loader().get_monitoring_config()
            self.retention_days = config.get("stats_retention_days", 90)
        except ImportError:
            self.retention_days = 90
        
        self._history: List[CleanupStats] = self._load_history()
        
        logger.info(f"[STATS_MONITOR] 初始化完成, 历史记录: {len(self._history)}条")
    
    def _load_history(self) -> List[CleanupStats]:
        """加载历史记录"""
        if not self.stats_file.exists():
            return []
        
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [CleanupStats.from_dict(item) for item in data]
        except Exception as e:
            logger.error(f"[STATS_MONITOR] 加载历史记录失败: {e}")
            return []
    
    def _save_history(self) -> bool:
        """保存历史记录"""
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(
                    [stat.to_dict() for stat in self._history],
                    f,
                    ensure_ascii=False,
                    indent=2
                )
            return True
        except Exception as e:
            logger.error(f"[STATS_MONITOR] 保存历史记录失败: {e}")
            return False
    
    def record_cleanup(self, stats: CleanupStats) -> bool:
        """
        记录一次清理
        
        Args:
            stats: 清理统计
        
        Returns:
            是否成功
        """
        self._history.append(stats)
        
        # 清理过期记录
        self._cleanup_old_records()
        
        # 保存
        success = self._save_history()
        
        if success:
            logger.info(f"[STATS_MONITOR] 记录清理: 删除{stats.removed_count}条")
        
        return success
    
    def _cleanup_old_records(self):
        """清理过期记录"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        original_count = len(self._history)
        self._history = [
            stat for stat in self._history
            if datetime.fromisoformat(stat.timestamp) > cutoff_date
        ]
        
        removed = original_count - len(self._history)
        if removed > 0:
            logger.info(f"[STATS_MONITOR] 清理过期记录: {removed}条")
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        获取看板数据
        
        Returns:
            {
                "total_cleanups": 10,
                "total_removed": 500,
                "avg_removed_per_cleanup": 50,
                "recent_cleanups": [...],
                "removal_trend": [...],
                "category_distribution": {...}
            }
        """
        if not self._history:
            return {
                "total_cleanups": 0,
                "total_removed": 0,
                "avg_removed_per_cleanup": 0,
                "recent_cleanups": [],
                "removal_trend": [],
                "category_distribution": {}
            }
        
        # 基础统计
        total_cleanups = len(self._history)
        total_removed = sum(stat.removed_count for stat in self._history)
        avg_removed = total_removed / total_cleanups if total_cleanups > 0 else 0
        
        # 最近10次清理
        recent_cleanups = [
            stat.to_dict() for stat in self._history[-10:]
        ]
        
        # 删除趋势（最近7天）
        removal_trend = self._calculate_removal_trend()
        
        # 删除原因分布
        category_distribution = self._calculate_category_distribution()
        
        return {
            "total_cleanups": total_cleanups,
            "total_removed": total_removed,
            "avg_removed_per_cleanup": round(avg_removed, 1),
            "recent_cleanups": recent_cleanups,
            "removal_trend": removal_trend,
            "category_distribution": category_distribution,
            "last_updated": datetime.now().isoformat()
        }
    
    def _calculate_removal_trend(self) -> List[Dict[str, Any]]:
        """计算删除趋势（最近7天）"""
        trend = []
        today = datetime.now().date()
        
        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            date_str = date.isoformat()
            
            # 计算当天的删除总数
            day_removed = sum(
                stat.removed_count
                for stat in self._history
                if datetime.fromisoformat(stat.timestamp).date() == date
            )
            
            trend.append({
                "date": date_str,
                "removed": day_removed
            })
        
        return trend
    
    def _calculate_category_distribution(self) -> Dict[str, int]:
        """计算删除原因分布"""
        distribution = defaultdict(int)
        
        for stat in self._history:
            distribution["重复词条"] += stat.dedup_removed
            distribution["低质量"] += stat.quality_removed
        
        return dict(distribution)
    
    def get_summary_report(self) -> str:
        """
        获取摘要报告（文本格式）
        
        Returns:
            摘要报告文本
        """
        data = self.get_dashboard_data()
        
        report = []
        report.append("=" * 50)
        report.append("知识库清理统计看板")
        report.append("=" * 50)
        report.append("")
        report.append(f"📊 总体统计")
        report.append(f"  - 清理次数: {data['total_cleanups']}次")
        report.append(f"  - 总删除数: {data['total_removed']}条")
        report.append(f"  - 平均每次删除: {data['avg_removed_per_cleanup']}条")
        report.append("")
        
        if data['category_distribution']:
            report.append(f"📈 删除原因分布")
            for category, count in data['category_distribution'].items():
                report.append(f"  - {category}: {count}条")
            report.append("")
        
        if data['removal_trend']:
            report.append(f"📉 最近7天趋势")
            for item in data['removal_trend']:
                report.append(f"  - {item['date']}: {item['removed']}条")
            report.append("")
        
        report.append(f"🕐 更新时间: {data['last_updated']}")
        
        return "\n".join(report)
    
    def export_to_csv(self, output_path: Path) -> bool:
        """
        导出历史记录到CSV
        
        Args:
            output_path: 输出文件路径
        
        Returns:
            是否成功
        """
        import csv
        
        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # 写入表头
                writer.writerow([
                    "时间", "原始数量", "重复删除", "质量删除",
                    "总删除", "最终数量", "耗时(秒)"
                ])
                
                # 写入数据
                for stat in self._history:
                    writer.writerow([
                        stat.timestamp,
                        stat.total_knowledge,
                        stat.dedup_removed,
                        stat.quality_removed,
                        stat.removed_count,
                        stat.final_count,
                        stat.duration_seconds
                    ])
            
            logger.info(f"[STATS_MONITOR] 导出CSV成功: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"[STATS_MONITOR] 导出CSV失败: {e}")
            return False


class ScheduledCleanupManager:
    """定期清理任务调度器"""
    
    def __init__(self, workspace_root: Path):
        """
        初始化调度器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = Path(workspace_root)
        self.schedule_file = self.workspace_root / "data" / "知识库验证器" / "schedule.json"
        self._load_schedule()
        
        logger.info("[SCHEDULE_MANAGER] 初始化完成")
    
    def _load_schedule(self):
        """加载调度配置"""
        self.schedule = {
            "enabled": False,
            "interval_days": 7,
            "last_run": None,
            "next_run": None
        }
        
        if self.schedule_file.exists():
            try:
                with open(self.schedule_file, 'r', encoding='utf-8') as f:
                    self.schedule.update(json.load(f))
            except Exception as e:
                logger.error(f"[SCHEDULE_MANAGER] 加载调度配置失败: {e}")
    
    def _save_schedule(self):
        """保存调度配置"""
        try:
            with open(self.schedule_file, 'w', encoding='utf-8') as f:
                json.dump(self.schedule, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[SCHEDULE_MANAGER] 保存调度配置失败: {e}")
    
    def enable_scheduled_cleanup(self, interval_days: int = 7) -> bool:
        """
        启用定期清理
        
        Args:
            interval_days: 间隔天数
        
        Returns:
            是否成功
        """
        self.schedule["enabled"] = True
        self.schedule["interval_days"] = interval_days
        self.schedule["next_run"] = self._calculate_next_run()
        
        self._save_schedule()
        
        logger.info(f"[SCHEDULE_MANAGER] 启用定期清理, 间隔{interval_days}天")
        return True
    
    def disable_scheduled_cleanup(self) -> bool:
        """
        禁用定期清理
        
        Returns:
            是否成功
        """
        self.schedule["enabled"] = False
        self._save_schedule()
        
        logger.info("[SCHEDULE_MANAGER] 禁用定期清理")
        return True
    
    def _calculate_next_run(self) -> str:
        """计算下次运行时间"""
        last_run = self.schedule.get("last_run")
        interval = self.schedule.get("interval_days", 7)
        
        if last_run:
            last_date = datetime.fromisoformat(last_run)
            next_date = last_date + timedelta(days=interval)
        else:
            next_date = datetime.now() + timedelta(days=interval)
        
        return next_date.isoformat()
    
    def check_should_run(self) -> bool:
        """
        检查是否应该执行清理
        
        Returns:
            是否应该执行
        """
        if not self.schedule.get("enabled", False):
            return False
        
        next_run = self.schedule.get("next_run")
        if not next_run:
            return True
        
        return datetime.now() >= datetime.fromisoformat(next_run)
    
    def mark_run_completed(self):
        """标记清理完成"""
        self.schedule["last_run"] = datetime.now().isoformat()
        self.schedule["next_run"] = self._calculate_next_run()
        self._save_schedule()
        
        logger.info(f"[SCHEDULE_MANAGER] 清理完成, 下次运行: {self.schedule['next_run']}")


def get_stats_monitor(workspace_root: Path) -> StatsMonitor:
    """获取统计监控器实例"""
    return StatsMonitor(workspace_root)


def get_schedule_manager(workspace_root: Path) -> ScheduledCleanupManager:
    """获取调度管理器实例"""
    return ScheduledCleanupManager(workspace_root)


if __name__ == "__main__":
    # 测试统计监控器
    from pathlib import Path
    
    monitor = StatsMonitor(Path("."))
    
    # 添加测试数据
    test_stat = CleanupStats(
        timestamp=datetime.now().isoformat(),
        total_knowledge=1000,
        dedup_removed=50,
        quality_removed=30,
        removed_count=80,
        final_count=920,
        duration_seconds=45.5
    )
    
    monitor.record_cleanup(test_stat)
    
    # 获取看板数据
    print(monitor.get_summary_report())
