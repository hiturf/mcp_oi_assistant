"""MCP服务器主模块，提供OI助手工具。"""

import asyncio
import subprocess
import sys
import time
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Optional

# MCP imports - 这些需要正确安装
try:
    from mcp import types
    from mcp.server import Server
    import mcp.server.stdio
except ImportError:
    print("请安装mcp包: pip install mcp", file=sys.stderr)
    raise

from runner import CodeRunner
from security import SecurityManager

logger = getLogger(__name__)


class CommandExecutor:
    """命令执行器，封装subprocess调用。"""
    
    def __init__(self, security: SecurityManager):
        self.security = security
        self.timeout_default = 30
    
    def execute(
        self,
        cmd: str,
        timeout: int = 30,
        cwd: Optional[str] = None,
        capture_output: bool = True
    ) -> Dict[str, Any]:
        """执行命令并返回结果。"""
        if not self.security.validate_command(cmd):
            return {
                'success': False,
                'error': '不安全的命令',
                'stdout': '',
                'stderr': '命令被安全策略阻止',
                'returncode': -1
            }
        
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                cwd=cwd,
                check=False
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': f'执行超时（{timeout}秒）',
                'stdout': '',
                'stderr': '',
                'returncode': -1
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'stdout': '',
                'stderr': '',
                'returncode': -1
            }


class ToolHandler:
    """工具处理器基类。"""
    
    def __init__(self, executor: CommandExecutor, security: SecurityManager):
        self.executor = executor
        self.security = security
    
    def format_result(self, title: str, cmd: str, result: Dict[str, Any]) -> str:
        """格式化执行结果。"""
        lines = [
            f"## {title}",
            "```bash",
            cmd,
            "```",
            ""
        ]
        
        if result['success']:
            lines.append("✅ 执行成功")
        else:
            lines.append("❌ 执行失败")
        
        if result.get('stdout'):
            lines.extend(["输出:", "```", result['stdout'], "```"])
        if result.get('stderr'):
            lines.extend(["错误信息:", "```", result['stderr'], "```"])
        if 'returncode' in result:
            lines.append(f"返回码: {result['returncode']}")
        
        return "\n".join(lines)


class CompileHandler(ToolHandler):
    """编译相关命令处理器。"""
    
    async def handle_gpp(self, args: Dict[str, Any]) -> str:
        source = args.get("source_file", "")
        output = args.get("output_file", "")
        flags = args.get("extra_flags", "")
        cmd = f"g++ {source} -o {output}"
        if flags:
            cmd += f" {flags}"
        result = self.executor.execute(cmd)
        return self.format_result("g++ 编译命令", cmd, result)
    
    async def handle_gcc(self, args: Dict[str, Any]) -> str:
        source = args.get("source_file", "")
        output = args.get("output_file", "")
        flags = args.get("extra_flags", "")
        cmd = f"gcc {source} -o {output}"
        if flags:
            cmd += f" {flags}"
        result = self.executor.execute(cmd)
        return self.format_result("gcc 编译命令", cmd, result)
    
    async def handle_make(self, args: Dict[str, Any]) -> str:
        target = args.get("target", "all")
        make_dir = args.get("makefile_dir", ".")
        extra = args.get("extra_args", "")
        cmd = f"make -C {make_dir} {target}"
        if extra:
            cmd += f" {extra}"
        result = self.executor.execute(cmd, timeout=60, cwd=make_dir)
        return self.format_result("make 自动化编译", cmd, result)


