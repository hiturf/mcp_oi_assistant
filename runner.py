"""代码运行模块：编译、执行、调试C++程序。"""

import os
import resource
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import psutil
import yaml

from security import SecurityManager


class CodeRunner:
    """处理C++代码的编译、运行、调试和输出比较。"""

    def __init__(self, config_path: str = "config.yaml") -> None:
        """初始化运行器，加载配置和安全管理器。"""
        if config_path is None:
            config_path = "config.yaml"

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.security = SecurityManager(config_path)

    def compile_cpp(self, code: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """编译C++代码，返回包含成功标志、可执行文件路径和错误信息的字典。"""
        if filename is None:
            temp_path = self.security.get_secure_temp_path("compile")
            cpp_file = temp_path.with_suffix('.cpp')
            exe_file = temp_path.with_suffix('.exe')
        else:
            safe_name = self.security.sanitize_filename(filename)
            cpp_file = self.security.temp_dir / "sources" / f"{safe_name}.cpp"
            exe_file = self.security.temp_dir / "execute" / f"{safe_name}.exe"

        cpp_file.parent.mkdir(parents=True, exist_ok=True)
        cpp_file.write_text(code, encoding='utf-8')

        compiler = self.config['compilation']['compiler_path']
        std = self.config['compilation']['cpp_standard']
        optimization = self.config['compilation']['optimization_level']

        compile_cmd = [
            compiler,
            str(cpp_file),
            '-std=' + std,
            optimization,
            '-o', str(exe_file),
            '-Wall',
            '-Wextra',
            '-Werror'
        ]

        try:
            result = subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cpp_file.parent,
                check=False  # 明确指定不检查返回码
            )
            return {
                'success': result.returncode == 0,
                'executable': str(exe_file) if result.returncode == 0 else None,
                'output': result.stdout,
                'error': result.stderr,
                'return_code': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': '编译超时（30秒）',
                'executable': None
            }
        except (OSError, ValueError) as e:
            return {
                'success': False,
                'error': f'编译异常: {str(e)}',
                'executable': None
            }

    def _get_memory_usage(self, pid: int) -> int:
        """获取进程内存使用量（KB）。"""
        try:
            process = psutil.Process(pid)
            return process.memory_info().rss // 1024
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return 0
        except Exception:
            return 0

    def run_with_input(
        self,
        executable: str,
        input_data: str,
        time_limit: Optional[int] = None,
        memory_limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """运行可执行文件，提供输入数据，限制时间和内存。"""
        if not self.security.validate_command(executable):
            return {'success': False, 'error': '不安全的可执行文件路径'}

        actual_time_limit = (
            time_limit if time_limit is not None
            else self.config['execution']['max_time']
        )
        actual_memory_limit = (
            memory_limit if memory_limit is not None
            else self.config['execution']['max_memory']
        )

        input_file = self.security.get_secure_temp_path("inputs").with_suffix('.in')
        input_file.write_text(input_data, encoding='utf-8')
        output_file = input_file.with_suffix('.out')

        def set_limits() -> None:
            """设置资源限制（仅 Unix）。"""
            if os.name != 'nt':
                cpu_seconds = actual_time_limit // 1000 + 1
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
                memory_bytes = actual_memory_limit * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

        start_time = time.time()
        process = None
        try:
            with (
                open(input_file, 'r', encoding='utf-8') as infile,
                open(output_file, 'w', encoding='utf-8') as outfile
            ):
                process = subprocess.Popen(
                    [executable],
                    stdin=infile,
                    stdout=outfile,
                    stderr=subprocess.PIPE,
                    preexec_fn=set_limits if os.name != 'nt' else None,
                    text=True,
                    cwd=self.security.temp_dir / "execute"
                )
                try:
                    timeout_seconds = actual_time_limit / 1000 + 1
                    _, stderr = process.communicate(timeout=timeout_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    _, stderr = process.communicate()
                    return {
                        'success': False,
                        'error': f'运行超时（{actual_time_limit}ms）',
                        'time_used': actual_time_limit,
                        'output': None,
                        'exit_code': -1
                    }
                exit_code = process.returncode

            elapsed_time = (time.time() - start_time) * 1000
            output_content = output_file.read_text(encoding='utf-8', errors='ignore')

            max_output = self.config['execution']['max_output_size']
            if len(output_content.encode('utf-8')) > max_output:
                output_content = (
                    output_content[:max_output // 4] +
                    "\n... (输出被截断)"
                )

            return {
                'success': exit_code == 0,
                'output': output_content,
                'error': stderr,
                'time_used': int(elapsed_time),
                'memory_used': self._get_memory_usage(process.pid) if process.pid else 0,
                'exit_code': exit_code
            }
        except (OSError, ValueError) as e:
            return {
                'success': False,
                'error': f'运行异常: {str(e)}',
                'output': None,
                'time_used': 0
            }
        finally:
            if process and process.poll() is None:
                process.kill()

    def compare_outputs(
        self,
        actual: str,
        expected: str,
        ignore_whitespace: bool = True,
        ignore_case: bool = False
    ) -> Dict[str, Any]:
        """比较实际输出和预期输出，返回差异详情。"""
        if ignore_whitespace:
            actual = ' '.join(actual.split())
            expected = ' '.join(expected.split())
        if ignore_case:
            actual = actual.lower()
            expected = expected.lower()

        actual_lines = actual.strip().split('\n')
        expected_lines = expected.strip().split('\n')
        differences = []
        max_lines = max(len(actual_lines), len(expected_lines))

        for i in range(max_lines):
            actual_line = actual_lines[i] if i < len(actual_lines) else ""
            expected_line = expected_lines[i] if i < len(expected_lines) else ""
            if actual_line != expected_line:
                differences.append({
                    'line': i + 1,
                    'actual': actual_line,
                    'expected': expected_line
                })

        return {
            'match': len(differences) == 0,
            'differences': differences,
            'actual_line_count': len(actual_lines),
            'expected_line_count': len(expected_lines)
        }

    def run_gdb(self, executable: str, script: Optional[str] = None) -> Dict[str, Any]:
        """使用GDB调试程序，返回调试输出。"""
        if not self.security.validate_command(executable):
            return {'success': False, 'error': '不安全的可执行文件路径'}

        gdb_script = self.security.get_secure_temp_path("gdb").with_suffix('.gdb')
        if script:
            gdb_script.write_text(script, encoding='utf-8')
        else:
            default_script = """
            set pagination off
            break main
            run
            backtrace
            info registers
            x/10i $pc
            quit
            """
            gdb_script.write_text(default_script, encoding='utf-8')

        try:
            gdb_path = str(Path(self.config['paths']['mingw_dir']) / "bin" / "gdb.exe")
            cmd = [gdb_path, '-x', str(gdb_script), executable, '--batch']
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.security.temp_dir / "execute",
                check=False
            )
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'return_code': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'GDB调试超时', 'output': None}
        except (OSError, ValueError) as e:
            return {'success': False, 'error': f'GDB调试异常: {str(e)}', 'output': None}
