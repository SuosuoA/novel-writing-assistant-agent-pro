"""
WebDashboard可视化 - Flask + Plotly Dash实现

V1.0版本
创建日期：2026-03-29

功能：
- 实时指标可视化
- 四层记忆状态监控
- 知识库统计分析
- 生成质量趋势图
- API使用统计
- 用户反馈分析

设计参考：
- OpenClaw Claw化系统
- 12.9claw化全面说明.md

使用示例：
    # 启动Web服务器
    python tools/web_dashboard.py
    
    # 访问 http://localhost:8050
"""

import logging
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Flask and Dash imports
try:
    from flask import Flask, jsonify, request
    from dash import Dash, dcc, html, Input, Output, callback
    import plotly.graph_objs as go
    import plotly.express as px
    import pandas as pd
    import numpy as np
    WEB_DEPS_AVAILABLE = True
except ImportError:
    WEB_DEPS_AVAILABLE = False
    logging.warning("[WebDashboard] Flask/Dash未安装，Web可视化功能不可用")

# Core imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.session_state import get_session_state_manager
from core.wal_manager import get_wal_manager
from core.git_notes_manager import get_git_notes_manager
from core.metrics_monitor import get_metrics_monitor
from core.user_feedback_loop import get_user_feedback_loop

logger = logging.getLogger(__name__)


# ============================================================================
# WebDashboard Flask API服务器
# ============================================================================