class DebugHandler(ToolHandler):
    """调试相关命令处理器。"""
    
    async def handle_gdb(self, args: Dict[str, Any]) -> str:
        executable = args.get("executable", "")
        commands = args.get("commands", "break main\nrun\nbacktrace\nquit")
        
        script_file = self.security.get_secure_temp_path("gdb").with_suffix('.gdb')
        script_file.write_text(commands, encoding='utf-8')
        
        cmd = f"gdb -x {script_file} {executable} --batch"
        result = self.executor.execute(cmd, timeout=60)
        
        # 清理临时文件
        if script_file.exists():
            script_file.unlink()
        
        lines = [
            "## GDB 调试",
            f"可执行文件: {executable}",
            "调试脚本:",
            "```gdb",
            commands,
            "```",
            ""
        ]
        
        if result['success']:
            lines.append("✅ 调试完成")
        else:
            lines.append("❌ 调试失败")
        
        if result.get('stdout'):
            lines.extend(["调试输出:", "```", result['stdout'], "```"])
        if result.get('stderr'):
            lines.extend(["错误信息:", "```", result['stderr'], "```"])
        
        return "\n".join(lines)


class BinaryHandler(ToolHandler):
    """二进制工具命令处理器。"""
    
    async def handle_ld(self, args: Dict[str, Any]) -> str:
        objects = args.get("object_files", "")
        output = args.get("output_file", "")
        lib_paths = args.get("library_paths", "")
        libs = args.get("libraries", "")
        
        cmd = f"ld {objects} -o {output}"
        if lib_paths:
            cmd += f" {lib_paths}"
        if libs:
            cmd += f" {libs}"
        
        result = self.executor.execute(cmd)
        return self.format_result("ld 链接器", cmd, result)
    
    async def handle_as(self, args: Dict[str, Any]) -> str:
        source = args.get("source_file", "")
        output = args.get("output_file", "")
        
        if not output:
            output = str(Path(source).with_suffix('.o'))
        
        cmd = f"as {source} -o {output}"
        result = self.executor.execute(cmd)
        return self.format_result("as 汇编器", cmd, result)
    
    async def handle_objdump(self, args: Dict[str, Any]) -> str:
        file_path = args.get("file", "")
        options = args.get("options", "-d")
        cmd = f"objdump {options} {file_path}"
        
        result = self.executor.execute(cmd, timeout=30)
        lines = [
            "## objdump 分析",
            f"文件: {file_path}",
            f"选项: {options}",
            "```bash",
            cmd,
            "```",
            ""
        ]
        
        if result['success'] and result.get('stdout'):
            output = result['stdout']
            if len(output) > 10000:
                output = output[:10000] + "\n... (输出被截断)"
            lines.extend(["输出:", "```asm", output, "```"])
        elif not result['success']:
            lines.append("❌ 执行失败")
            if result.get('stderr'):
                lines.extend(["错误信息:", "```", result['stderr'], "```"])
        
        return "\n".join(lines)
    
    async def handle_nm(self, args: Dict[str, Any]) -> str:
        file_path = args.get("file", "")
        options = args.get("options", "-C")
        cmd = f"nm {options} {file_path}"
        
        result = self.executor.execute(cmd, timeout=30)
        lines = [
            "## nm 符号表",
            f"文件: {file_path}",
            f"选项: {options}",
            "```bash",
            cmd,
            "```",
            ""
        ]
        
        if result['success'] and result.get('stdout'):
            output = result['stdout']
            if len(output) > 5000:
                output = output[:5000] + "\n... (输出被截断)"
            lines.extend(["输出:", "```", output, "```"])
        elif not result['success']:
            lines.append("❌ 执行失败")
            if result.get('stderr'):
                lines.extend(["错误信息:", "```", result['stderr'], "```"])
        
        return "\n".join(lines)


