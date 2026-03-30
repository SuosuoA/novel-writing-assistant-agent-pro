"""
用户友好错误提示转换器
P2-003修复：将技术化错误提示转换为用户友好的提示

功能：
1. 自动识别异常类型并转换为友好提示
2. 提供具体的解决建议
3. 记录原始错误日志供开发者调试
"""

import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class UserFriendlyError:
    """用户友好错误提示转换器"""
    
    # 错误类型映射表
    ERROR_MAPPINGS = {
        # 网络相关错误
        r"ConnectionError|ConnectTimeout|连接被拒绝|Connection refused": {
            "title": "网络连接失败",
            "message": "无法连接到服务器，请检查网络连接。",
            "suggestion": "建议：\n1. 检查网络是否正常\n2. 确认API地址是否正确\n3. 尝试使用VPN或代理"
        },
        r"Timeout|timed out|超时": {
            "title": "请求超时",
            "message": "服务器响应时间过长，请稍后重试。",
            "suggestion": "建议：\n1. 检查网络连接速度\n2. 稍后重试\n3. 减少请求内容长度"
        },
        r"SSLError|SSL|证书|certificate": {
            "title": "安全连接失败",
            "message": "无法建立安全连接，可能是网络或证书问题。",
            "suggestion": "建议：\n1. 检查系统时间是否正确\n2. 更新系统证书\n3. 尝试其他网络环境"
        },
        
        # API相关错误
        r"401|Unauthorized|authentication|api_key|API key|invalid.*key": {
            "title": "API认证失败",
            "message": "API密钥无效或已过期。",
            "suggestion": "建议：\n1. 检查API Key是否正确\n2. 确认API Key是否已激活\n3. 重新生成API Key"
        },
        r"403|Forbidden|permission|权限": {
            "title": "权限不足",
            "message": "您没有执行此操作的权限。",
            "suggestion": "建议：\n1. 检查账户权限\n2. 确认API订阅状态\n3. 联系服务提供商"
        },
        r"404|Not Found|找不到|not found": {
            "title": "资源不存在",
            "message": "请求的资源不存在或已被删除。",
            "suggestion": "建议：\n1. 检查文件路径是否正确\n2. 确认资源是否已删除\n3. 刷新后重试"
        },
        r"429|Rate.*limit|rate.*limit|请求过于频繁": {
            "title": "请求过于频繁",
            "message": "API调用频率超过限制，请稍后重试。",
            "suggestion": "建议：\n1. 等待1-2分钟后重试\n2. 减少请求频率\n3. 升级API套餐"
        },
        r"500|502|503|504|Internal.*Error|Server.*Error|服务器错误": {
            "title": "服务器错误",
            "message": "远程服务器暂时不可用，请稍后重试。",
            "suggestion": "建议：\n1. 等待几分钟后重试\n2. 检查服务状态页面\n3. 联系技术支持"
        },
        
        # 文件相关错误
        r"FileNotFound|文件不存在|No such file": {
            "title": "文件未找到",
            "message": "指定的文件不存在。",
            "suggestion": "建议：\n1. 检查文件路径是否正确\n2. 确认文件是否已被移动或删除\n3. 使用浏览功能重新选择文件"
        },
        r"Permission.*denied|权限.*拒绝|Access.*denied": {
            "title": "文件访问被拒绝",
            "message": "没有权限访问该文件或文件夹。",
            "suggestion": "建议：\n1. 以管理员身份运行程序\n2. 检查文件是否被其他程序占用\n3. 修改文件权限"
        },
        r"disk.*full|磁盘.*满|No.*space": {
            "title": "磁盘空间不足",
            "message": "存储空间不足，无法完成操作。",
            "suggestion": "建议：\n1. 清理磁盘空间\n2. 更换保存位置\n3. 删除不需要的文件"
        },
        
        # 数据相关错误
        r"JSON.*Error|JSONDecode|解析.*失败|parse.*error": {
            "title": "数据格式错误",
            "message": "文件格式不正确或已损坏。",
            "suggestion": "建议：\n1. 检查文件是否为有效JSON格式\n2. 使用备份文件\n3. 重新导出数据"
        },
        r"ValidationError|验证.*失败|validation": {
            "title": "数据验证失败",
            "message": "输入的数据不符合要求。",
            "suggestion": "建议：\n1. 检查必填字段是否完整\n2. 确认数据格式是否正确\n3. 参考帮助文档"
        },
        r"KeyError|TypeError|ValueError|AttributeError": {
            "title": "数据处理错误",
            "message": "程序处理数据时遇到问题。",
            "suggestion": "建议：\n1. 检查输入数据是否完整\n2. 尝试重置相关设置\n3. 联系技术支持"
        },
        
        # 内存相关错误
        r"MemoryError|OutOfMemory|内存.*不足": {
            "title": "内存不足",
            "message": "程序运行所需内存不足。",
            "suggestion": "建议：\n1. 关闭其他程序释放内存\n2. 处理较小的文件\n3. 重启程序"
        },
        
        # 模型相关错误
        r"model.*not.*found|模型.*未找到|Model.*not.*exist": {
            "title": "模型未找到",
            "message": "指定的AI模型不存在或不可用。",
            "suggestion": "建议：\n1. 检查模型名称是否正确\n2. 确认API是否支持该模型\n3. 选择其他可用模型"
        },
        r"context.*length|上下文.*长度|token.*limit": {
            "title": "内容超长",
            "message": "输入内容超过了模型的最大处理长度。",
            "suggestion": "建议：\n1. 减少输入内容长度\n2. 分批处理\n3. 使用支持更长上下文的模型"
        },
        
        # 插件相关错误
        r"plugin.*not.*load|插件.*加载.*失败|Plugin.*error": {
            "title": "插件加载失败",
            "message": "无法加载指定的功能插件。",
            "suggestion": "建议：\n1. 检查插件是否已安装\n2. 重启程序\n3. 重新安装插件"
        },
        
        # 向量数据库相关错误
        r"LanceDB|vector.*db|向量.*库|embedding": {
            "title": "知识库错误",
            "message": "知识库操作失败。",
            "suggestion": "建议：\n1. 检查知识库文件是否完整\n2. 重建向量索引\n3. 清除缓存后重试"
        },
    }
    
    @classmethod
    def convert(cls, error: Exception, context: str = "") -> Tuple[str, str, str]:
        """
        将异常转换为用户友好的提示
        
        Args:
            error: 原始异常对象
            context: 错误上下文描述（可选）
        
        Returns:
            Tuple[str, str, str]: (标题, 用户友好提示, 完整提示)
        """
        error_str = str(error)
        error_type = type(error).__name__
        
        # 记录原始错误日志
        logger.error(f"[原始错误] 类型: {error_type}, 消息: {error_str}, 上下文: {context}")
        
        # 匹配错误模式
        for pattern, mapping in cls.ERROR_MAPPINGS.items():
            if re.search(pattern, error_str, re.IGNORECASE) or re.search(pattern, error_type, re.IGNORECASE):
                title = mapping["title"]
                message = mapping["message"]
                if context:
                    message = f"{context}时{message}"
                suggestion = mapping["suggestion"]
                
                full_message = f"{message}\n\n{suggestion}"
                return title, message, full_message
        
        # 未匹配到已知模式，使用通用提示
        title = "操作失败"
        if context:
            message = f"{context}时发生错误。"
        else:
            message = "程序执行时遇到问题。"
        
        # 隐藏技术细节，只显示简化信息
        suggestion = "建议：\n1. 稍后重试\n2. 检查输入是否正确\n3. 如问题持续，请联系技术支持"
        full_message = f"{message}\n\n{suggestion}"
        
        return title, message, full_message
    
    @classmethod
    def get_error_title(cls, error: Exception, context: str = "") -> str:
        """获取用户友好的错误标题"""
        title, _, _ = cls.convert(error, context)
        return title
    
    @classmethod
    def get_error_message(cls, error: Exception, context: str = "") -> str:
        """获取用户友好的错误消息"""
        _, message, _ = cls.convert(error, context)
        return message
    
    @classmethod
    def get_full_message(cls, error: Exception, context: str = "") -> str:
        """获取完整的用户友好提示（包含建议）"""
        _, _, full_message = cls.convert(error, context)
        return full_message


