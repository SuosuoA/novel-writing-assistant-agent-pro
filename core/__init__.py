"""
Core模块入口

V1.2版本（最终修订版）
创建日期：2026-03-21

导出所有核心类和函数
"""

# 核心类
from .event_bus import EventBus, EventPriority, DeadLetterQueue, get_event_bus

from .plugin_registry import (
    PluginRegistry,
    PluginState,
    PluginType,
    get_plugin_registry,
)

from .service_locator import (
    ServiceLocator,
    ServiceScope,
    ServiceScopeManager,
    CircularDependencyError,
    ServiceNotFoundError,
    get_service_locator,
)

from .config_manager import (
    ConfigManager,
    ConfigValidationError,
    ConfigKeyError,
    get_config_manager,
)

from .plugin_loader import (
    PluginLoader,
    PluginLoadResult,
    DependencyResolver,
    HotSwapPermission,
    PluginSignatureVerifier,
    get_plugin_loader,
)

from .hot_swap_manager import (
    HotSwapManager,
    HotSwapAction,
    HotSwapState,
    HotSwapEvent,
    PluginStateInfo,
    get_hot_swap_manager,
)

from .plugin_interface import (
    BasePlugin,
    AnalyzerPlugin,
    GeneratorPlugin,
    ValidatorPlugin,
    StoragePlugin,
    AIPlugin,
    ToolPlugin,
    ProtocolPlugin,
)

from .models import (
    Event,
    HandlerInfo,
    PluginMetadata,
    PluginInfo,
    ValidationScores,
    GenerationRequest,
    GenerationResult,
    PluginEvent,
)

# V1.2新增模块
from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerManager,
    get_circuit_breaker_manager,
)

from .secure_config import SecureConfig, SecureConfigError, get_secure_config

from .log_sanitizer import LogSanitizer, SanitizingFormatter, get_log_sanitizer

from .plugin_signer import PluginSigner, PluginSignatureError, get_plugin_signer

# UI层API
from .ui_api import (
    CoreServiceManager,
    GenerationServiceProxy,
    PluginServiceProxy,
    ConfigServiceProxy,
    EventServiceProxy,
)

# Database（V1.0新增）
from .database import (
    ConnectionPool,
    DatabaseMigration,
    AgentStateStore,
    GenerationHistoryStore,
    get_database,
    get_agent_state_store,
    get_generation_history_store,
    close_database,
)

# AsyncHandler（V1.0新增）
from .async_handler import (
    AsyncHandler,
    Task,
    TaskPriority,
    TaskState,
    PriorityTaskQueue,
    get_async_handler,
    init_async_handler,
)

# Launcher（V1.0新增）
from .launcher import (
    LazyLoader,
    LoadPriority,
    ModuleInfo,
    get_lazy_loader,
)

from .app_launcher import (
    OptimizedLauncher,
    StartupConfig,
    get_optimized_launcher,
)

# ConfigService（V1.3新增，V1.2监听器模式增强）
from .config_service import ConfigService, AppConfig, get_config_service

# LoggingService（V1.3新增）
from .logging_service import LoggingService, get_logging_service

# BootstrapService（V1.3新增）
from .bootstrap import (
    BootstrapService,
    get_bootstrap_service,
    initialize_core_services,
    dispose_core_services,
)

# CacheManager（V1.4新增）
from .cache_manager import (
    CacheManager,
    CacheConfig,
    CacheEntry,
    CacheStats,
    SimpleTTLCache,
    generate_cache_key,
    cached,
    get_cache_manager,
    init_cache_manager,
    CACHETOOLS_AVAILABLE,
)

# CacheWarmup（V1.5新增）
from .cache_warmup import (
    CacheWarmupService,
    get_warmup_service,
)

# AIProvider（V1.7新增）
from .ai_provider import (
    AIProvider,
    AIProviderType,
    AIProviderState,
    AIModelInfo,
    GenerationConfig,
    GenerationResult,
    AIProviderError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    AIProviderConfigError,
)

# AIServiceManager（V1.7新增）
from .ai_service_manager import AIServiceManager, get_ai_service_manager

# OnlineProvider（V1.7新增）
from .online_provider import OnlineProvider

# LocalProvider（V1.7新增）
from .local_provider import LocalProvider

# QwenProvider（V2.23新增 - 本地Qwen模型支持）
from .qwen_provider import QwenProvider

