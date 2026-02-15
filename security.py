"""安全模块：路径消毒、命令验证、目录创建等。"""

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Optional, Tuple

import yaml


class SecurityManager:
    """管理安全相关的操作，包括路径验证、文件名消毒等。"""

    def __init__(self, config_path: str = "config.yaml") -> None:
        """初始化安全管理器，加载配置文件并创建必要目录。"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"配置文件 {config_path} 未找到"
            ) from exc

        self.temp_dir = Path(self.config['paths']['temp_dir']).resolve()
        self.mingw_dir = Path(self.config['paths']['mingw_dir']).resolve()
        self.create_secure_directories()

    def create_secure_directories(self) -> None:
        """创建安全的临时目录结构，设置适当权限。"""
        directories = [
            self.temp_dir / "compile",
            self.temp_dir / "execute",
            self.temp_dir / "cache",
            self.temp_dir / "inputs",
            self.temp_dir / "outputs",
            self.temp_dir / "sources"
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            if os.name != 'nt':
                os.chmod(directory, 0o700)

    def sanitize_filename(self, filename: str) -> str:
        """对文件名进行消毒，防止路径遍历攻击。"""
        safe_name = re.sub(r'[^\w\.\-]', '_', filename)
        safe_name = safe_name.lstrip('.')
        return safe_name[:100]

    def get_secure_temp_path(self, prefix: str = "oi") -> Path:
        """生成一个安全的临时文件路径（不实际创建文件）。"""
        timestamp = int(time.time() * 1000)
        random_hash = hashlib.md5(str(timestamp).encode()).hexdigest()[:8]
        safe_dir = self.temp_dir / prefix
        safe_dir.mkdir(exist_ok=True)
        return safe_dir / f"{timestamp}_{random_hash}"

    def validate_path(self, path: str) -> Tuple[bool, Optional[Path]]:
        """检查给定路径是否在允许的目录内。"""
        try:
            resolved = Path(path).resolve()
            temp_resolved = self.temp_dir.resolve()
            mingw_resolved = self.mingw_dir.resolve()
            if (
                str(resolved).startswith(str(temp_resolved)) or
                str(resolved).startswith(str(mingw_resolved))
            ):
                return True, resolved
            return False, None
        except (OSError, ValueError):
            return False, None

    def validate_command(self, command: str) -> bool:
        """检查命令是否包含危险操作。"""
        forbidden = self.config['security']['forbidden_commands']
        for forbidden_cmd in forbidden:
            if forbidden_cmd in command.lower():
                return False

        dangerous_patterns = [
            r'&&\s*rm',
            r';\s*rm',
            r'\|\s*rm',
            r'`.*`',
            r'\$\(.*\)',
            r'>\s*/dev/',
            r'>>\s*/dev/'
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False
        return True
