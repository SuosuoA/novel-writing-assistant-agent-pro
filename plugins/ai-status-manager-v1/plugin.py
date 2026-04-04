"""
AI状态管理插件 V1.0

功能：
1. 管理AI连接状态（已连接/连接中/离线）
2. 提供状态查询接口
3. 发布状态变更事件
4. 本地AI服务启动/停止管理

架构设计：
- 业务逻辑全部在插件层实现
- GUI通过EventBus订阅状态事件
- 不影响软件启动速度，按需初始化
"""

import logging
import threading
import time
import sys
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# 插件基础类（简化版，避免循环导入）
class PluginState(str, Enum):
    """插件状态"""
    LOADED = "loaded"
    READY = "ready"
    ERROR = "error"


class PluginContext:
    """插件上下文"""
    def __init__(self, plugin_id: str, config: Dict[str, Any] = None):
        self.plugin_id = plugin_id
        self.config = config or {}


class BasePlugin(ABC):
    """插件基类"""
    def __init__(self):
        self._state = PluginState.LOADED
        self._context = None

    @property
    def state(self) -> PluginState:
        return self._state

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件"""
        self._context = context
        # 默认实现，子类可以重写
        self._state = PluginState.READY
        return True


class ToolPlugin(BasePlugin):
    """工具插件基类"""
    pass


class AIConnectionState(str, Enum):
    """AI连接状态"""
    DISCONNECTED = "未连接"
    CONNECTING = "连接中"
    CONNECTED = "已连接"
    ERROR = "连接错误"
    STARTING = "服务启动中"


class AIServiceType(str, Enum):
    """AI服务类型"""
    LOCAL = "本地"
    ONLINE = "线上"


class AIStatusManagerPlugin(ToolPlugin):
    """
    AI状态管理插件

    职责：
    1. 维护AI连接状态
    2. 管理本地AI服务启动/停止
    3. 发布状态变更事件
    4. 提供状态查询接口
    """

    PLUGIN_ID = "ai-status-manager-v1"
    PLUGIN_NAME = "AI状态管理插件"
    PLUGIN_VERSION = "1.0.0"

    def __init__(self):
        super().__init__()

        # 状态管理
        self._connection_state = AIConnectionState.DISCONNECTED
        self._service_type = AIServiceType.ONLINE
        self._provider = "DeepSeek"
        self._model = "deepseek-chat"
        self._endpoint = ""
        self._error_message = ""

        # 本地服务管理
        self._local_service_process = None
        self._health_check_thread = None
        self._health_check_running = False

        # 配置
        self._auto_sync_interval = 30
        self._retry_on_failure = True
        self._max_retry_count = 3

        # 状态锁
        self._state_lock = threading.RLock()

        # EventBus（延迟初始化）
        self._event_bus = None

    def initialize(self, context: PluginContext) -> bool:
        """
        初始化插件

        Args:
            context: 插件上下文

        Returns:
            初始化是否成功
        """
        try:
            # 保存配置
            config = context.config or {}
            self._auto_sync_interval = config.get("auto_sync_interval", 30)
            self._retry_on_failure = config.get("retry_on_failure", True)
            self._max_retry_count = config.get("max_retry_count", 3)

            # 获取EventBus引用并订阅配置变更事件
            try:
                from core.service_locator import get_service_locator
                locator = get_service_locator()
                from core.event_bus import EventBus
                self._event_bus = locator.get(EventBus)

                # V3.2新增：订阅配置变更事件
                if self._event_bus:
                    self._event_bus.subscribe("config.changed", self._on_config_changed)
                    logger.info("[AI状态管理] 已订阅config.changed事件")

            except Exception as e:
                logger.warning(f"[AI状态管理] 获取EventBus失败: {e}，事件发布功能不可用")

            logger.info(
                f"[AI状态管理] 插件初始化完成 - "
                f"sync_interval={self._auto_sync_interval}s, "
                f"retry={self._retry_on_failure}, "
                f"max_retry={self._max_retry_count}"
            )

            return True

        except Exception as e:
            logger.error(f"[AI状态管理] 初始化失败: {e}", exc_info=True)
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        获取AI状态

        Returns:
            状态字典，包含：
            - connection_state: 连接状态
            - service_type: 服务类型（本地/线上）
            - provider: 提供商
            - model: 模型名称
            - endpoint: 端点地址
            - error_message: 错误信息（如果有）
        """
        with self._state_lock:
            return {
                "connection_state": self._connection_state.value,
                "service_type": self._service_type.value,
                "provider": self._provider,
                "model": self._model,
                "endpoint": self._endpoint,
                "error_message": self._error_message,
                "is_connected": self._connection_state == AIConnectionState.CONNECTED,
                "is_local": self._service_type == AIServiceType.LOCAL,
            }

    def update_status(
        self,
        connection_state: Optional[AIConnectionState] = None,
        service_type: Optional[AIServiceType] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        endpoint: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        更新AI状态并发布事件

        Args:
            connection_state: 连接状态
            service_type: 服务类型
            provider: 提供商
            model: 模型名称
            endpoint: 端点地址
            error_message: 错误信息
        """
        with self._state_lock:
            # 更新状态
            if connection_state is not None:
                self._connection_state = connection_state
            if service_type is not None:
                self._service_type = service_type
            if provider is not None:
                self._provider = provider
            if model is not None:
                self._model = model
            if endpoint is not None:
                self._endpoint = endpoint
            if error_message is not None:
                self._error_message = error_message

            logger.info(
                f"[AI状态管理] 状态更新: "
                f"connection={self._connection_state.value}, "
                f"type={self._service_type.value}, "
                f"provider={self._provider}"
            )

        # 发布状态变更事件
        self._publish_status_changed()

    def test_connection(self, endpoint: str, provider: str, timeout: int = 10) -> Dict[str, Any]:
        """
        测试AI连接

        Args:
            endpoint: 端点地址
            provider: 提供商
            timeout: 超时时间（秒）

        Returns:
            测试结果字典：
            - success: 是否成功
            - message: 结果消息
            - details: 详细信息
        """
        try:
            # 更新状态为"连接中"
            self.update_status(
                connection_state=AIConnectionState.CONNECTING,
                endpoint=endpoint,
                provider=provider,
            )

            import requests

            if provider.lower() == "qwen":
                # Qwen健康检查（V3.2.1修复：健康检查在根路径，不在/v1下）
                # endpoint可能是 http://localhost:8000/v1，需要提取根路径
                base_url = endpoint.replace("/v1", "").rstrip("/")
                response = requests.get(f"{base_url}/health", timeout=timeout)
                if response.status_code == 200:
                    data = response.json()
                    self.update_status(
                        connection_state=AIConnectionState.CONNECTED,
                        error_message="",
                    )
                    return {
                        "success": True,
                        "message": "Qwen服务连接成功",
                        "details": {
                            "model_loaded": data.get("model_loaded", False),
                            "model": data.get("model", "Qwen2.5-14B"),
                        }
                    }
                else:
                    raise Exception(f"服务返回状态码: {response.status_code}")

            elif provider.lower() == "ollama":
                # Ollama健康检查
                response = requests.get(f"{endpoint}/api/tags", timeout=timeout)
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    self.update_status(connection_state=AIConnectionState.CONNECTED)
                    return {
                        "success": True,
                        "message": "Ollama服务连接成功",
                        "details": {
                            "models": [m.get("name") for m in models],
                        }
                    }
                else:
                    raise Exception(f"服务返回状态码: {response.status_code}")

            else:
                # 其他服务：使用通用健康检查
                response = requests.get(f"{endpoint}/v1/models", timeout=timeout)
                if response.status_code in [200, 401]:  # 401也表示服务可达
                    self.update_status(connection_state=AIConnectionState.CONNECTED)
                    return {
                        "success": True,
                        "message": f"{provider}服务连接成功",
                        "details": {},
                    }
                else:
                    raise Exception(f"服务返回状态码: {response.status_code}")

        except requests.exceptions.ConnectionError as e:
            error_msg = f"无法连接到{provider}服务: {endpoint}"
            self.update_status(
                connection_state=AIConnectionState.ERROR,
                error_message=error_msg,
            )
            return {
                "success": False,
                "message": error_msg,
                "details": {"error": str(e)},
            }

        except Exception as e:
            error_msg = f"连接测试失败: {str(e)}"
            self.update_status(
                connection_state=AIConnectionState.ERROR,
                error_message=error_msg,
            )
            return {
                "success": False,
                "message": error_msg,
                "details": {"error": str(e)},
            }

    def start_local_service(self, service_name: str) -> Dict[str, Any]:
        """
        启动本地AI服务

        Args:
            service_name: 服务名称（qwen, ollama等）

        Returns:
            启动结果字典：
            - success: 是否成功
            - message: 结果消息
            - pid: 进程ID（如果成功）
        """
        try:
            # 更新状态为"服务启动中"
            self.update_status(
                connection_state=AIConnectionState.STARTING,
                service_type=AIServiceType.LOCAL,
            )

            if service_name.lower() == "qwen":
                # 启动Qwen服务
                import subprocess
                import os

                qwen_path = Path("F:/Qwen/start_server_v2.py")
                if not qwen_path.exists():
                    raise Exception(f"Qwen服务脚本不存在: {qwen_path}")

                # 后台启动服务
                self._local_service_process = subprocess.Popen(
                    [sys.executable, str(qwen_path)],
                    cwd=str(qwen_path.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )

                # 等待服务启动
                logger.info(f"[AI状态管理] Qwen服务启动中，PID: {self._local_service_process.pid}")

                # 启动健康检查线程
                self._start_health_check("qwen", "http://localhost:8000")

                return {
                    "success": True,
                    "message": "Qwen服务启动中，请稍候...",
                    "pid": self._local_service_process.pid,
                    "endpoint": "http://localhost:8000",
                }

            elif service_name.lower() == "ollama":
                # 启动Ollama服务
                import subprocess

                self._local_service_process = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                logger.info(f"[AI状态管理] Ollama服务启动中，PID: {self._local_service_process.pid}")

                # 启动健康检查线程
                self._start_health_check("ollama", "http://localhost:11434")

                return {
                    "success": True,
                    "message": "Ollama服务启动中，请稍候...",
                    "pid": self._local_service_process.pid,
                    "endpoint": "http://localhost:11434",
                }

            else:
                raise Exception(f"不支持的服务类型: {service_name}")

        except Exception as e:
            error_msg = f"启动本地服务失败: {str(e)}"
            logger.error(f"[AI状态管理] {error_msg}", exc_info=True)
            self.update_status(
                connection_state=AIConnectionState.ERROR,
                error_message=error_msg,
            )
            return {
                "success": False,
                "message": error_msg,
            }

    def stop_local_service(self) -> Dict[str, Any]:
        """
        停止本地AI服务

        Returns:
            停止结果字典
        """
        try:
            # 停止健康检查线程
            self._stop_health_check()

            # 停止服务进程
            if self._local_service_process:
                self._local_service_process.terminate()
                self._local_service_process.wait(timeout=5)
                self._local_service_process = None

            self.update_status(connection_state=AIConnectionState.DISCONNECTED)

            return {
                "success": True,
                "message": "本地服务已停止",
            }

        except Exception as e:
            error_msg = f"停止本地服务失败: {str(e)}"
            logger.error(f"[AI状态管理] {error_msg}", exc_info=True)
            return {
                "success": False,
                "message": error_msg,
            }

    def _start_health_check(self, service_name: str, endpoint: str):
        """启动健康检查线程"""
        self._health_check_running = True
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            args=(service_name, endpoint),
            daemon=True,
        )
        self._health_check_thread.start()

    def _stop_health_check(self):
        """停止健康检查线程"""
        self._health_check_running = False
        if self._health_check_thread:
            self._health_check_thread.join(timeout=2)
            self._health_check_thread = None

    def _health_check_loop(self, service_name: str, endpoint: str):
        """
        健康检查循环

        等待服务就绪，然后定期检查健康状态
        """
        import requests

        # 初始等待（最多60秒）
        max_wait = 60
        start_time = time.time()

        while self._health_check_running and (time.time() - start_time) < max_wait:
            try:
                if service_name.lower() == "qwen":
                    response = requests.get(f"{endpoint}/health", timeout=2)
                else:
                    response = requests.get(f"{endpoint}/api/tags", timeout=2)

                if response.status_code == 200:
                    # 服务就绪
                    self.update_status(
                        connection_state=AIConnectionState.CONNECTED,
                        endpoint=endpoint,
                    )
                    logger.info(f"[AI状态管理] {service_name}服务已就绪")
                    break

            except Exception:
                pass  # 继续等待

            time.sleep(2)

        # 定期健康检查（每30秒）
        while self._health_check_running:
            try:
                if service_name.lower() == "qwen":
                    response = requests.get(f"{endpoint}/health", timeout=5)
                else:
                    response = requests.get(f"{endpoint}/api/tags", timeout=5)

                if response.status_code == 200:
                    if self._connection_state != AIConnectionState.CONNECTED:
                        self.update_status(connection_state=AIConnectionState.CONNECTED)
                else:
                    if self._connection_state == AIConnectionState.CONNECTED:
                        self.update_status(
                            connection_state=AIConnectionState.ERROR,
                            error_message=f"服务异常：HTTP {response.status_code}",
                        )

            except Exception as e:
                if self._connection_state == AIConnectionState.CONNECTED:
                    self.update_status(
                        connection_state=AIConnectionState.ERROR,
                        error_message=f"健康检查失败: {str(e)}",
                    )

            time.sleep(self._auto_sync_interval)

    def _publish_status_changed(self):
        """发布状态变更事件"""
        if self._event_bus:
            try:
                self._event_bus.publish(
                    "ai.status.changed",
                    self.get_status(),
                )
            except Exception as e:
                logger.warning(f"[AI状态管理] 发布状态事件失败: {e}")

    def _on_config_changed(self, event):
        """配置变更事件处理（V3.2新增）

        订阅config.changed事件，自动响应AI配置变更：
        1. 更新AI状态
        2. 测试连接
        3. 发布状态变更事件

        Args:
            event: EventBus的Event对象，包含event.data（配置字典）
        """
        try:
            # 从Event对象中提取配置数据
            from core.event_bus import Event as EventType

            if isinstance(event, EventType):
                config = event.data if event.data else {}
            elif isinstance(event, dict):
                config = event
            else:
                logger.warning(f"[AI状态管理] 配置事件格式错误: {type(event)}")
                return

            # 只处理AI配置变更
            if config.get("type") != "ai_config":
                return

            ai_config = config.get("data", {})
            if not ai_config:
                return

            logger.info(f"[AI状态管理] 收到配置变更事件: {ai_config.get('provider')}, mode={ai_config.get('service_mode')}")

            # 提取配置参数
            service_mode = ai_config.get("service_mode", "online")
            provider = ai_config.get("provider", "DeepSeek")
            model = ai_config.get("model", "")
            endpoint = ai_config.get("local_url", "")
            api_key = ai_config.get("api_key", "")

            # 更新状态
            with self._state_lock:
                self._provider = provider
                self._model = model
                self._endpoint = endpoint

            # 更新连接状态
            if service_mode == "local":
                # 本地服务：更新状态为"连接中"，然后异步测试连接
                self.update_status(
                    connection_state=AIConnectionState.CONNECTING,
                    service_type=AIServiceType.LOCAL,
                    provider=provider,
                    model=model,
                    endpoint=endpoint
                )

                # 异步测试连接，失败时自动启动服务
                def test_connection_async():
                    import time
                    time.sleep(1)  # 等待配置生效

                    result = self.test_connection(endpoint, provider)
                    if result["success"]:
                        logger.info(f"[AI状态管理] 配置变更后连接测试成功: {provider}")
                    else:
                        logger.warning(f"[AI状态管理] 配置变更后连接测试失败: {result.get('message')}")
                        
                        # V3.2.3新增：连接失败时自动启动服务（仅支持Qwen）
                        if provider.lower() == "qwen":
                            logger.info("[AI状态管理] 尝试自动启动Qwen服务...")
                            start_result = self.start_local_service("qwen")
                            if start_result["success"]:
                                logger.info(f"[AI状态管理] Qwen服务自动启动成功，PID: {start_result.get('pid')}")
                            else:
                                logger.error(f"[AI状态管理] Qwen服务自动启动失败: {start_result.get('message')}")

                threading.Thread(target=test_connection_async, daemon=True).start()

            else:
                # 线上服务：直接标记为"已连接"
                self.update_status(
                    connection_state=AIConnectionState.CONNECTED,
                    service_type=AIServiceType.ONLINE,
                    provider=provider,
                    model=model,
                    endpoint=f"https://api.{provider.lower()}.com"
                )
                logger.info(f"[AI状态管理] 线上服务配置已更新: {provider}")

        except Exception as e:
            logger.error(f"[AI状态管理] 处理配置变更失败: {e}", exc_info=True)

    def shutdown(self):
        """插件关闭"""
        self._stop_health_check()

        if self._local_service_process:
            self.stop_local_service()

        logger.info("[AI状态管理] 插件已关闭")


# 插件导出
__all__ = ["AIStatusManagerPlugin"]