class WebDashboard:
    """
    WebDashboard可视化服务器
    
    提供：
    1. RESTful API接口
    2. 实时数据推送
    3. 历史数据查询
    4. 指标计算与缓存
    """
    
    def __init__(self, workspace: Optional[Path] = None, port: int = 8050):
        """
        初始化WebDashboard
        
        Args:
            workspace: 工作区路径
            port: 服务端口
        """
        if not WEB_DEPS_AVAILABLE:
            raise ImportError("Flask/Dash未安装，请运行: pip install flask dash plotly pandas numpy")
        
        self.workspace = workspace or Path.cwd()
        self.port = port
        
        # 初始化核心组件
        self.session_manager = get_session_state_manager(self.workspace)
        self.wal_manager = get_wal_manager(self.workspace)
        self.git_notes_manager = get_git_notes_manager(self.workspace)
        self.metrics_monitor = get_metrics_monitor(self.workspace)
        self.feedback_loop = get_user_feedback_loop(self.workspace)
        
        # 创建Flask应用
        self.app = Flask(__name__)
        self.dash_app = None
        
        # 数据缓存
        self._cache = {}
        self._cache_time = {}
        self._cache_ttl = 60  # 60秒缓存
        
        # 注册API路由
        self._register_routes()
        
        logger.info(f"[WebDashboard] 初始化完成，端口: {port}")
    
    def _register_routes(self):
        """注册Flask API路由"""
        
        @self.app.route('/api/overview', methods=['GET'])
        def get_overview():
            """获取总览数据"""
            return jsonify(self._get_overview_data())
        
        @self.app.route('/api/memory-status', methods=['GET'])
        def get_memory_status():
            """获取四层记忆状态"""
            return jsonify(self._get_memory_status())
        
        @self.app.route('/api/knowledge-stats', methods=['GET'])
        def get_knowledge_stats():
            """获取知识库统计"""
            return jsonify(self._get_knowledge_stats())
        
        @self.app.route('/api/generation-trend', methods=['GET'])
        def get_generation_trend():
            """获取生成质量趋势"""
            days = request.args.get('days', 7, type=int)
            return jsonify(self._get_generation_trend(days))
        
        @self.app.route('/api/api-usage', methods=['GET'])
        def get_api_usage():
            """获取API使用统计"""
            return jsonify(self._get_api_usage())
        
        @self.app.route('/api/feedback-analysis', methods=['GET'])
        def get_feedback_analysis():
            """获取用户反馈分析"""
            return jsonify(self._get_feedback_analysis())
        
        @self.app.route('/api/metrics', methods=['GET'])
        def get_metrics():
            """获取核心指标"""
            period = request.args.get('period', 30, type=int)
            return jsonify(self._get_core_metrics(period))
        
        @self.app.route('/api/daily-meditation-logs', methods=['GET'])
        def get_meditation_logs():
            """获取每日冥想日志"""
            limit = request.args.get('limit', 7, type=int)
            return jsonify(self._get_meditation_logs(limit))
        
        @self.app.route('/', methods=['GET'])
        def index():
            """重定向到Dash应用"""
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Novel Writing Assistant Dashboard</title>
                <meta http-equiv="refresh" content="0; url=/dash/">
            </head>
            <body>
                <h1>Novel Writing Assistant Dashboard</h1>
                <p>正在跳转到可视化界面...</p>
                <p><a href="/dash/">点击这里进入Dashboard</a></p>
            </body>
            </html>
            '''
    
    def _get_cached_data(self, key: str, fetch_func, ttl: int = None):
        """获取缓存数据"""
        ttl = ttl or self._cache_ttl
        
        if key in self._cache:
            if (datetime.now() - self._cache_time[key]).total_seconds() < ttl:
                return self._cache[key]
        
        data = fetch_func()
        self._cache[key] = data
        self._cache_time[key] = datetime.now()
        return data
    
    def _get_overview_data(self) -> Dict[str, Any]:
        """获取总览数据"""
        try:
            state = self.session_manager.get_state()
            wal_stats = self.wal_manager.get_wal_stats()
            
            return {
                "current_chapter": state.temp_context.current_chapter,
                "word_count": state.temp_context.word_count,
                "characters_involved": len(state.temp_context.characters_involved),
                "total_operations": wal_stats.get("total_writes", 0),
                "success_rate": wal_stats.get("success_rate", 0),
                "latest_score": state.pending_data.latest_score,
                "last_operation": state.active_task.last_operation,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[WebDashboard] 获取总览数据失败: {e}")
            return {"error": str(e)}
    
    def _get_memory_status(self) -> Dict[str, Any]:
        """获取四层记忆状态"""
        try:
            # L1热记忆
            state = self.session_manager.get_state()
            l1_stats = {
                "status": "active",
                "word_count": state.temp_context.word_count,
                "current_chapter": state.temp_context.current_chapter,
                "last_update": datetime.now().isoformat()
            }
            
            # L2温记忆（向量库）
            try:
                from infrastructure.vector_store import get_vector_store
                vector_store = get_vector_store(self.workspace)
                l2_stats = {
                    "status": "active",
                    "chapters": vector_store.count_vectors(table="chapters") if hasattr(vector_store, 'count_vectors') else 0,
                    "knowledge": vector_store.count_vectors(table="knowledge") if hasattr(vector_store, 'count_vectors') else 0,
                    "styles": vector_store.count_vectors(table="styles") if hasattr(vector_store, 'count_vectors') else 0
                }
            except:
                l2_stats = {"status": "unavailable", "message": "Vector store not initialized"}
            
            # L3冷记忆（Git-Notes）
            try:
                branch_memories = self.git_notes_manager.get_branch_memories()
                l3_stats = {
                    "status": "active",
                    "current_branch": branch_memories.branch_name,
                    "decisions": len(branch_memories.decisions),
                    "milestones": len(branch_memories.milestones),
                    "lessons": len(branch_memories.lessons)
                }
            except:
                l3_stats = {"status": "unavailable", "message": "Git-Notes not initialized"}
            
            # L4档案（MEMORY.md）- Claw化运行记忆
            memory_file = self.workspace / "Memory-Novel Writing Assistant-Agent Pro" / "MEMORY.md"
            l4_stats = {
                "status": "active" if memory_file.exists() else "empty",
                "file_path": str(memory_file),
                "size_kb": memory_file.stat().st_size / 1024 if memory_file.exists() else 0,
                "last_modified": datetime.fromtimestamp(memory_file.stat().st_mtime).isoformat() if memory_file.exists() else None
            }
            
            return {
                "L1_hot": l1_stats,
                "L2_warm": l2_stats,
                "L3_cold": l3_stats,
                "L4_archive": l4_stats,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[WebDashboard] 获取记忆状态失败: {e}")
            return {"error": str(e)}
    
    def _get_knowledge_stats(self) -> Dict[str, Any]:
        """获取知识库统计"""
        try:
            knowledge_dir = self.workspace / "data" / "knowledge"
            
            stats = {
                "total_categories": 0,
                "total_items": 0,
                "categories": {}
            }
            
            if knowledge_dir.exists():
                for category_file in knowledge_dir.glob("*.json"):
                    try:
                        with open(category_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            count = len(data) if isinstance(data, list) else 1
                            stats["categories"][category_file.stem] = count
                            stats["total_items"] += count
                    except:
                        pass
                stats["total_categories"] = len(stats["categories"])
            
            return stats
        except Exception as e:
            logger.error(f"[WebDashboard] 获取知识库统计失败: {e}")
            return {"error": str(e)}
    
    def _get_generation_trend(self, days: int = 7) -> Dict[str, Any]:
        """获取生成质量趋势"""
        try:
            meditation_dir = self.workspace / ".workbuddy" / "meditations"
            
            trends = []
            for i in range(days):
                date = datetime.now() - timedelta(days=i)
                log_file = meditation_dir / f"meditation_{date.strftime('%Y%m%d')}.json"
                
                if log_file.exists():
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                        trends.append({
                            "date": date.strftime('%Y-%m-%d'),
                            "word_count": log_data.get("steps", {}).get("data_collection", {}).get("word_count", 0),
                            "operations": log_data.get("steps", {}).get("data_collection", {}).get("operations", 0),
                            "overall_score": log_data.get("steps", {}).get("metrics_calculation", {}).get("overall_score", 0),
                            "pass_rate": log_data.get("steps", {}).get("metrics_calculation", {}).get("pass_rate", 0)
                        })
            
            return {
                "trends": list(reversed(trends)),
                "period_days": days,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[WebDashboard] 获取生成趋势失败: {e}")
            return {"error": str(e)}
    
    def _get_api_usage(self) -> Dict[str, Any]:
        """获取API使用统计"""
        try:
            # 从SessionState获取API调用统计
            state = self.session_manager.get_state()
            wal_stats = self.wal_manager.get_wal_stats()
            
            return {
                "total_calls": wal_stats.get("total_writes", 0),
                "success_rate": wal_stats.get("success_rate", 0),
                "failed_calls": wal_stats.get("failed_writes", 0),
                "last_call": state.active_task.last_operation,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[WebDashboard] 获取API使用统计失败: {e}")
            return {"error": str(e)}
    
    def _get_feedback_analysis(self) -> Dict[str, Any]:
        """获取用户反馈分析"""
        try:
            # 从用户反馈闭环获取数据
            feedbacks = self.feedback_loop.get_recent_feedback(hours=24*7)
            
            positive_count = sum(1 for f in feedbacks if f.get("type") == "positive")
            negative_count = sum(1 for f in feedbacks if f.get("type") == "negative")
            suggestion_count = sum(1 for f in feedbacks if f.get("type") == "suggestion")
            
            return {
                "total_feedbacks": len(feedbacks),
                "positive": positive_count,
                "negative": negative_count,
                "suggestion": suggestion_count,
                "sentiment_score": (positive_count - negative_count) / len(feedbacks) if feedbacks else 0,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[WebDashboard] 获取反馈分析失败: {e}")
            return {"error": str(e)}
    
    def _get_core_metrics(self, period_days: int = 30) -> Dict[str, Any]:
        """获取核心指标"""
        try:
            report = self.metrics_monitor.calculate_all_metrics(period_days=period_days)
            
            return {
                "overall_score": report.overall_score,
                "pass_rate": report.pass_rate,
                "metrics": {
                    "word_count": report.word_count_score,
                    "consistency": report.consistency_score,
                    "api_success": report.api_success_rate,
                    "user_satisfaction": report.user_satisfaction_score,
                    "knowledge_usage": report.knowledge_usage_score,
                    "generation_quality": report.generation_quality_score
                },
                "period_start": report.period_start,
                "period_end": report.period_end,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[WebDashboard] 获取核心指标失败: {e}")
            return {"error": str(e)}
    
    def _get_meditation_logs(self, limit: int = 7) -> Dict[str, Any]:
        """获取每日冥想日志"""
        try:
            meditation_dir = self.workspace / ".workbuddy" / "meditations"
            
            logs = []
            for log_file in sorted(meditation_dir.glob("meditation_*.json"), reverse=True)[:limit]:
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                        logs.append(log_data)
                except:
                    pass
            
            return {
                "logs": logs,
                "count": len(logs),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[WebDashboard] 获取冥想日志失败: {e}")
            return {"error": str(e)}
    
    def create_dash_app(self):
        """创建Dash应用"""
        if not WEB_DEPS_AVAILABLE:
            return None
        
        # 创建Dash应用
        self.dash_app = Dash(
            __name__,
            server=self.app,
            url_base_pathname='/dash/'
        )
        
        # 定义布局
        self.dash_app.layout = html.Div([
            html.H1('Novel Writing Assistant Dashboard', style={'textAlign': 'center', 'color': '#2c3e50'}),
            html.P('Claw化系统实时监控', style={'textAlign': 'center', 'color': '#7f8c8d'}),
            html.Hr(),
            
            # 自动刷新
            dcc.Interval(id='interval-component', interval=10*1000, n_intervals=0),
            
            # 总览卡片
            html.Div([
                html.H2('📊 总览', style={'color': '#34495e'}),
                html.Div(id='overview-cards', style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '20px'}),
            ], style={'marginBottom': '30px'}),
            
            # 四层记忆状态
            html.Div([
                html.H2('🧠 四层记忆状态', style={'color': '#34495e'}),
                html.Div(id='memory-status'),
            ], style={'marginBottom': '30px'}),
            
            # 核心指标
            html.Div([
                html.H2('📈 核心指标', style={'color': '#34495e'}),
                dcc.Graph(id='metrics-chart'),
            ], style={'marginBottom': '30px'}),
            
            # 生成质量趋势
            html.Div([
                html.H2('📉 生成质量趋势', style={'color': '#34495e'}),
                dcc.Graph(id='trend-chart'),
            ], style={'marginBottom': '30px'}),
            
            # API使用统计
            html.Div([
                html.H2('🔌 API使用统计', style={'color': '#34495e'}),
                html.Div(id='api-usage-stats'),
            ], style={'marginBottom': '30px'}),
            
            # 用户反馈分析
            html.Div([
                html.H2('💬 用户反馈分析', style={'color': '#34495e'}),
                dcc.Graph(id='feedback-chart'),
            ], style={'marginBottom': '30px'}),
        ], style={'padding': '20px', 'fontFamily': 'Arial, sans-serif'})
        
        # 注册回调
        self._register_dash_callbacks()
        
        return self.dash_app
    
    def _register_dash_callbacks(self):
        """注册Dash回调函数"""
        
        @self.dash_app.callback(
            [Output('overview-cards', 'children'),
             Output('memory-status', 'children'),
             Output('metrics-chart', 'figure'),
             Output('trend-chart', 'figure'),
             Output('api-usage-stats', 'children'),
             Output('feedback-chart', 'figure')],
            [Input('interval-component', 'n_intervals')]
        )
        def update_dashboard(n):
            """更新Dashboard数据"""
            # 获取总览数据
            overview = self._get_overview_data()
            overview_cards = html.Div([
                html.Div([
                    html.H3('当前章节', style={'color': '#7f8c8d'}),
                    html.P(overview.get('current_chapter', 'N/A'), style={'fontSize': '24px', 'fontWeight': 'bold'})
                ], style={'flex': '1', 'padding': '20px', 'backgroundColor': '#ecf0f1', 'borderRadius': '10px'}),
                html.Div([
                    html.H3('字数', style={'color': '#7f8c8d'}),
                    html.P(f"{overview.get('word_count', 0):,}", style={'fontSize': '24px', 'fontWeight': 'bold'})
                ], style={'flex': '1', 'padding': '20px', 'backgroundColor': '#ecf0f1', 'borderRadius': '10px'}),
                html.Div([
                    html.H3('成功率', style={'color': '#7f8c8d'}),
                    html.P(f"{overview.get('success_rate', 0):.1f}%", style={'fontSize': '24px', 'fontWeight': 'bold'})
                ], style={'flex': '1', 'padding': '20px', 'backgroundColor': '#ecf0f1', 'borderRadius': '10px'}),
                html.Div([
                    html.H3('最新评分', style={'color': '#7f8c8d'}),
                    html.P(f"{overview.get('latest_score', 0):.2f}", style={'fontSize': '24px', 'fontWeight': 'bold'})
                ], style={'flex': '1', 'padding': '20px', 'backgroundColor': '#ecf0f1', 'borderRadius': '10px'}),
            ])
            
            # 获取记忆状态
            memory_status = self._get_memory_status()
            memory_div = html.Div([
                html.Div([
                    html.H4('L1 热记忆', style={'color': '#e74c3c'}),
                    html.P(f"状态: {memory_status.get('L1_hot', {}).get('status', 'unknown')}"),
                    html.P(f"字数: {memory_status.get('L1_hot', {}).get('word_count', 0)}"),
                ], style={'flex': '1', 'padding': '15px', 'backgroundColor': '#ffebee', 'borderRadius': '8px'}),
                html.Div([
                    html.H4('L2 温记忆', style={'color': '#f39c12'}),
                    html.P(f"状态: {memory_status.get('L2_warm', {}).get('status', 'unknown')}"),
                    html.P(f"向量数: {memory_status.get('L2_warm', {}).get('chapters', 0) + memory_status.get('L2_warm', {}).get('knowledge', 0)}"),
                ], style={'flex': '1', 'padding': '15px', 'backgroundColor': '#fff3e0', 'borderRadius': '8px'}),
                html.Div([
                    html.H4('L3 冷记忆', style={'color': '#3498db'}),
                    html.P(f"状态: {memory_status.get('L3_cold', {}).get('status', 'unknown')}"),
                    html.P(f"决策: {memory_status.get('L3_cold', {}).get('decisions', 0)}条"),
                ], style={'flex': '1', 'padding': '15px', 'backgroundColor': '#e3f2fd', 'borderRadius': '8px'}),
                html.Div([
                    html.H4('L4 档案', style={'color': '#9b59b6'}),
                    html.P(f"状态: {memory_status.get('L4_archive', {}).get('status', 'unknown')}"),
                    html.P(f"大小: {memory_status.get('L4_archive', {}).get('size_kb', 0):.1f}KB"),
                ], style={'flex': '1', 'padding': '15px', 'backgroundColor': '#f3e5f5', 'borderRadius': '8px'}),
            ], style={'display': 'flex', 'gap': '15px'})
            
            # 核心指标图表
            metrics = self._get_core_metrics(30)
            metrics_fig = go.Figure(data=[
                go.Bar(
                    x=list(metrics.get('metrics', {}).keys()),
                    y=list(metrics.get('metrics', {}).values()),
                    marker_color=['#3498db', '#e74c3c', '#f39c12', '#2ecc71', '#9b59b6', '#1abc9c']
                )
            ])
            metrics_fig.update_layout(
                title='核心指标得分',
                yaxis=dict(range=[0, 1]),
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
            
            # 生成趋势图表
            trend = self._get_generation_trend(7)
            trend_fig = go.Figure()
            
            if trend.get('trends'):
                dates = [t['date'] for t in trend['trends']]
                scores = [t['overall_score'] for t in trend['trends']]
                
                trend_fig.add_trace(go.Scatter(
                    x=dates,
                    y=scores,
                    mode='lines+markers',
                    name='整体评分',
                    line=dict(color='#3498db', width=3),
                    marker=dict(size=10)
                ))
                
                trend_fig.update_layout(
                    title='生成质量趋势（近7天）',
                    xaxis_title='日期',
                    yaxis_title='评分',
                    yaxis=dict(range=[0, 1]),
                    plot_bgcolor='white',
                    paper_bgcolor='white'
                )
            else:
                trend_fig.update_layout(title='暂无数据')
            
            # API使用统计
            api_usage = self._get_api_usage()
            api_div = html.Div([
                html.Div([
                    html.P(f"总调用: {api_usage.get('total_calls', 0)}", style={'fontSize': '18px'}),
                    html.P(f"成功率: {api_usage.get('success_rate', 0):.1f}%", style={'fontSize': '18px'}),
                    html.P(f"失败次数: {api_usage.get('failed_calls', 0)}", style={'fontSize': '18px'}),
                ])
            ])
            
            # 用户反馈图表
            feedback = self._get_feedback_analysis()
            feedback_fig = go.Figure(data=[
                go.Pie(
                    labels=['正面', '负面', '建议'],
                    values=[feedback.get('positive', 0), feedback.get('negative', 0), feedback.get('suggestion', 0)],
                    marker_colors=['#2ecc71', '#e74c3c', '#f39c12']
                )
            ])
            feedback_fig.update_layout(title='用户反馈分布')
            
            return overview_cards, memory_div, metrics_fig, trend_fig, api_div, feedback_fig
    
    def run(self, debug: bool = False):
        """启动Web服务器"""
        if not WEB_DEPS_AVAILABLE:
            logger.error("[WebDashboard] Flask/Dash未安装，无法启动Web服务器")
            return False
        
        try:
            # 创建Dash应用
            self.create_dash_app()
            
            # 启动Flask服务器
            logger.info(f"[WebDashboard] 启动Web服务器: http://localhost:{self.port}")
            logger.info(f"[WebDashboard] Dashboard界面: http://localhost:{self.port}/dash/")
            
            self.app.run(host='0.0.0.0', port=self.port, debug=debug)
            return True
            
        except Exception as e:
            logger.error(f"[WebDashboard] 启动失败: {e}")
            return False


# ============================================================================
# 全局实例
# ============================================================================

_dashboard_instance: Optional[WebDashboard] = None
_dashboard_lock = threading.Lock()


def get_web_dashboard(workspace: Optional[Path] = None, port: int = 8050) -> WebDashboard:
    """
    获取WebDashboard单例
    
    Args:
        workspace: 工作区路径
        port: 服务端口
        
    Returns:
        WebDashboard: Dashboard实例
    """
    global _dashboard_instance
    
    if _dashboard_instance is None:
        with _dashboard_lock:
            if _dashboard_instance is None:
                _dashboard_instance = WebDashboard(workspace, port)
    
    return _dashboard_instance


# ============================================================================
# 主入口
# ============================================================================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 启动Dashboard
    dashboard = get_web_dashboard()
    dashboard.run(debug=True)