# SessionState（V1.9新增 - OpenClaw L1热记忆）
from .session_state import (
    SessionStateManager,
    SessionState,
    ActiveTask,
    TempContext,
    ErrorState,
    PendingData,
    get_session_state_manager,
    reset_session_state_manager,
)

# WALManager（V1.10新增 - OpenClaw核心机制）
from .wal_manager import (
    WALManager,
    WALRecord,
    WALState,
    get_wal_manager,
    reset_wal_manager,
)

# GitNotesManager（V1.11新增 - OpenClaw L3冷记忆）
from .git_notes_manager import (
    GitNotesManager,
    GitNote,
    BranchMemory,
    GitNotesState,
    get_git_notes_manager,
    reset_git_notes_manager,
)

# KnowledgeManager（V1.12新增 - 知识库CRUD接口）
from .knowledge_manager import (
    KnowledgeManager,
    KnowledgePoint,
    KnowledgeCreateResult,
    KnowledgeSearchResult,
    ImportResult,
    get_knowledge_manager,
    reset_knowledge_manager,
)

# KnowledgeRetriever（V1.13新增 - 知识库检索接口）
from .knowledge_retriever import (
    KnowledgeRetriever,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStats,
    get_knowledge_retriever,
    reset_knowledge_retriever,
)

# KnowledgeRecall（V1.14新增 - 知识库召回机制）
from .knowledge_recall import (
    KnowledgeRecall,
    KnowledgeConflict,
    RecallResult,
    ConsistencyCheckResult,
    GenreRecognizer,
    get_knowledge_recall,
    reset_knowledge_recall,
)

# ChapterEncoder（V1.15新增 - 章节向量编码）
from .chapter_encoder import (
    ChapterEncoder,
    ChapterEncodingResult,
    BatchEncodingResult,
    EncodingStats,
    get_chapter_encoder,
    reset_chapter_encoder,
)

# ContextRecaller（V1.16新增 - 上下文智能召回）
from .context_recall import (
    ContextRecaller,
    RecalledChapter,
    RecalledKnowledge,
    RecalledStyle,
    ContextSummary,
    TokenBudget,
    RecallStats,
    get_context_recaller,
    reset_context_recaller,
)

# ConflictFixer（V1.17新增 - 冲突修复建议生成）
from .conflict_fixer import (
    ConflictFixer,
    FixOption,
    ConflictFix,
    FixGenerationResult,
    FixStats,
    get_conflict_fixer,
    reset_conflict_fixer,
)

# ThreadPoolManager（V1.18新增 - 统一线程池管理器，解决卡顿问题）
from .thread_pool_manager import (
    ThreadPoolManager,
    thread_pool_manager,
)

# GUIAsyncHelper（V1.19新增 - GUI异步任务辅助）
from .gui_async_helper import (
    GUIAsyncHelper,
    create_async_helper,
)

