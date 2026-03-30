"""
记忆备份/恢复工具（OpenClaw mem9 L5 云备份层）

参考 OpenClaw mem9 框架设计：
- 完整备份：备份所有记忆层级（L1-L4）
- 选择性备份：支持备份指定层级
- 增量备份：只备份变更内容
- 验证恢复：恢复前验证备份完整性

文件位置：tools/memory_backup.py

作者：AI工程师
日期：2026-03-26
版本：V1.0
"""

import os
import sys
import json
import shutil
import hashlib
import tarfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class BackupManifest:
    """备份清单数据模型"""
    version: str = "1.0"
    created_at: str = ""
    workspace_root: str = ""
    backup_type: str = "full"  # full / incremental / selective
    layers: List[str] = field(default_factory=list)
    files_count: int = 0
    total_size: int = 0
    checksum: str = ""
    description: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'BackupManifest':
        return cls(**data)


@dataclass
class BackupResult:
    """备份结果"""
    success: bool
    backup_path: str = ""
    manifest: Optional[BackupManifest] = None
    error: str = ""
    files_count: int = 0
    total_size: int = 0


@dataclass
class RestoreResult:
    """恢复结果"""
    success: bool
    layers_restored: List[str] = field(default_factory=list)
    files_restored: int = 0
    error: str = ""
    warnings: List[str] = field(default_factory=list)