class OIAssistantServer:
    """MCP服务器，提供OI助手工具。"""

    def __init__(self) -> None:
        """初始化服务器、运行器和安全管理器。"""
        self.runner = CodeRunner()
        self.security = SecurityManager()
        self.executor = CommandExecutor(self.security)
        
        # 初始化各处理器
        self.compile_handler = CompileHandler(self.executor, self.security)
        self.debug_handler = DebugHandler(self.executor, self.security)
        self.binary_handler = BinaryHandler(self.executor, self.security)
        
        self.server = Server("oi-assistant")
        self.setup_handlers()
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def setup_handlers(self) -> None:
        """注册MCP工具处理器。"""

        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            return [
                # 🎯 核心命令
                types.Tool(
                    name="g++",
                    description="🎯 编译C++代码 - 最常用的编译命令",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "source_file": {"type": "string", "description": "源文件路径"},
                            "output_file": {"type": "string", "description": "输出文件名"},
                            "extra_flags": {"type": "string", "description": "额外编译选项", "default": ""}
                        },
                        "required": ["source_file", "output_file"]
                    }
                ),
                types.Tool(
                    name="gcc",
                    description="🎯 编译C代码 - 用于C语言编程",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "source_file": {"type": "string", "description": "源文件路径"},
                            "output_file": {"type": "string", "description": "输出文件名"},
                            "extra_flags": {"type": "string", "description": "额外编译选项", "default": ""}
                        },
                        "required": ["source_file", "output_file"]
                    }
                ),
                
                # 🔧 辅助命令
                types.Tool(
                    name="gdb",
                    description="🔧 调试程序 - 单步执行、查看变量、设置断点",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "executable": {"type": "string", "description": "要调试的可执行文件"},
                            "commands": {"type": "string", "description": "GDB命令", "default": "break main\nrun\nbacktrace\nquit"}
                        },
                        "required": ["executable"]
                    }
                ),
                types.Tool(
                    name="make",
                    description="🔧 自动化编译 - 用于多文件项目",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "description": "make目标", "default": "all"},
                            "makefile_dir": {"type": "string", "description": "Makefile所在目录", "default": "."},
                            "extra_args": {"type": "string", "description": "额外参数", "default": ""}
                        }
                    }
                ),
                types.Tool(
                    name="ld",
                    description="🔧 链接器 - 处理链接错误时使用",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "object_files": {"type": "string", "description": "目标文件列表"},
                            "output_file": {"type": "string", "description": "输出文件名"},
                            "library_paths": {"type": "string", "description": "库路径", "default": ""},
                            "libraries": {"type": "string", "description": "链接的库", "default": ""}
                        },
                        "required": ["object_files", "output_file"]
                    }
                ),
                types.Tool(
                    name="as",
                    description="🔧 汇编器 - 将汇编代码转换为机器码",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "source_file": {"type": "string", "description": "汇编源文件"},
                            "output_file": {"type": "string", "description": "输出目标文件", "default": ""}
                        },
                        "required": ["source_file"]
                    }
                ),
                types.Tool(
                    name="objdump",
                    description="🔧 查看二进制信息 - 反汇编、查看段信息",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file": {"type": "string", "description": "要分析的文件"},
                            "options": {"type": "string", "description": "objdump选项", "default": "-d"}
                        },
                        "required": ["file"]
                    }
                ),
                types.Tool(
                    name="nm",
                    description="🔧 列出符号表 - 查看目标文件中的函数和变量",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file": {"type": "string", "description": "要分析的文件"},
                            "options": {"type": "string", "description": "nm选项", "default": "-C"}
                        },
                        "required": ["file"]
                    }
                ),
                
                # 原有的工具（简化版）
                types.Tool(
                    name="compile_and_run",
                    description="编译并运行C++代码（集成版）",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "C++源代码"},
                            "input": {"type": "string", "description": "输入数据"},
                            "expected_output": {"type": "string", "description": "预期输出"},
                            "filename": {"type": "string", "description": "文件名"}
                        },
                        "required": ["code", "input"]
                    }
                ),
                types.Tool(
                    name="compare_outputs",
                    description="比较两个输出",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "actual": {"type": "string", "description": "实际输出"},
                            "expected": {"type": "string", "description": "预期输出"},
                            "ignore_whitespace": {"type": "boolean", "default": True},
                            "ignore_case": {"type": "boolean", "default": False}
                        },
                        "required": ["actual", "expected"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, args: Dict[str, Any]) -> List[types.TextContent]:
            """分发工具调用请求。"""
            session_id = f"session_{int(time.time())}_{hash(str(args)) % 10000}"
            self.sessions[session_id] = {"start_time": time.time(), "tool": name}
            
            try:
                # 分发到对应的处理器
                handlers = {
                    "g++": self.compile_handler.handle_gpp,
                    "gcc": self.compile_handler.handle_gcc,
                    "make": self.compile_handler.handle_make,
                    "gdb": self.debug_handler.handle_gdb,
                    "ld": self.binary_handler.handle_ld,
                    "as": self.binary_handler.handle_as,
                    "objdump": self.binary_handler.handle_objdump,
                    "nm": self.binary_handler.handle_nm,
                }
                
                if name in handlers:
                    result = await handlers[name](args)
                    return [types.TextContent(type="text", text=result)]
                
                if name == "compile_and_run":
                    return await self._handle_compile_and_run(args, session_id)
                if name == "compare_outputs":
                    return await self._handle_compare_outputs(args)
                
                return [types.TextContent(type="text", text=f"未知工具: {name}")]
                
            except Exception as e:
                logger.exception("工具执行错误")
                return [types.TextContent(type="text", text=f"错误: {str(e)}")]
            finally:
                self.sessions.pop(session_id, None)

    async def _handle_compile_and_run(self, args: Dict[str, Any], session_id: str) -> List[types.TextContent]:
        """处理编译运行请求。"""
        code = args.get("code", "")
        input_data = args.get("input", "")
        expected = args.get("expected_output", "")
        filename = args.get("filename", f"program_{session_id}")
        
        lines = [f"## 编译与运行报告", f"会话ID: {session_id}", f"文件名: {filename}", ""]
        
        # 编译
        lines.append("### 1. 编译阶段")
        compile_result = self.runner.compile_cpp(code, filename)
        if compile_result['success']:
            lines.append("✅ 编译成功")
        else:
            lines.append("❌ 编译失败")
            if compile_result['error']:
                lines.extend(["错误信息:", "```", compile_result['error'], "```"])
            return [types.TextContent(type="text", text="\n".join(lines))]
        
        # 运行
        lines.append("")
        lines.append("### 2. 运行阶段")
        run_result = self.runner.run_with_input(compile_result['executable'], input_data)
        lines.append(f"运行状态: {'✅ 成功' if run_result['success'] else '❌ 失败'}")
        lines.append(f"时间消耗: {run_result['time_used']}ms")
        
        if run_result['output']:
            lines.extend(["程序输出:", "```", run_result['output'], "```"])
        
        # 比较输出
        if expected and run_result['output']:
            lines.append("")
            lines.append("### 3. 输出比较")
            compare = self.runner.compare_outputs(run_result['output'], expected)
            lines.append("✅ 输出完全匹配！" if compare['match'] else "❌ 输出不匹配")
        
        return [types.TextContent(type="text", text="\n".join(lines))]

    async def _handle_compare_outputs(self, args: Dict[str, Any]) -> List[types.TextContent]:
        """处理输出比较请求。"""
        actual = args.get("actual", "")
        expected = args.get("expected", "")
        ignore_ws = args.get("ignore_whitespace", True)
        ignore_case = args.get("ignore_case", False)
        
        result = self.runner.compare_outputs(actual, expected, ignore_ws, ignore_case)
        lines = ["## 输出比较结果", ""]
        lines.append("✅ 输出完全匹配！" if result['match'] else "❌ 输出不匹配")
        
        if not result['match'] and result['differences']:
            lines.append("")
            lines.append("差异详情:")
            for diff in result['differences'][:5]:
                lines.append(f"第{diff['line']}行: 实际='{diff['actual']}', 预期='{diff['expected']}'")
        
        return [types.TextContent(type="text", text="\n".join(lines))]

    async def run(self) -> None:
        """启动MCP服务器。"""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main() -> None:
    """主入口函数。"""
    server = OIAssistantServer()
    print("OI助手MCP服务器启动中...", file=sys.stderr)
    print(f"临时目录: {server.security.temp_dir}", file=sys.stderr)
    print(f"MinGW目录: {server.security.mingw_dir}", file=sys.stderr)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()