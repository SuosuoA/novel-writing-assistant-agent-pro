#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件清理器 - 安全删除词条

功能：
- 只删除JSON文件内的词条，不删除文件本身
- 自动创建备份
- 支持干运行模式

P2安全增强：
- 路径安全检查：防止路径穿越攻击（禁止../等）
- 权限验证：检查文件读写权限
"""

import json
import shutil
import logging
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class PathSecurityError(Exception):
    """路径安全异常"""
    pass


class PermissionError(Exception):
    """权限异常"""
    pass


class FileCleaner:
    """文件清理器 - 安全删除词条"""
    
    # 危险路径模式
    DANGEROUS_PATTERNS = [
        r'\.\.',           # 父目录引用
        r'[/\\]\.\.[/\\]', # 路径穿越
        r'^[/\\]',         # 绝对路径根
        r'^[A-Za-z]:',     # Windows盘符
        r'~',              # 用户主目录
        r'\$\{',           # 环境变量
        r'\%',             # Windows环境变量
    ]
    
    def __init__(self, backup_dir: Path, allowed_dirs: Optional[List[Path]] = None):
        """
        初始化清理器
        
        Args:
            backup_dir: 备份目录路径
            allowed_dirs: 允许操作的目录列表（白名单）
        """
        self.backup_dir = Path(backup_dir).resolve()
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置允许操作的目录白名单
        self.allowed_dirs = [Path(d).resolve() for d in (allowed_dirs or [self.backup_dir.parent.parent])]
        
        logger.info(f"[FILE_CLEANER] 初始化完成, 备份目录: {self.backup_dir}, 允许目录: {len(self.allowed_dirs)}个")
    
    def _validate_path(self, path: Path, operation: str = "access") -> Tuple[bool, str]:
        """
        验证路径安全性（P2-2安全增强）
        
        检查：
        1. 路径穿越攻击（../等）
        2. 路径是否在允许的目录内
        3. 路径是否解析到预期位置
        
        Args:
            path: 要验证的路径
            operation: 操作类型（access/read/write）
        
        Returns:
            (是否安全, 错误信息)
        """
        try:
            path_str = str(path)
            
            # 1. 检查危险模式
            for pattern in self.DANGEROUS_PATTERNS:
                if re.search(pattern, path_str):
                    return False, f"检测到危险路径模式: {pattern}"
            
            # 2. 规范化路径（解析符号链接、相对路径等）
            try:
                resolved_path = path.resolve()
            except Exception as e:
                return False, f"路径解析失败: {e}"
            
            # 3. 检查是否在允许的目录内
            is_allowed = False
            for allowed_dir in self.allowed_dirs:
                try:
                    resolved_path.relative_to(allowed_dir)
                    is_allowed = True
                    break
                except ValueError:
                    continue
            
            if not is_allowed:
                return False, f"路径不在允许的目录内: {resolved_path}"
            
            # 4. 检查路径是否存在（对于读取操作）
            if operation in ["access", "read"] and not resolved_path.exists():
                return False, f"路径不存在: {resolved_path}"
            
            return True, "路径安全"
            
        except Exception as e:
            return False, f"路径验证异常: {e}"
    
    def _check_permission(self, path: Path, operation: str = "read") -> Tuple[bool, str]:
        """
        检查文件权限（P2-4安全增强）
        
        Args:
            path: 文件路径
            operation: 操作类型（read/write）
        
        Returns:
            (有权限, 错误信息)
        """
        try:
            if operation == "read":
                if not os.access(path, os.R_OK):
                    return False, f"无读取权限: {path}"
            elif operation == "write":
                # 检查写入权限（如果文件存在检查文件权限，否则检查父目录权限）
                if path.exists():
                    if not os.access(path, os.W_OK):
                        return False, f"无写入权限: {path}"
                else:
                    if not os.access(path.parent, os.W_OK):
                        return False, f"无写入权限(父目录): {path.parent}"
            
            return True, "权限正常"
            
        except Exception as e:
            return False, f"权限检查异常: {e}"
    
    def remove_from_file(self, 
                       file_path: Path,
                       knowledge_ids: List[str],
                       dry_run: bool = False) -> Dict[str, Any]:
        """
        从文件中删除指定词条
        
        P2安全增强：添加路径安全检查和权限验证
        
        Args:
            file_path: JSON文件路径
            knowledge_ids: 要删除的词条ID列表
            dry_run: 干运行模式
        
        Returns:
            {
                "file_path": str,
                "original_count": 100,
                "final_count": 90,
                "removed_count": 10,
                "backup_path": str (if not dry_run)
            }
        """
        # P2-2: 路径安全检查
        is_safe, safety_msg = self._validate_path(file_path, "read")
        if not is_safe:
            logger.error(f"[FILE_CLEANER] 路径安全检查失败: {safety_msg}")
            return {
                "file_path": str(file_path),
                "original_count": 0,
                "final_count": 0,
                "removed_count": 0,
                "backup_path": None,
                "error": f"路径安全检查失败: {safety_msg}"
            }
        
        # P2-4: 权限验证
        has_read_perm, read_msg = self._check_permission(file_path, "read")
        if not has_read_perm:
            logger.error(f"[FILE_CLEANER] 读取权限验证失败: {read_msg}")
            return {
                "file_path": str(file_path),
                "original_count": 0,
                "final_count": 0,
                "removed_count": 0,
                "backup_path": None,
                "error": f"权限验证失败: {read_msg}"
            }
        
        # 1. 读取文件
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"[FILE_CLEANER] 读取文件失败: {file_path}, {e}")
            return {
                "file_path": str(file_path),
                "original_count": 0,
                "final_count": 0,
                "removed_count": 0,
                "backup_path": None,
                "error": str(e)
            }
        
        original_count = len(data.get('knowledge_points', []))
        
        # 2. 备份（非干运行）
        backup_path = None
        if not dry_run:
            backup_path = self._create_backup(file_path)
            if backup_path:
                try:
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"[FILE_CLEANER] 备份失败: {e}")
        
        # 3. 过滤词条
        knowledge_ids_set = set(knowledge_ids)
        knowledge_points = [
            kp for kp in data.get('knowledge_points', [])
            if kp.get('knowledge_id', '') not in knowledge_ids_set
        ]
        
        # P2-4: 写入权限验证
        if not dry_run:
            has_write_perm, write_msg = self._check_permission(file_path, "write")
            if not has_write_perm:
                logger.error(f"[FILE_CLEANER] 写入权限验证失败: {write_msg}")
                return {
                    "file_path": str(file_path),
                    "original_count": original_count,
                    "final_count": original_count,
                    "removed_count": 0,
                    "backup_path": str(backup_path) if backup_path else None,
                    "error": f"写入权限验证失败: {write_msg}"
                }
        
        # 4. 写回文件（非干运行）
        if not dry_run:
            data['knowledge_points'] = knowledge_points
            data['last_cleaned'] = datetime.now().isoformat()
            
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"[FILE_CLEANER] 写回文件失败: {e}")
                return {
                    "file_path": str(file_path),
                    "original_count": original_count,
                    "final_count": original_count,
                    "removed_count": 0,
                    "backup_path": str(backup_path) if backup_path else None,
                    "error": str(e)
                }
        
        removed_count = original_count - len(knowledge_points)
        
        logger.info(f"[FILE_CLEANER] 文件 {file_path.name}: 删除 {removed_count} 条")
        
        return {
            "file_path": str(file_path),
            "original_count": original_count,
            "final_count": len(knowledge_points),
            "removed_count": removed_count,
            "backup_path": str(backup_path) if backup_path else None
        }
    
    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """
        创建备份文件
        
        P2-3: 自动清理30天前的旧备份
        
        Args:
            file_path: 原文件路径
        
        Returns:
            备份文件路径
        """
        try:
            # P2-3: 自动清理旧备份（在创建新备份前）
            self.auto_cleanup_old_backups(days=30)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{file_path.stem}_backup_{timestamp}.json"
            backup_path = self.backup_dir / filename
            
            shutil.copy2(file_path, backup_path)
            
            logger.info(f"[FILE_CLEANER] 备份已创建: {backup_path}")
            
            return backup_path
        except Exception as e:
            logger.error(f"[FILE_CLEANER] 创建备份失败: {e}")
            return None
    
    def auto_cleanup_old_backups(self, days: int = 30) -> int:
        """
        自动清理旧备份文件（P2-3新增）
        
        在每次创建新备份时自动调用，删除超过指定天数的旧备份
        
        Args:
            days: 保留天数（默认30天）
        
        Returns:
            删除的文件数量
        """
        deleted_count = 0
        now = datetime.now()
        
        try:
            for backup_file in self.backup_dir.glob("*.json"):
                try:
                    # 从文件修改时间判断（更可靠）
                    file_mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
                    age_days = (now - file_mtime).days
                    
                    if age_days > days:
                        # 安全检查：确保是备份文件
                        if '_backup_' in backup_file.name:
                            backup_file.unlink()
                            deleted_count += 1
                            logger.info(f"[FILE_CLEANER] 自动清理旧备份: {backup_file.name} ({age_days}天前)")
                except Exception as e:
                    logger.warning(f"[FILE_CLEANER] 处理备份文件失败: {backup_file}, {e}")
            
            if deleted_count > 0:
                logger.info(f"[FILE_CLEANER] 自动清理完成: 删除 {deleted_count} 个旧备份文件")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"[FILE_CLEANER] 自动清理备份失败: {e}")
            return 0
    
    def clean_old_backups(self, days: int = 30) -> int:
        """
        清理旧备份文件
        
        Args:
            days: 保留天数
        
        Returns:
            删除的文件数量
        """
        deleted_count = 0
        now = datetime.now()
        
        for backup_file in self.backup_dir.glob("*.json"):
            try:
                # 从文件名提取时间戳
                parts = backup_file.stem.split('_')
                if len(parts) >= 4:
                    timestamp_str = f"{parts[-2]}_{parts[-1]}"
                    backup_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    
                    # 判断是否过期
                    age_days = (now - backup_time).days
                    if age_days > days:
                        backup_file.unlink()
                        deleted_count += 1
                        logger.info(f"[FILE_CLEANER] 删除旧备份: {backup_file}")
            except Exception as e:
                logger.warning(f"[FILE_CLEANER] 处理备份文件失败: {backup_file}, {e}")
        
        return deleted_count
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """
        列出所有可恢复的备份文件
        
        Returns:
            [
                {
                    "backup_path": str,
                    "original_file": str,
                    "timestamp": str,
                    "knowledge_count": int,
                    "size_kb": float
                }
            ]
        """
        backups = []
        
        for backup_file in sorted(self.backup_dir.glob("*.json"), reverse=True):
            try:
                # 从文件名提取原始文件名和时间戳
                parts = backup_file.stem.split('_backup_')
                if len(parts) == 2:
                    original_file = parts[0] + ".json"
                    timestamp = parts[1]
                    
                    # 读取备份文件获取知识条目数量
                    with open(backup_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        knowledge_count = len(data.get('knowledge_points', []))
                    
                    # 获取文件大小
                    size_kb = backup_file.stat().st_size / 1024
                    
                    backups.append({
                        "backup_path": str(backup_file),
                        "original_file": original_file,
                        "timestamp": timestamp,
                        "knowledge_count": knowledge_count,
                        "size_kb": round(size_kb, 2),
                        "created_at": datetime.fromtimestamp(backup_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    })
            except Exception as e:
                logger.warning(f"[FILE_CLEANER] 解析备份文件失败: {backup_file}, {e}")
        
        return backups
    
    def restore_from_backup(self, backup_path: Path) -> Dict[str, Any]:
        """
        从备份恢复知识点
        
        Args:
            backup_path: 备份文件路径
        
        Returns:
            {
                "success": bool,
                "restored_count": int,
                "original_file": str,
                "message": str
            }
        """
        try:
            # 读取备份文件
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            # 提取原始文件名
            parts = Path(backup_path).stem.split('_backup_')
            if len(parts) != 2:
                return {
                    "success": False,
                    "restored_count": 0,
                    "original_file": "",
                    "message": "无法解析备份文件名"
                }
            
            original_file = parts[0] + ".json"
            
            # 查找原始文件（可能在 knowledge 目录下）
            knowledge_dir = self.backup_dir.parent.parent / "knowledge"
            original_path = None
            
            for json_file in knowledge_dir.rglob(original_file):
                original_path = json_file
                break
            
            if not original_path:
                # 如果找不到原始文件，在备份目录创建
                original_path = knowledge_dir / original_file
                original_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 读取当前文件
            current_count = 0
            if original_path.exists():
                with open(original_path, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
                    current_count = len(current_data.get('knowledge_points', []))
            else:
                current_data = {"knowledge_points": []}
            
            # 合并知识点（备份中的知识点添加到当前文件）
            backup_points = backup_data.get('knowledge_points', [])
            current_ids = {kp.get('knowledge_id') for kp in current_data.get('knowledge_points', [])}
            
            restored_count = 0
            for kp in backup_points:
                kp_id = kp.get('knowledge_id')
                if kp_id not in current_ids:
                    current_data['knowledge_points'].append(kp)
                    restored_count += 1
            
            # 写回文件
            current_data['last_restored'] = datetime.now().isoformat()
            with open(original_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[FILE_CLEANER] 从备份恢复: {backup_path.name} -> {original_path.name}, 恢复 {restored_count} 条")
            
            return {
                "success": True,
                "restored_count": restored_count,
                "original_file": str(original_path),
                "message": f"成功恢复 {restored_count} 条知识点到 {original_path.name}"
            }
            
        except Exception as e:
            logger.error(f"[FILE_CLEANER] 恢复失败: {e}")
            return {
                "success": False,
                "restored_count": 0,
                "original_file": "",
                "message": f"恢复失败: {str(e)}"
            }
    
    def get_latest_backup(self) -> Optional[Dict[str, Any]]:
        """
        获取最新的备份文件信息
        
        Returns:
            最新备份信息，如果没有备份则返回 None
        """
        backups = self.list_backups()
        if backups:
            return backups[0]  # 已按时间倒序排列
        return None
