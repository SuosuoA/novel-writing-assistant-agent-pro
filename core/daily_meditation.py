"""
每日冥想定时任务 - OpenClaw自我优化机制

V1.0版本
创建日期：2026-03-28

功能：
- 定时总结当日工作
- 提取经验教训
- 更新MEMORY.md
- 压缩冷数据
- 优化向量索引

设计参考：
- OpenClaw mem9 每日冥想机制
- 升级方案10.1

使用示例：
    from core.daily_meditation import DailyMeditationScheduler
    
    # 启动调度器
    scheduler = DailyMeditationScheduler()
    scheduler.start()
    
    # 配置每日23:00执行
    scheduler.schedule_daily_meditation(hour=23, minute=0)
"""

import logging
import threading
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# 尝试导入APScheduler
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logging.warning("[DailyMeditation] APScheduler未安装，定时任务功能不可用")

from .config_service import get_config_service
from .session_state import get_session_state_manager
from .wal_manager import get_wal_manager

logger = logging.getLogger(__name__)


class DailyMeditation:
    """
    每日冥想执行器
    
    执行以下优化操作：
    1. 总结当日工作
    2. 提取经验教训
    3. 更新MEMORY.md
    4. 压缩冷数据
    5. 优化向量索引
    """
    
    def __init__(self, workspace: Optional[Path] = None):
        """
        初始化每日冥想执行器
        
        Args:
            workspace: 工作区路径
        """
        self.workspace = workspace or Path.cwd()
        self.config = get_config_service()
        self.session_manager = get_session_state_manager(self.workspace)
        self.wal_manager = get_wal_manager(self.workspace)
        
        # 冥想结果存储路径
        self.meditation_dir = self.workspace / ".workbuddy" / "meditations"
        self.meditation_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("[DailyMeditation] 初始化完成")
    
    def execute(self) -> Dict[str, Any]:
        """
        执行每日冥想（V2.0 - 集成量化指标）
        
        Returns:
            Dict: 冥想结果
        """
        logger.info("=" * 60)
        logger.info("[DailyMeditation] 开始每日冥想...")
        logger.info("=" * 60)
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "workspace": str(self.workspace),
            "steps": {}
        }
        
        try:
            # 1. 收集当日数据
            daily_data = self._collect_daily_data()
            results["steps"]["data_collection"] = {
                "status": "success",
                "word_count": daily_data.get("word_count", 0),
                "operations": daily_data.get("total_operations", 0)
            }
            logger.info(f"[DailyMeditation] 数据收集完成: {daily_data.get('word_count', 0)}字, {daily_data.get('total_operations', 0)}次操作")
            
            # 2. 计算核心指标（V2.0新增）
            metrics_report = self._calculate_metrics()
            results["steps"]["metrics_calculation"] = {
                "status": "success",
                "overall_score": metrics_report.overall_score,
                "pass_rate": metrics_report.pass_rate
            }
            logger.info(f"[DailyMeditation] 指标计算: 整体评分{metrics_report.overall_score:.2%}, 达标率{metrics_report.pass_rate:.1%}")
            
            # 3. 分析工作效率
            analysis = self._analyze_productivity(daily_data)
            analysis["metrics"] = {
                "overall_score": metrics_report.overall_score,
                "pass_rate": metrics_report.pass_rate
            }
            results["steps"]["productivity_analysis"] = {
                "status": "success",
                "avg_score": analysis.get("avg_score", 0),
                "efficiency": analysis.get("efficiency", "unknown")
            }
            logger.info(f"[DailyMeditation] 效率分析: 平均分{analysis.get('avg_score', 0):.2f}, 效率{analysis.get('efficiency', 'unknown')}")
            
            # 4. 提取经验教训
            lessons = self._extract_lessons(daily_data, analysis)
            results["steps"]["lesson_extraction"] = {
                "status": "success",
                "lessons_count": len(lessons)
            }
            logger.info(f"[DailyMeditation] 提取经验: {len(lessons)}条")
            
            # 5. 更新MEMORY.md
            memory_updated = self._update_memory(lessons)
            results["steps"]["memory_update"] = {
                "status": "success" if memory_updated else "skipped",
                "updated": memory_updated
            }
            logger.info(f"[DailyMeditation] MEMORY更新: {'成功' if memory_updated else '跳过'}")
            
            # 6. 压缩冷数据
            compressed = self._compress_cold_data()
            results["steps"]["data_compression"] = {
                "status": "success" if compressed else "skipped",
                "compressed": compressed
            }
            logger.info(f"[DailyMeditation] 数据压缩: {'成功' if compressed else '跳过'}")
            
            # 7. 更新知识库（V3.0新增 - 从用户反馈提取知识点）
            knowledge_result = self._update_knowledge_base()
            results["steps"]["knowledge_update"] = knowledge_result
            logger.info(f"[DailyMeditation] 知识库更新: 新增{knowledge_result.get('added_knowledge', 0)}条")
            
            # 8. 保存冥想记录
            self._save_meditation_log(results)
            
            logger.info("=" * 60)
            logger.info("[DailyMeditation] 每日冥想完成")
            logger.info("=" * 60)
            
            return results
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"[DailyMeditation] 冥想执行失败: {error_msg}")
            results["error"] = error_msg
            return results
    
    def _calculate_metrics(self):
        """计算核心指标（V2.0新增）"""
        try:
            from .metrics_monitor import get_metrics_monitor
            
            monitor = get_metrics_monitor(self.workspace)
            report = monitor.calculate_all_metrics(period_days=30)
            
            # 保存报告
            monitor.save_report(report)
            
            return report
            
        except Exception as e:
            logger.error(f"[DailyMeditation] 指标计算失败: {e}")
            # 返回默认报告
            from .metrics_monitor import MetricsReport
            return MetricsReport(
                period_start=datetime.now().isoformat(),
                period_end=datetime.now().isoformat()
            )
    
    def _collect_daily_data(self) -> Dict[str, Any]:
        """收集当日工作数据"""
        try:
            # 获取SessionState
            state = self.session_manager.get_state()
            
            # 获取WAL统计
            wal_stats = self.wal_manager.get_wal_stats()
            
            return {
                "word_count": state.temp_context.word_count,
                "total_operations": wal_stats.get("total_writes", 0),
                "failed_operations": wal_stats.get("failed_writes", 0),
                "success_rate": wal_stats.get("success_rate", 0),
                "last_operation": state.active_task.last_operation,
                "current_chapter": state.temp_context.current_chapter,
                "characters_involved": state.temp_context.characters_involved,
                "latest_score": state.pending_data.latest_score
            }
            
        except Exception as e:
            logger.warning(f"[DailyMeditation] 数据收集失败: {e}")
            return {}
    
    def _analyze_productivity(self, daily_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析工作效率"""
        try:
            word_count = daily_data.get("word_count", 0)
            operations = daily_data.get("total_operations", 0)
            success_rate = daily_data.get("success_rate", 0)
            latest_score = daily_data.get("latest_score", 0)
            
            # 计算平均评分（结合最新评分和成功率）
            avg_score = (latest_score + success_rate / 100) / 2 if latest_score and success_rate else 0
            
            # 判断效率等级
            if avg_score >= 0.8 and success_rate >= 90:
                efficiency = "excellent"
            elif avg_score >= 0.6 and success_rate >= 70:
                efficiency = "good"
            elif avg_score >= 0.4 and success_rate >= 50:
                efficiency = "average"
            else:
                efficiency = "needs_improvement"
            
            return {
                "avg_score": avg_score,
                "efficiency": efficiency,
                "word_count": word_count,
                "operations": operations,
                "success_rate": success_rate
            }
            
        except Exception as e:
            logger.warning(f"[DailyMeditation] 效率分析失败: {e}")
            return {"avg_score": 0, "efficiency": "unknown"}
    
    def _extract_lessons(
        self,
        daily_data: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> List[str]:
        """提取经验教训"""
        lessons = []
        
        try:
            # 基于数据分析提取经验
            efficiency = analysis.get("efficiency", "unknown")
            success_rate = daily_data.get("success_rate", 0)
            word_count = daily_data.get("word_count", 0)
            
            # 效率相关经验
            if efficiency == "excellent":
                lessons.append("当前配置表现优异，保持现有设置")
            elif efficiency == "needs_improvement":
                if success_rate < 50:
                    lessons.append("API调用失败率较高，建议检查网络连接或更换API端点")
                if word_count < 1000:
                    lessons.append("生成字数较少，可尝试提高temperature或调整prompt")
            
            # 字数相关经验
            if word_count > 5000:
                lessons.append(f"今日高产{word_count}字，注意保存进度")
            
            # 成功率相关经验
            if success_rate < 100 and success_rate > 0:
                lessons.append(f"成功率{success_rate:.1f}%，仍有优化空间")
            
            # 如果没有提取到经验，添加默认建议
            if not lessons:
                lessons.append("继续使用，积累更多数据后可提供更精准的建议")
            
        except Exception as e:
            logger.warning(f"[DailyMeditation] 经验提取失败: {e}")
            lessons.append("数据分析中遇到问题，请检查日志")
        
        return lessons
    
    def _update_memory(self, lessons: List[str]) -> bool:
        """更新MEMORY.md（Claw化L4档案记忆）"""
        try:
            # Claw化运行记忆保存位置
            memory_file = self.workspace / "Memory-Novel Writing Assistant-Agent Pro" / "MEMORY.md"
            
            # 如果MEMORY.md不存在，创建基础结构
            if not memory_file.exists():
                memory_file.parent.mkdir(parents=True, exist_ok=True)
                content = f"""# Novel Writing Assistant-Agent Pro Claw化记忆库

> 更新日期: {datetime.now().strftime("%Y-%m-%d")} | 由每日冥想自动生成

---

## 每日冥想记录

### {datetime.now().strftime("%Y-%m-%d")}

**经验教训**：
"""
                for i, lesson in enumerate(lessons, 1):
                    content += f"{i}. {lesson}\n"
                
                content += "\n---\n"
                memory_file.write_text(content, encoding="utf-8")
                logger.info(f"[DailyMeditation] 创建MEMORY.md: {memory_file}")
                return True
            
            # 追加到现有MEMORY.md
            existing = memory_file.read_text(encoding="utf-8")
            
            # 构建追加内容
            append_content = f"""
### {datetime.now().strftime("%Y-%m-%d")}

**经验教训**：
"""
            for i, lesson in enumerate(lessons, 1):
                append_content += f"{i}. {lesson}\n"
            
            append_content += "\n"
            
            # 更新文件
            updated_content = existing + append_content
            memory_file.write_text(updated_content, encoding="utf-8")
            
            logger.info(f"[DailyMeditation] 更新MEMORY.md成功")
            return True
            
        except Exception as e:
            logger.error(f"[DailyMeditation] 更新MEMORY.md失败: {e}")
            return False
    
    def _compress_cold_data(self) -> bool:
        """压缩冷数据（归档旧数据）"""
        try:
            # 查找30天前的冥想记录
            meditation_files = list(self.meditation_dir.glob("meditation_*.json"))
            
            archived_count = 0
            archive_dir = self.meditation_dir / "archive"
            archive_dir.mkdir(exist_ok=True)
            
            for file in meditation_files:
                try:
                    # 解析日期
                    date_str = file.stem.split("_")[1]  # meditation_20260328.json
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    
                    # 如果超过30天，归档
                    if (datetime.now() - file_date).days > 30:
                        archive_path = archive_dir / file.name
                        file.rename(archive_path)
                        archived_count += 1
                        
                except Exception as e:
                    logger.warning(f"[DailyMeditation] 归档文件失败 {file}: {e}")
            
            if archived_count > 0:
                logger.info(f"[DailyMeditation] 归档 {archived_count} 个旧冥想记录")
            
            return archived_count > 0
            
        except Exception as e:
            logger.warning(f"[DailyMeditation] 数据压缩失败: {e}")
            return False
    
    def _update_knowledge_base(self) -> Dict[str, Any]:
        """
        更新知识库 - 从用户反馈中提取新知识点
        
        V3.0新增：实现Claw化的知识库自动进化
        
        Returns:
            更新结果统计
        """
        result = {
            "status": "skipped",
            "extracted_knowledge": 0,
            "added_knowledge": 0,
            "feedback_processed": 0
        }
        
        try:
            from .user_feedback_loop import get_user_feedback_loop
            from .knowledge_updater import get_knowledge_updater
            
            feedback_loop = get_user_feedback_loop(self.workspace)
            updater = get_knowledge_updater(self.workspace)
            
            # 获取最近的负面反馈（24小时内）
            recent_negative = feedback_loop.get_recent_feedback(
                feedback_type="negative",
                hours=24
            )
            
            # 也获取建议类反馈
            recent_suggestions = feedback_loop.get_recent_feedback(
                feedback_type="suggestion",
                hours=24
            )
            
            # 合并反馈
            all_feedbacks = recent_negative + recent_suggestions
            
            if len(all_feedbacks) == 0:
                logger.info("[DailyMeditation] 无相关反馈，跳过知识库更新")
                return result
            
            result["feedback_processed"] = len(all_feedbacks)
            result["status"] = "processing"
            
            # 批量处理反馈
            process_result = updater.process_feedback_batch(all_feedbacks)
            
            result["extracted_knowledge"] = process_result.get("extracted_knowledge", 0)
            result["added_knowledge"] = process_result.get("added_knowledge", 0)
            result["status"] = "success"
            
            logger.info(f"[DailyMeditation] 知识库更新完成: "
                       f"处理{len(all_feedbacks)}条反馈，"
                       f"提取{result['extracted_knowledge']}条，"
                       f"新增{result['added_knowledge']}条")
            
            return result
            
        except Exception as e:
            logger.error(f"[DailyMeditation] 知识库更新失败: {e}")
            result["status"] = "error"
            result["error"] = str(e)
            return result
    
    def _save_meditation_log(self, results: Dict[str, Any]) -> None:
        """保存冥想日志"""
        try:
            log_file = self.meditation_dir / f"meditation_{datetime.now().strftime('%Y%m%d')}.json"
            
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[DailyMeditation] 冥想日志保存: {log_file}")
            
        except Exception as e:
            logger.warning(f"[DailyMeditation] 保存冥想日志失败: {e}")


class DailyMeditationScheduler:
    """
    每日冥想调度器
    
    使用APScheduler定时执行冥想任务
    """
    
    def __init__(self, workspace: Optional[Path] = None):
        """
        初始化调度器
        
        Args:
            workspace: 工作区路径
        """
        self.workspace = workspace or Path.cwd()
        self.meditation = DailyMeditation(self.workspace)
        
        # 检查APScheduler可用性
        if not APSCHEDULER_AVAILABLE:
            logger.warning("[DailyMeditationScheduler] APScheduler不可用，使用简单定时器")
            self._scheduler = None
            self._simple_timer = None
        else:
            self._scheduler = BackgroundScheduler()
            logger.info("[DailyMeditationScheduler] APScheduler初始化成功")
        
        # 读取配置
        self.config = get_config_service()
        self._enabled = self._check_enabled()
        self._schedule_time = self._get_schedule_time()
    
    def _check_enabled(self) -> bool:
        """检查每日冥想是否启用"""
        try:
            # 默认启用
            return True
        except Exception as e:
            logger.warning(f"[DailyMeditationScheduler] 读取配置失败: {e}")
            return True
    
    def _get_schedule_time(self) -> str:
        """获取调度时间"""
        try:
            # 直接读取config.yaml文件
            import yaml
            config_path = self.workspace / "config.yaml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_dict = yaml.safe_load(f)
                memory_config = config_dict.get("memory", {})
                return memory_config.get("daily_meditation_time", "23:00")
            return "23:00"
        except Exception as e:
            logger.warning(f"[DailyMeditationScheduler] 读取调度时间失败: {e}")
            return "23:00"
    
    def start(self) -> bool:
        """
        启动调度器
        
        Returns:
            bool: 是否成功启动
        """
        if not self._enabled:
            logger.info("[DailyMeditationScheduler] 每日冥想已禁用")
            return False
        
        if APSCHEDULER_AVAILABLE and self._scheduler:
            # 使用APScheduler
            try:
                hour, minute = map(int, self._schedule_time.split(":"))
                
                self._scheduler.add_job(
                    func=self.meditation.execute,
                    trigger=CronTrigger(hour=hour, minute=minute),
                    id="daily_meditation",
                    name="每日冥想",
                    replace_existing=True
                )
                
                self._scheduler.start()
                logger.info(f"[DailyMeditationScheduler] 定时任务已启动: 每日{self._schedule_time}执行冥想")
                return True
                
            except Exception as e:
                logger.error(f"[DailyMeditationScheduler] 启动失败: {e}")
                return False
        else:
            # 使用简单定时器（每24小时执行一次）
            try:
                self._schedule_simple_timer()
                logger.info("[DailyMeditationScheduler] 简单定时器已启动（每24小时执行一次）")
                return True
            except Exception as e:
                logger.error(f"[DailyMeditationScheduler] 简单定时器启动失败: {e}")
                return False
    
    def _schedule_simple_timer(self) -> None:
        """使用简单定时器（当APScheduler不可用时）"""
        def timer_callback():
            self.meditation.execute()
            # 递归调度下一次
            self._schedule_simple_timer()
        
        # 24小时后执行
        self._simple_timer = threading.Timer(24 * 60 * 60, timer_callback)
        self._simple_timer.daemon = True
        self._simple_timer.start()
    
    def stop(self) -> None:
        """停止调度器"""
        if self._scheduler:
            self._scheduler.shutdown()
            logger.info("[DailyMeditationScheduler] 调度器已停止")
        
        if self._simple_timer:
            self._simple_timer.cancel()
            logger.info("[DailyMeditationScheduler] 定时器已取消")
    
    def execute_now(self) -> Dict[str, Any]:
        """
        立即执行一次冥想
        
        Returns:
            Dict: 冥想结果
        """
        logger.info("[DailyMeditationScheduler] 手动触发冥想")
        return self.meditation.execute()


# ============================================================================
# 全局实例（单例模式）
# ============================================================================

_scheduler_instance: Optional[DailyMeditationScheduler] = None
_scheduler_lock = threading.Lock()


def get_daily_meditation_scheduler(workspace: Optional[Path] = None) -> DailyMeditationScheduler:
    """
    获取每日冥想调度器单例
    
    Args:
        workspace: 工作区路径（可选）
        
    Returns:
        DailyMeditationScheduler: 调度器实例
    """
    global _scheduler_instance
    
    if _scheduler_instance is None:
        with _scheduler_lock:
            if _scheduler_instance is None:
                _scheduler_instance = DailyMeditationScheduler(workspace)
    
    return _scheduler_instance