def show_user_friendly_error(parent, error: Exception, context: str = ""):
    """
    显示用户友好的错误提示框
    
    Args:
        parent: 父窗口
        error: 原始异常对象
        context: 错误上下文描述（可选）
    """
    from tkinter import messagebox
    
    title, _, full_message = UserFriendlyError.convert(error, context)
    messagebox.showerror(title, full_message)


def convert_exception(error: Exception, context: str = "") -> Tuple[str, str]:
    """
    快捷转换异常为用户友好提示
    
    Args:
        error: 原始异常对象
        context: 错误上下文描述（可选）
    
    Returns:
        Tuple[str, str]: (标题, 完整提示)
    """
    title, _, full_message = UserFriendlyError.convert(error, context)
    return title, full_message


# 常用错误转换函数
def convert_api_error(error: Exception, provider: str = "") -> Tuple[str, str]:
    """转换API相关错误"""
    context = f"连接{provider}" if provider else "API调用"
    return convert_exception(error, context)


def convert_file_error(error: Exception, operation: str = "") -> Tuple[str, str]:
    """转换文件相关错误"""
    context = f"{operation}文件" if operation else "文件操作"
    return convert_exception(error, context)


def convert_generation_error(error: Exception) -> Tuple[str, str]:
    """转换AI生成相关错误"""
    return convert_exception(error, "AI内容生成")


def convert_knowledge_error(error: Exception, operation: str = "") -> Tuple[str, str]:
    """转换知识库相关错误"""
    context = f"知识库{operation}" if operation else "知识库操作"
    return convert_exception(error, context)
