"""
本地服务管理插件

V1.0版本
创建日期：2026-04-04

设计目标：
- 按需启动本地大模型服务（Qwen、Ollama等）
- 不在软件启动时启动，只在用户选择调用时启动
- 自动健康检查和重启
- 软件退出时自动停止服务

架构角色：
- 插件层：实现ToolPlugin接口
- 管理层：管理本地服务的生命周期
- 服务层：为AIServiceManager提供服务状态
"""

import os
import sys
import time
import logging
import threading
import subprocess
from typing import Any, Dict, Optional
from pathlib import Path

# 添加项目根目录到sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plugins.base_plugin import BasePlugin, PluginState, PluginContext
from plugins.plugin_types import ToolPlugin

logger = logging.getLogger(__name__)


class LocalServicePlugin(ToolPlugin):
    """
    本地服务管理插件
    
    核心功能：
    1. 按需启动本地大模型服务
    2. 健康检查和自动重启
    3. 服务状态监控
    4. 退出时自动停止
    
    支持的服务：
    - Qwen（F:\Qwen\start_server_v2.py）
    - Ollama（系统安装）
    - 其他本地推理框架
    """
    
    def __init__(self):
        super().__init__()
        self._service_processes: Dict[str, subprocess.Popen] = {}
        self._service_status: Dict[str, Dict[str, Any]] = {}
        self._health_check_thread: Optional[threading.Thread] = None
        self._shutdown_flag = threading.Event()
        self._lock = threading.RLock()
        
    @property
    def plugin_id(self) -> str:
        return "local-service-v1"
    
    @property
    def name(self) -> str:
        return "本地服务管理插件"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    def initialize(self, context: PluginContext) -> bool:
        """
        初始化插件
        
        Args:
            context: 插件上下文
            
        Returns:
            初始化是否成功
        """
        try:
            logger.info(f"[{self.plugin_id}] 初始化本地服务管理插件...")
            
            # 读取配置
            config = context.config or {}
            self._qwen_service_path = config.get(
                "qwen_service_path", 
                "F:\\Qwen\\start_server_v2.py"
            )
            self._qwen_endpoint = config.get(
                "qwen_endpoint",
                "http://localhost:8000"
            )
            self._auto_start_on_demand = config.get("auto_start_on_demand", True)
            self._auto_stop_on_exit = config.get("auto_stop_on_exit", True)
            self._health_check_interval = config.get("health_check_interval", 30)
            self._max_restart_attempts = config.get("max_restart_attempts", 3)
            
            # 启动健康检查线程（守护线程，不阻塞主线程）
            if self._health_check_interval > 0:
                self._health_check_thread = threading.Thread(
                    target=self._health_check_loop,
                    daemon=True,
                    name="LocalServiceHealthCheck"
                )
                self._health_check_thread.start()
            
            self._state = PluginState.LOADED
            logger.info(f"[{self.plugin_id}] 插件初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"[{self.plugin_id}] 初始化失败: {e}", exc_info=True)
            self._state = PluginState.ERROR
            return False
    
    def start_service(self, service_name: str) -> Dict[str, Any]:
        """
        启动本地服务（按需调用）
        
        Args:
            service_name: 服务名称（qwen, ollama等）
            
        Returns:
            启动结果字典：
            - success: 是否成功
            - message: 提示信息
            - endpoint: 服务端点
            - pid: 进程ID（如果成功）
        """
        with self._lock:
            logger.info(f"[{self.plugin_id}] 启动本地服务: {service_name}")
            
            # 检查服务是否已启动
            if self._is_service_running(service_name):
                logger.info(f"[{self.plugin_id}] 服务已在运行: {service_name}")
                return {
                    "success": True,
                    "message": f"{service_name}服务已在运行",
                    "endpoint": self._get_service_endpoint(service_name),
                    "pid": self._service_processes.get(service_name, {}).get("pid")
                }
            
            # 根据服务类型启动
            if service_name.lower() == "qwen":
                return self._start_qwen_service()
            elif service_name.lower() == "ollama":
                return self._start_ollama_service()
            else:
                return {
                    "success": False,
                    "message": f"不支持的服务类型: {service_name}"
                }
    
    def stop_service(self, service_name: str) -> Dict[str, Any]:
        """
        停止本地服务
        
        Args:
            service_name: 服务名称
            
        Returns:
            停止结果字典
        """
        with self._lock:
            logger.info(f"[{self.plugin_id}] 停止本地服务: {service_name}")
            
            if service_name not in self._service_processes:
                return {
                    "success": True,
                    "message": f"{service_name}服务未运行"
                }
            
            try:
                process_info = self._service_processes[service_name]
                process = process_info.get("process")
                
                if process and process.poll() is None:
                    # 进程仍在运行，发送终止信号
                    process.terminate()
                    
                    # 等待进程结束（最多5秒）
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # 强制终止
                        process.kill()
                        process.wait()
                    
                    logger.info(f"[{self.plugin_id}] 服务已停止: {service_name} (PID: {process_info.get('pid')})")
                
                # 清理记录
                del self._service_processes[service_name]
                
                return {
                    "success": True,
                    "message": f"{service_name}服务已停止"
                }
                
            except Exception as e:
                logger.error(f"[{self.plugin_id}] 停止服务失败: {e}")
                return {
                    "success": False,
                    "message": f"停止服务失败: {str(e)}"
                }
    
    def check_service_health(self, service_name: str) -> Dict[str, Any]:
        """
        检查服务健康状态
        
        Args:
            service_name: 服务名称
            
        Returns:
            健康状态字典：
            - healthy: 是否健康
            - endpoint: 服务端点
            - response_time: 响应时间（毫秒）
            - error: 错误信息（如果有）
        """
        try:
            import requests
            
            endpoint = self._get_service_endpoint(service_name)
            if not endpoint:
                return {
                    "healthy": False,
                    "error": f"未知的服务类型: {service_name}"
                }
            
            # 根据服务类型选择健康检查端点
            if service_name.lower() == "qwen":
                health_url = f"{endpoint}/health"
            elif service_name.lower() == "ollama":
                health_url = f"{endpoint}/api/tags"
            else:
                health_url = f"{endpoint}/health"
            
            start_time = time.time()
            response = requests.get(health_url, timeout=5)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                return {
                    "healthy": True,
                    "endpoint": endpoint,
                    "response_time": response_time,
                    "details": response.json() if response.text else {}
                }
            else:
                return {
                    "healthy": False,
                    "endpoint": endpoint,
                    "response_time": response_time,
                    "error": f"HTTP {response.status_code}"
                }
                
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e)
            }
    
    def _start_qwen_service(self) -> Dict[str, Any]:
        """启动Qwen服务"""
        try:
            # 检查服务脚本是否存在
            if not os.path.exists(self._qwen_service_path):
                logger.error(f"[{self.plugin_id}] Qwen服务脚本不存在: {self._qwen_service_path}")
                return {
                    "success": False,
                    "message": f"Qwen服务脚本不存在: {self._qwen_service_path}\n请确认Qwen已部署到正确位置。"
                }
            
            # 获取脚本目录
            script_dir = os.path.dirname(self._qwen_service_path)
            
            logger.info(f"[{self.plugin_id}] 启动Qwen服务: {self._qwen_service_path}")
            
            # 启动服务进程（后台运行）
            # 使用CREATE_NO_WINDOW标志避免弹出命令行窗口
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            process = subprocess.Popen(
                [sys.executable, self._qwen_service_path],
                cwd=script_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            
            # 记录进程信息
            self._service_processes["qwen"] = {
                "process": process,
                "pid": process.pid,
                "start_time": time.time(),
                "restart_count": 0
            }
            
            logger.info(f"[{self.plugin_id}] Qwen服务已启动 (PID: {process.pid})")
            
            # 等待服务就绪（最多60秒）
            logger.info(f"[{self.plugin_id}] 等待Qwen服务就绪...")
            max_wait = 60
            start_wait = time.time()
            
            while time.time() - start_wait < max_wait:
                health = self.check_service_health("qwen")
                if health.get("healthy"):
                    logger.info(f"[{self.plugin_id}] Qwen服务已就绪")
                    return {
                        "success": True,
                        "message": "Qwen服务已启动并就绪",
                        "endpoint": self._qwen_endpoint,
                        "pid": process.pid
                    }
                time.sleep(2)
            
            # 超时未就绪
            logger.warning(f"[{self.plugin_id}] Qwen服务启动超时（{max_wait}秒）")
            return {
                "success": False,
                "message": f"Qwen服务启动超时（{max_wait}秒）\n请检查日志确认模型是否加载成功。"
            }
            
        except Exception as e:
            logger.error(f"[{self.plugin_id}] 启动Qwen服务失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"启动Qwen服务失败: {str(e)}"
            }
    
    def _start_ollama_service(self) -> Dict[str, Any]:
        """启动Ollama服务"""
        try:
            logger.info(f"[{self.plugin_id}] 启动Ollama服务")
            
            # Ollama通常是系统服务，尝试启动
            if sys.platform == "win32":
                # Windows: 使用ollama serve命令
                process = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                # Linux/Mac
                process = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            
            self._service_processes["ollama"] = {
                "process": process,
                "pid": process.pid,
                "start_time": time.time(),
                "restart_count": 0
            }
            
            logger.info(f"[{self.plugin_id}] Ollama服务已启动 (PID: {process.pid})")
            
            # 等待服务就绪
            time.sleep(3)
            health = self.check_service_health("ollama")
            
            if health.get("healthy"):
                return {
                    "success": True,
                    "message": "Ollama服务已启动并就绪",
                    "endpoint": "http://localhost:11434",
                    "pid": process.pid
                }
            else:
                return {
                    "success": False,
                    "message": f"Ollama服务启动失败: {health.get('error')}"
                }
            
        except FileNotFoundError:
            return {
                "success": False,
                "message": "Ollama未安装，请先安装Ollama: https://ollama.ai"
            }
        except Exception as e:
            logger.error(f"[{self.plugin_id}] 启动Ollama服务失败: {e}")
            return {
                "success": False,
                "message": f"启动Ollama服务失败: {str(e)}"
            }
    
    def _is_service_running(self, service_name: str) -> bool:
        """检查服务是否正在运行"""
        if service_name not in self._service_processes:
            return False
        
        process_info = self._service_processes[service_name]
        process = process_info.get("process")
        
        if process and process.poll() is None:
            # 进程仍在运行
            return True
        else:
            # 进程已结束，清理记录
            del self._service_processes[service_name]
            return False
    
    def _get_service_endpoint(self, service_name: str) -> Optional[str]:
        """获取服务端点"""
        if service_name.lower() == "qwen":
            return self._qwen_endpoint
        elif service_name.lower() == "ollama":
            return "http://localhost:11434"
        else:
            return None
    
    def _health_check_loop(self):
        """健康检查循环（守护线程）"""
        logger.info(f"[{self.plugin_id}] 健康检查线程已启动")
        
        while not self._shutdown_flag.is_set():
            try:
                # 检查所有已启动的服务
                with self._lock:
                    for service_name in list(self._service_processes.keys()):
                        health = self.check_service_health(service_name)
                        
                        if not health.get("healthy"):
                            logger.warning(
                                f"[{self.plugin_id}] 服务不健康: {service_name}, "
                                f"错误: {health.get('error')}"
                            )
                            
                            # 尝试重启（如果自动重启次数未超过限制）
                            process_info = self._service_processes.get(service_name, {})
                            restart_count = process_info.get("restart_count", 0)
                            
                            if restart_count < self._max_restart_attempts:
                                logger.info(
                                    f"[{self.plugin_id}] 尝试重启服务: {service_name} "
                                    f"(第{restart_count + 1}次)"
                                )
                                self.stop_service(service_name)
                                result = self.start_service(service_name)
                                
                                if result.get("success"):
                                    self._service_processes[service_name]["restart_count"] = restart_count + 1
                                    logger.info(f"[{self.plugin_id}] 服务重启成功: {service_name}")
                                else:
                                    logger.error(
                                        f"[{self.plugin_id}] 服务重启失败: {service_name}, "
                                        f"原因: {result.get('message')}"
                                    )
                
                # 等待下次检查
                self._shutdown_flag.wait(self._health_check_interval)
                
            except Exception as e:
                logger.error(f"[{self.plugin_id}] 健康检查异常: {e}")
                self._shutdown_flag.wait(10)  # 异常后等待10秒再重试
        
        logger.info(f"[{self.plugin_id}] 健康检查线程已停止")
    
    def shutdown(self):
        """关闭插件，停止所有服务"""
        logger.info(f"[{self.plugin_id}] 关闭本地服务管理插件...")
        
        # 停止健康检查线程
        self._shutdown_flag.set()
        if self._health_check_thread and self._health_check_thread.is_alive():
            self._health_check_thread.join(timeout=5)
        
        # 停止所有服务
        if self._auto_stop_on_exit:
            for service_name in list(self._service_processes.keys()):
                logger.info(f"[{self.plugin_id}] 停止服务: {service_name}")
                self.stop_service(service_name)
        
        self._state = PluginState.UNLOADED
        logger.info(f"[{self.plugin_id}] 插件已关闭")
    
    def get_service_status(self, service_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取服务状态
        
        Args:
            service_name: 服务名称（None表示获取所有服务状态）
            
        Returns:
            服务状态字典
        """
        if service_name:
            if service_name in self._service_processes:
                process_info = self._service_processes[service_name]
                health = self.check_service_health(service_name)
                
                return {
                    "service": service_name,
                    "running": self._is_service_running(service_name),
                    "pid": process_info.get("pid"),
                    "uptime": time.time() - process_info.get("start_time", time.time()),
                    "health": health
                }
            else:
                return {
                    "service": service_name,
                    "running": False,
                    "message": "服务未启动"
                }
        else:
            # 返回所有服务状态
            status = {}
            for name in ["qwen", "ollama"]:
                status[name] = self.get_service_status(name)
            return status


# 插件注册函数
def create_plugin():
    """创建插件实例"""
    return LocalServicePlugin()