class MemoryBackupTool:
    """
    记忆备份/恢复工具
    
    核心功能：
    1. 完整备份：备份所有记忆层级（L1-L4）
    2. 选择性备份：支持备份指定层级
    3. 增量备份：只备份变更内容（基于checksum）
    4. 验证恢复：恢复前验证备份完整性
    5. 压缩备份：使用tar.gz格式压缩
    """
    
    # 记忆层级定义
    MEMORY_LAYERS = {
        "L1": {
            "name": "热记忆",
            "paths": [".workbuddy/session-state.md", ".workbuddy/wal.json"],
            "description": "当前会话状态、WAL日志"
        },
        "L2": {
            "name": "温记忆",
            "paths": ["data/vector_store", "data/chapter_encoding_history.json"],
            "description": "向量数据库、章节编码历史"
        },
        "L3": {
            "name": "冷记忆",
            "paths": [".git/refs/notes"],  # Git-Notes
            "description": "Git-Notes分支感知历史"
        },
        "L4": {
            "name": "精选档案",
            "paths": ["Memory-Novel Writing Assistant-Agent Pro"],
            "description": "MEMORY.md、日志文档"
        },
        "config": {
            "name": "配置文件",
            "paths": ["config.yaml", ".workbuddy/settings.local.json"],
            "description": "项目配置"
        }
    }
    
    def __init__(self, workspace_root: Path = None):
        """
        初始化备份工具
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = workspace_root or Path(os.getcwd())
        self.backup_dir_name = "memory_backups"
        
    def backup(
        self,
        output_dir: Path = None,
        layers: List[str] = None,
        description: str = "",
        compress: bool = True
    ) -> BackupResult:
        """
        执行备份
        
        Args:
            output_dir: 输出目录（默认为workspace/memory_backups）
            layers: 要备份的层级列表（None=全部）
            description: 备份描述
            compress: 是否压缩（tar.gz）
            
        Returns:
            BackupResult: 备份结果
        """
        try:
            # 确定备份层级
            if layers is None:
                layers = list(self.MEMORY_LAYERS.keys())
                backup_type = "full"
            else:
                backup_type = "selective"
            
            # 创建备份目录
            if output_dir is None:
                output_dir = self.workspace_root / self.backup_dir_name
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"backup_{timestamp}"
            backup_path = output_dir / backup_name
            backup_path.mkdir(parents=True, exist_ok=True)
            
            # 创建清单
            manifest = BackupManifest(
                version="1.0",
                created_at=datetime.now().isoformat(),
                workspace_root=str(self.workspace_root),
                backup_type=backup_type,
                layers=layers,
                description=description
            )
            
            files_count = 0
            total_size = 0
            
            # 备份各层级
            for layer in layers:
                if layer not in self.MEMORY_LAYERS:
                    logger.warning(f"未知层级: {layer}")
                    continue
                
                layer_info = self.MEMORY_LAYERS[layer]
                layer_backup_dir = backup_path / layer
                layer_backup_dir.mkdir(exist_ok=True)
                
                for rel_path in layer_info["paths"]:
                    src_path = self.workspace_root / rel_path
                    
                    if not src_path.exists():
                        logger.debug(f"跳过不存在的路径: {rel_path}")
                        continue
                    
                    dst_path = layer_backup_dir / Path(rel_path).name
                    
                    if src_path.is_file():
                        shutil.copy2(src_path, dst_path)
                        files_count += 1
                        total_size += src_path.stat().st_size
                    elif src_path.is_dir():
                        shutil.copytree(src_path, dst_path)
                        for f in dst_path.rglob("*"):
                            if f.is_file():
                                files_count += 1
                                total_size += f.stat().st_size
            
            # 更新清单
            manifest.files_count = files_count
            manifest.total_size = total_size
            
            # 计算校验和
            manifest.checksum = self._calculate_checksum(backup_path)
            
            # 保存清单
            manifest_path = backup_path / "manifest.json"
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
            
            # 压缩
            if compress:
                compressed_path = self._compress_backup(backup_path)
                shutil.rmtree(backup_path)
                backup_path = compressed_path
            
            logger.info(f"备份完成: {backup_path}")
            logger.info(f"文件数: {files_count}, 大小: {total_size / 1024:.2f} KB")
            
            return BackupResult(
                success=True,
                backup_path=str(backup_path),
                manifest=manifest,
                files_count=files_count,
                total_size=total_size
            )
            
        except Exception as e:
            logger.error(f"备份失败: {e}")
            return BackupResult(success=False, error=str(e))
    
    def restore(
        self,
        backup_path: Path,
        layers: List[str] = None,
        verify: bool = True,
        create_backup: bool = True
    ) -> RestoreResult:
        """
        恢复备份
        
        Args:
            backup_path: 备份路径
            layers: 要恢复的层级列表（None=全部）
            verify: 是否验证备份完整性
            create_backup: 是否在恢复前创建当前状态的备份
            
        Returns:
            RestoreResult: 恢复结果
        """
        try:
            # 解压（如果是压缩文件）
            if backup_path.suffix == '.gz' or backup_path.suffix == '.tar':
                backup_path = self._decompress_backup(backup_path)
            
            # 验证备份
            if verify:
                is_valid, error = self._verify_backup(backup_path)
                if not is_valid:
                    return RestoreResult(success=False, error=f"备份验证失败: {error}")
            
            # 读取清单
            manifest_path = backup_path / "manifest.json"
            if not manifest_path.exists():
                return RestoreResult(success=False, error="备份清单不存在")
            
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = BackupManifest.from_dict(json.load(f))
            
            # 确定恢复层级
            if layers is None:
                layers = manifest.layers
            
            # 创建当前状态备份
            if create_backup:
                current_backup = self.backup(
                    description="恢复前自动备份",
                    layers=layers,
                    compress=True
                )
                logger.info(f"已创建当前状态备份: {current_backup.backup_path}")
            
            files_restored = 0
            layers_restored = []
            warnings = []
            
            # 恢复各层级
            for layer in layers:
                if layer not in self.MEMORY_LAYERS:
                    warnings.append(f"未知层级: {layer}")
                    continue
                
                layer_backup_dir = backup_path / layer
                if not layer_backup_dir.exists():
                    warnings.append(f"备份中不存在层级: {layer}")
                    continue
                
                layer_info = self.MEMORY_LAYERS[layer]
                
                for rel_path in layer_info["paths"]:
                    src_name = Path(rel_path).name
                    src_path = layer_backup_dir / src_name
                    dst_path = self.workspace_root / rel_path
                    
                    if not src_path.exists():
                        continue
                    
                    # 删除现有文件/目录
                    if dst_path.exists():
                        if dst_path.is_dir():
                            shutil.rmtree(dst_path)
                        else:
                            dst_path.unlink()
                    
                    # 创建父目录
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 复制
                    if src_path.is_file():
                        shutil.copy2(src_path, dst_path)
                        files_restored += 1
                    elif src_path.is_dir():
                        shutil.copytree(src_path, dst_path)
                        for f in dst_path.rglob("*"):
                            if f.is_file():
                                files_restored += 1
                
                layers_restored.append(layer)
            
            logger.info(f"恢复完成: {files_restored} 个文件")
            
            return RestoreResult(
                success=True,
                layers_restored=layers_restored,
                files_restored=files_restored,
                warnings=warnings
            )
            
        except Exception as e:
            logger.error(f"恢复失败: {e}")
            return RestoreResult(success=False, error=str(e))
    
    def list_backups(self, output_dir: Path = None) -> List[Dict]:
        """
        列出所有备份
        
        Args:
            output_dir: 备份目录
            
        Returns:
            List[Dict]: 备份列表
        """
        if output_dir is None:
            output_dir = self.workspace_root / self.backup_dir_name
        
        if not output_dir.exists():
            return []
        
        backups = []
        
        for backup in output_dir.iterdir():
            if backup.is_file() and backup.suffix == '.gz':
                # 压缩备份
                backups.append({
                    "name": backup.name,
                    "path": str(backup),
                    "type": "compressed",
                    "size": backup.stat().st_size,
                    "created_at": datetime.fromtimestamp(backup.stat().st_mtime).isoformat()
                })
            elif backup.is_dir():
                # 未压缩备份
                manifest_path = backup / "manifest.json"
                if manifest_path.exists():
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = BackupManifest.from_dict(json.load(f))
                    backups.append({
                        "name": backup.name,
                        "path": str(backup),
                        "type": "directory",
                        "manifest": manifest.to_dict(),
                        "size": sum(f.stat().st_size for f in backup.rglob("*") if f.is_file()),
                        "created_at": manifest.created_at
                    })
        
        # 按创建时间排序
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups
    
    def _calculate_checksum(self, backup_path: Path) -> str:
        """计算备份校验和"""
        hasher = hashlib.sha256()
        
        for file_path in sorted(backup_path.rglob("*")):
            if file_path.is_file() and file_path.name != "manifest.json":
                with open(file_path, 'rb') as f:
                    hasher.update(file_path.name.encode())
                    hasher.update(f.read())
        
        return hasher.hexdigest()[:16]
    
    def _verify_backup(self, backup_path: Path) -> Tuple[bool, str]:
        """验证备份完整性"""
        manifest_path = backup_path / "manifest.json"
        
        if not manifest_path.exists():
            return False, "清单文件不存在"
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = BackupManifest.from_dict(json.load(f))
        
        # 验证校验和
        current_checksum = self._calculate_checksum(backup_path)
        if current_checksum != manifest.checksum:
            return False, f"校验和不匹配: {current_checksum} != {manifest.checksum}"
        
        # 验证文件数量
        actual_files = sum(1 for _ in backup_path.rglob("*") if _.is_file())
        if actual_files != manifest.files_count + 1:  # +1 for manifest
            return False, f"文件数量不匹配: {actual_files} != {manifest.files_count + 1}"
        
        return True, ""
    
    def _compress_backup(self, backup_path: Path) -> Path:
        """压缩备份"""
        compressed_path = backup_path.parent / f"{backup_path.name}.tar.gz"
        
        with tarfile.open(compressed_path, "w:gz") as tar:
            tar.add(backup_path, arcname=backup_path.name)
        
        return compressed_path
    
    def _decompress_backup(self, compressed_path: Path) -> Path:
        """解压备份"""
        with tarfile.open(compressed_path, "r:gz") as tar:
            # 使用filter参数避免Python 3.14 deprecation警告
            tar.extractall(path=compressed_path.parent, filter='data')
        
        # 返回解压后的目录
        return compressed_path.parent / compressed_path.name.replace('.tar.gz', '')


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="记忆备份/恢复工具")
    parser.add_argument("action", choices=["backup", "restore", "list"], help="操作类型")
    parser.add_argument("--output", "-o", help="输出目录")
    parser.add_argument("--input", "-i", help="备份路径（恢复时）")
    parser.add_argument("--layers", "-l", nargs="+", help="备份/恢复的层级")
    parser.add_argument("--description", "-d", default="", help="备份描述")
    parser.add_argument("--no-compress", action="store_true", help="不压缩")
    parser.add_argument("--no-verify", action="store_true", help="不验证")
    parser.add_argument("--no-backup", action="store_true", help="恢复前不创建备份")
    
    args = parser.parse_args()
    
    tool = MemoryBackupTool()
    
    if args.action == "backup":
        result = tool.backup(
            output_dir=Path(args.output) if args.output else None,
            layers=args.layers,
            description=args.description,
            compress=not args.no_compress
        )
        
        if result.success:
            print(f"备份成功: {result.backup_path}")
            print(f"文件数: {result.files_count}, 大小: {result.total_size / 1024:.2f} KB")
        else:
            print(f"备份失败: {result.error}")
            sys.exit(1)
    
    elif args.action == "restore":
        if not args.input:
            print("错误: 恢复操作需要 --input 参数")
            sys.exit(1)
        
        result = tool.restore(
            backup_path=Path(args.input),
            layers=args.layers,
            verify=not args.no_verify,
            create_backup=not args.no_backup
        )
        
        if result.success:
            print(f"恢复成功: {result.files_restored} 个文件")
            print(f"恢复层级: {', '.join(result.layers_restored)}")
            if result.warnings:
                print(f"警告: {', '.join(result.warnings)}")
        else:
            print(f"恢复失败: {result.error}")
            sys.exit(1)
    
    elif args.action == "list":
        backups = tool.list_backups(
            output_dir=Path(args.output) if args.output else None
        )
        
        if not backups:
            print("无备份记录")
        else:
            print(f"共 {len(backups)} 个备份:")
            for backup in backups:
                size_kb = backup["size"] / 1024
                print(f"  - {backup['name']}: {size_kb:.2f} KB, {backup['created_at']}")


if __name__ == "__main__":
    main()