__all__ = [
    # EventBus
    "EventBus",
    "EventPriority",
    "DeadLetterQueue",
    "get_event_bus",
    # PluginRegistry
    "PluginRegistry",
    "PluginState",
    "PluginType",
    "get_plugin_registry",
    # ServiceLocator
    "ServiceLocator",
    "ServiceScope",
    "ServiceScopeManager",
    "CircularDependencyError",
    "ServiceNotFoundError",
    "get_service_locator",
    # ConfigManager
    "ConfigManager",
    "ConfigValidationError",
    "ConfigKeyError",
    "get_config_manager",
    # PluginLoader
    "PluginLoader",
    "PluginLoadResult",
    "DependencyResolver",
    "HotSwapPermission",
    "PluginSignatureVerifier",
    "get_plugin_loader",
    # HotSwapManager
    "HotSwapManager",
    "HotSwapAction",
    "HotSwapState",
    "HotSwapEvent",
    "PluginStateInfo",
    "get_hot_swap_manager",
    # PluginInterface
    "BasePlugin",
    "AnalyzerPlugin",
    "GeneratorPlugin",
    "ValidatorPlugin",
    "StoragePlugin",
    "AIPlugin",
    "ToolPlugin",
    "ProtocolPlugin",
    # Models
    "Event",
    "HandlerInfo",
    "PluginMetadata",
    "PluginInfo",
    "ValidationScores",
    "GenerationRequest",
    "GenerationResult",
    "PluginEvent",
    # V1.2新增
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerManager",
    "get_circuit_breaker_manager",
    "SecureConfig",
    "SecureConfigError",
    "get_secure_config",
    "LogSanitizer",
    "SanitizingFormatter",
    "get_log_sanitizer",
    "PluginSigner",
    "PluginSignatureError",
    "get_plugin_signer",
    # UI层API
    "CoreServiceManager",
    "GenerationServiceProxy",
    "PluginServiceProxy",
    "ConfigServiceProxy",
    "EventServiceProxy",
    # Database
    "ConnectionPool",
    "DatabaseMigration",
    "AgentStateStore",
    "GenerationHistoryStore",
    "get_database",
    "get_agent_state_store",
    "get_generation_history_store",
    "close_database",
    # AsyncHandler
    "AsyncHandler",
    "Task",
    "TaskPriority",
    "TaskState",
    "PriorityTaskQueue",
    "get_async_handler",
    "init_async_handler",
    # Launcher
    "LazyLoader",
    "LoadPriority",
    "ModuleInfo",
    "get_lazy_loader",
    "OptimizedLauncher",
    "StartupConfig",
    "get_optimized_launcher",
    # ConfigService
    "ConfigService",
    "AppConfig",
    "get_config_service",
    # LoggingService
    "LoggingService",
    "get_logging_service",
    # BootstrapService
    "BootstrapService",
    "get_bootstrap_service",
    "initialize_core_services",
    "dispose_core_services",
    # CacheManager
    "CacheManager",
    "CacheConfig",
    "CacheEntry",
    "CacheStats",
    "SimpleTTLCache",
    "generate_cache_key",
    "cached",
    "get_cache_manager",
    "init_cache_manager",
    "CACHETOOLS_AVAILABLE",
    # CacheWarmup
    "CacheWarmupService",
    "get_warmup_service",
    # AIProvider & AIServiceManager
    "AIProvider",
    "AIProviderType",
    "AIProviderState",
    "AIModelInfo",
    "GenerationConfig",
    "GenerationResult",
    "AIProviderError",
    "AIProviderTimeoutError",
    "AIProviderUnavailableError",
    "AIProviderConfigError",
    "AIServiceManager",
    "get_ai_service_manager",
    # OnlineProvider
    "OnlineProvider",
    # LocalProvider
    "LocalProvider",
    # SessionState (L1热记忆)
    "SessionStateManager",
    "SessionState",
    "ActiveTask",
    "TempContext",
    "ErrorState",
    "PendingData",
    "get_session_state_manager",
    "reset_session_state_manager",
    # WALManager (WAL协议)
    "WALManager",
    "WALRecord",
    "WALState",
    "get_wal_manager",
    "reset_wal_manager",
    # GitNotesManager (L3冷记忆)
    "GitNotesManager",
    "GitNote",
    "BranchMemory",
    "GitNotesState",
    "get_git_notes_manager",
    "reset_git_notes_manager",
    # KnowledgeManager (知识库CRUD)
    "KnowledgeManager",
    "KnowledgePoint",
    "KnowledgeCreateResult",
    "KnowledgeSearchResult",
    "ImportResult",
    "get_knowledge_manager",
    "reset_knowledge_manager",
    # KnowledgeRetriever (知识库检索)
    "KnowledgeRetriever",
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievalStats",
    "get_knowledge_retriever",
    "reset_knowledge_retriever",
    # KnowledgeRecall (知识库召回)
    "KnowledgeRecall",
    "KnowledgeConflict",
    "RecallResult",
    "ConsistencyCheckResult",
    "GenreRecognizer",
    "get_knowledge_recall",
    "reset_knowledge_recall",
    # ChapterEncoder (章节向量编码)
    "ChapterEncoder",
    "ChapterEncodingResult",
    "BatchEncodingResult",
    "EncodingStats",
    "get_chapter_encoder",
    "reset_chapter_encoder",
    # ContextRecaller (上下文智能召回)
    "ContextRecaller",
    "RecalledChapter",
    "RecalledKnowledge",
    "RecalledStyle",
    "ContextSummary",
    "TokenBudget",
    "RecallStats",
    "get_context_recaller",
    "reset_context_recaller",
    # ConflictFixer (冲突修复建议生成)
    "ConflictFixer",
    "FixOption",
    "ConflictFix",
    "FixGenerationResult",
    "FixStats",
    "get_conflict_fixer",
    "reset_conflict_fixer",
    # ThreadPoolManager (统一线程池管理器)
    "ThreadPoolManager",
    "thread_pool_manager",
    # GUIAsyncHelper (GUI异步任务辅助)
    "GUIAsyncHelper",
    "create_async_helper",
]


__version__ = "1.19.0"
__author__ = "Novel Assistant Team"
