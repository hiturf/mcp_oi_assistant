"""MCP服务器主模块，提供OI助手工具。"""

import asyncio
import sys
import time
from typing import Any, Dict, List
from logging import getLogger
from pathlib import Path  # 修复：添加Path导入

# MCP imports
from mcp import types
from mcp.server import Server
import mcp.server.stdio

from runner import CodeRunner
from security import SecurityManager

logger = getLogger(__name__)


class OIAssistantServer:
    """MCP服务器，提供代码编译、运行、调试和测试工具。"""

    def __init__(self) -> None:
        """初始化服务器、运行器和安全管理器。"""
        self.runner = CodeRunner()
        self.security = SecurityManager()
        self.server = Server("oi-assistant")
        self.setup_handlers()
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def setup_handlers(self) -> None:
        """注册MCP工具处理器。"""

        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            return [
                # 🎯 核心命令（每天必用）
                types.Tool(
                    name="g++",
                    description="🎯 编译C++代码 - 最常用的编译命令",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "source_file": {
                                "type": "string",
                                "description": "源文件路径（如 solve.cpp）"
                            },
                            "output_file": {
                                "type": "string",
                                "description": "输出文件名（如 solve）"
                            },
                            "extra_flags": {
                                "type": "string",
                                "description": "额外编译选项（如 -O2 -Wall）",
                                "default": ""
                            }
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
                            "source_file": {
                                "type": "string",
                                "description": "源文件路径（如 main.c）"
                            },
                            "output_file": {
                                "type": "string",
                                "description": "输出文件名（如 main）"
                            },
                            "extra_flags": {
                                "type": "string",
                                "description": "额外编译选项",
                                "default": ""
                            }
                        },
                        "required": ["source_file", "output_file"]
                    }
                ),
                
                # 🔧 辅助命令（查错、调试、管理）
                types.Tool(
                    name="gdb",
                    description="🔧 调试程序 - 单步执行、查看变量、设置断点",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "executable": {
                                "type": "string",
                                "description": "要调试的可执行文件"
                            },
                            "commands": {
                                "type": "string",
                                "description": "GDB命令（如 'break main\nrun\nprint x\nquit'）",
                                "default": "break main\nrun\nbacktrace\nquit"
                            }
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
                            "target": {
                                "type": "string",
                                "description": "make目标（如 all, clean）",
                                "default": "all"
                            },
                            "makefile_dir": {
                                "type": "string",
                                "description": "Makefile所在目录",
                                "default": "."
                            },
                            "extra_args": {
                                "type": "string",
                                "description": "额外参数",
                                "default": ""
                            }
                        }
                    }
                ),
                types.Tool(
                    name="ld",
                    description="🔧 链接器 - 处理链接错误时使用",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "object_files": {
                                "type": "string",
                                "description": "目标文件列表（空格分隔）"
                            },
                            "output_file": {
                                "type": "string",
                                "description": "输出文件名"
                            },
                            "library_paths": {
                                "type": "string",
                                "description": "库路径（如 -L/path/to/lib）",
                                "default": ""
                            },
                            "libraries": {
                                "type": "string",
                                "description": "链接的库（如 -lm -lpthread）",
                                "default": ""
                            }
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
                            "source_file": {
                                "type": "string",
                                "description": "汇编源文件（.s或.asm）"
                            },
                            "output_file": {
                                "type": "string",
                                "description": "输出目标文件（.o）",
                                "default": ""
                            }
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
                            "file": {
                                "type": "string",
                                "description": "要分析的文件（可执行文件或目标文件）"
                            },
                            "options": {
                                "type": "string",
                                "description": "objdump选项（如 -d 反汇编，-t 查看符号表）",
                                "default": "-d"
                            }
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
                            "file": {
                                "type": "string",
                                "description": "要分析的文件（.o或可执行文件）"
                            },
                            "options": {
                                "type": "string",
                                "description": "nm选项（如 -C 解码C++符号）",
                                "default": "-C"
                            }
                        },
                        "required": ["file"]
                    }
                ),
                
                # 保留原有的工具
                types.Tool(
                    name="compile_and_run",
                    description="编译并运行C++代码（集成版）",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "C++源代码"},
                            "input": {"type": "string", "description": "输入数据"},
                            "expected_output": {"type": "string", "description": "预期输出（可选）"},
                            "filename": {"type": "string", "description": "文件名（可选）"},
                            "time_limit": {"type": "integer", "description": "时间限制（毫秒）"},
                            "memory_limit": {"type": "integer", "description": "内存限制（MB）"}
                        },
                        "required": ["code", "input"]
                    }
                ),
                types.Tool(
                    name="debug_with_gdb",
                    description="使用GDB调试C++程序（集成版）",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "C++源代码"},
                            "gdb_script": {"type": "string", "description": "GDB调试脚本（可选）"}
                        },
                        "required": ["code"]
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
                            "ignore_whitespace": {"type": "boolean", "description": "是否忽略空白字符", "default": True},
                            "ignore_case": {"type": "boolean", "description": "是否忽略大小写", "default": False}
                        },
                        "required": ["actual", "expected"]
                    }
                ),
                types.Tool(
                    name="read_test_case",
                    description="读取测试用例文件",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "test_case_id": {"type": "string", "description": "测试用例ID"}
                        },
                        "required": ["test_case_id"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str,
            arguments: Dict[str, Any]
        ) -> List[types.TextContent]:
            """分发工具调用请求。"""
            session_id = f"session_{int(time.time())}_{hash(str(arguments)) % 10000}"
            self.sessions[session_id] = {
                "start_time": time.time(),
                "tool": name,
                "arguments": arguments
            }
            try:
                # 核心命令
                if name == "g++":
                    return await self._handle_gpp(arguments)
                if name == "gcc":
                    return await self._handle_gcc(arguments)
                
                # 辅助命令
                if name == "gdb":
                    return await self._handle_gdb_command(arguments)
                if name == "make":
                    return await self._handle_make(arguments)
                if name == "ld":
                    return await self._handle_ld(arguments)
                if name == "as":
                    return await self._handle_as(arguments)
                if name == "objdump":
                    return await self._handle_objdump(arguments)
                if name == "nm":
                    return await self._handle_nm(arguments)
                
                # 原有的工具
                if name == "compile_and_run":
                    return await self._handle_compile_and_run(arguments, session_id)
                if name == "debug_with_gdb":
                    return await self._handle_debug_with_gdb(arguments, session_id)
                if name == "compare_outputs":
                    return await self._handle_compare_outputs(arguments)
                if name == "read_test_case":
                    return await self._handle_read_test_case(arguments)
                
                return [types.TextContent(type="text", text=f"未知工具: {name}")]
            except ValueError as e:
                logger.exception("参数错误")
                return [types.TextContent(type="text", text=f"参数错误: {str(e)}")]
            except OSError as e:
                logger.exception("系统错误")
                return [types.TextContent(type="text", text=f"系统错误: {str(e)}")]
            except Exception as e:
                logger.exception("未知错误")
                return [types.TextContent(type="text", text=f"工具执行错误: {str(e)}")]
            finally:
                self.sessions.pop(session_id, None)

    async def _handle_gpp(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """处理g++编译命令。"""
        source_file = arguments.get("source_file", "")
        output_file = arguments.get("output_file", "")
        extra_flags = arguments.get("extra_flags", "")

        # 构建编译命令
        cmd = f"g++ {source_file} -o {output_file}"
        if extra_flags:
            cmd += f" {extra_flags}"

        result_lines = [
            f"## g++ 编译命令",
            f"```bash",
            f"{cmd}",
            f"```",
            f""
        ]

        # 执行命令
        import subprocess
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )

            if result.returncode == 0:
                result_lines.append("✅ 编译成功")
                if result.stdout:
                    result_lines.extend(["输出:", "```", result.stdout, "```"])
            else:
                result_lines.append("❌ 编译失败")
                if result.stderr:
                    result_lines.extend(["错误信息:", "```", result.stderr, "```"])

            result_lines.append(f"返回码: {result.returncode}")

        except subprocess.TimeoutExpired:
            result_lines.append("❌ 编译超时")
        except Exception as e:
            result_lines.append(f"❌ 执行错误: {str(e)}")

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    async def _handle_gcc(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """处理gcc编译命令。"""
        source_file = arguments.get("source_file", "")
        output_file = arguments.get("output_file", "")
        extra_flags = arguments.get("extra_flags", "")

        cmd = f"gcc {source_file} -o {output_file}"
        if extra_flags:
            cmd += f" {extra_flags}"

        result_lines = [
            f"## gcc 编译命令",
            f"```bash",
            f"{cmd}",
            f"```",
            f""
        ]

        import subprocess
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )

            if result.returncode == 0:
                result_lines.append("✅ 编译成功")
                if result.stdout:
                    result_lines.extend(["输出:", "```", result.stdout, "```"])
            else:
                result_lines.append("❌ 编译失败")
                if result.stderr:
                    result_lines.extend(["错误信息:", "```", result.stderr, "```"])

            result_lines.append(f"返回码: {result.returncode}")

        except subprocess.TimeoutExpired:
            result_lines.append("❌ 编译超时")
        except Exception as e:
            result_lines.append(f"❌ 执行错误: {str(e)}")

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    async def _handle_gdb_command(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """处理gdb调试命令。"""
        executable = arguments.get("executable", "")
        commands = arguments.get("commands", "break main\nrun\nbacktrace\nquit")

        # 创建临时GDB脚本
        script_file = self.security.get_secure_temp_path("gdb").with_suffix('.gdb')
        script_file.write_text(commands, encoding='utf-8')

        cmd = f"gdb -x {script_file} {executable} --batch"

        result_lines = [
            f"## GDB 调试",
            f"可执行文件: {executable}",
            f"调试脚本:",
            f"```gdb",
            f"{commands}",
            f"```",
            f""
        ]

        import subprocess
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=60,  # 调试可能耗时较长
                check=False
            )

            if result.stdout:
                result_lines.extend(["调试输出:", "```", result.stdout, "```"])
            if result.stderr:
                result_lines.extend(["错误信息:", "```", result.stderr, "```"])

        except subprocess.TimeoutExpired:
            result_lines.append("❌ 调试超时")
        except Exception as e:
            result_lines.append(f"❌ 执行错误: {str(e)}")
        finally:
            # 清理临时脚本
            if script_file.exists():
                script_file.unlink()

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    async def _handle_make(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """处理make命令。"""
        target = arguments.get("target", "all")
        makefile_dir = arguments.get("makefile_dir", ".")
        extra_args = arguments.get("extra_args", "")

        cmd = f"make -C {makefile_dir} {target}"
        if extra_args:
            cmd += f" {extra_args}"

        result_lines = [
            f"## make 自动化编译",
            f"```bash",
            f"{cmd}",
            f"```",
            f""
        ]

        import subprocess
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=60,
                cwd=makefile_dir,
                check=False
            )

            if result.returncode == 0:
                result_lines.append("✅ make执行成功")
            else:
                result_lines.append("❌ make执行失败")

            if result.stdout:
                result_lines.extend(["输出:", "```", result.stdout, "```"])
            if result.stderr:
                result_lines.extend(["错误信息:", "```", result.stderr, "```"])

            result_lines.append(f"返回码: {result.returncode}")

        except subprocess.TimeoutExpired:
            result_lines.append("❌ make执行超时")
        except Exception as e:
            result_lines.append(f"❌ 执行错误: {str(e)}")

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    async def _handle_ld(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """处理ld链接命令。"""
        object_files = arguments.get("object_files", "")
        output_file = arguments.get("output_file", "")
        library_paths = arguments.get("library_paths", "")
        libraries = arguments.get("libraries", "")

        cmd = f"ld {object_files} -o {output_file}"
        if library_paths:
            cmd += f" {library_paths}"
        if libraries:
            cmd += f" {libraries}"

        result_lines = [
            f"## ld 链接器",
            f"```bash",
            f"{cmd}",
            f"```",
            f""
        ]

        import subprocess
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )

            if result.returncode == 0:
                result_lines.append("✅ 链接成功")
            else:
                result_lines.append("❌ 链接失败")
                if result.stderr:
                    result_lines.extend(["错误信息:", "```", result.stderr, "```"])

        except subprocess.TimeoutExpired:
            result_lines.append("❌ 链接超时")
        except Exception as e:
            result_lines.append(f"❌ 执行错误: {str(e)}")

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    async def _handle_as(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """处理as汇编命令。"""
        source_file = arguments.get("source_file", "")
        output_file = arguments.get("output_file", "")

        if not output_file:
            # 修复：使用Path生成输出文件名
            output_file = str(Path(source_file).with_suffix('.o'))

        cmd = f"as {source_file} -o {output_file}"

        result_lines = [
            f"## as 汇编器",
            f"```bash",
            f"{cmd}",
            f"```",
            f""
        ]

        import subprocess
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )

            if result.returncode == 0:
                result_lines.append(f"✅ 汇编成功: {output_file}")
            else:
                result_lines.append("❌ 汇编失败")
                if result.stderr:
                    result_lines.extend(["错误信息:", "```", result.stderr, "```"])

        except subprocess.TimeoutExpired:
            result_lines.append("❌ 汇编超时")
        except Exception as e:
            result_lines.append(f"❌ 执行错误: {str(e)}")

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    async def _handle_objdump(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """处理objdump命令。"""
        file_path = arguments.get("file", "")
        options = arguments.get("options", "-d")

        cmd = f"objdump {options} {file_path}"

        result_lines = [
            f"## objdump 分析",
            f"文件: {file_path}",
            f"选项: {options}",
            f"```bash",
            f"{cmd}",
            f"```",
            f""
        ]

        import subprocess
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )

            if result.returncode == 0:
                if result.stdout:
                    # 输出可能很大，只显示部分
                    output = result.stdout
                    if len(output) > 10000:
                        output = output[:10000] + "\n... (输出被截断)"
                    result_lines.extend(["输出:", "```asm", output, "```"])
            else:
                result_lines.append("❌ 执行失败")
                if result.stderr:
                    result_lines.extend(["错误信息:", "```", result.stderr, "```"])

        except subprocess.TimeoutExpired:
            result_lines.append("❌ 执行超时")
        except Exception as e:
            result_lines.append(f"❌ 执行错误: {str(e)}")

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    async def _handle_nm(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """处理nm命令。"""
        file_path = arguments.get("file", "")
        options = arguments.get("options", "-C")

        cmd = f"nm {options} {file_path}"

        result_lines = [
            f"## nm 符号表",
            f"文件: {file_path}",
            f"选项: {options}",
            f"```bash",
            f"{cmd}",
            f"```",
            f""
        ]

        import subprocess
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )

            if result.returncode == 0:
                if result.stdout:
                    output = result.stdout
                    if len(output) > 5000:
                        output = output[:5000] + "\n... (输出被截断)"
                    result_lines.extend(["输出:", "```", output, "```"])
            else:
                result_lines.append("❌ 执行失败")
                if result.stderr:
                    result_lines.extend(["错误信息:", "```", result.stderr, "```"])

        except subprocess.TimeoutExpired:
            result_lines.append("❌ 执行超时")
        except Exception as e:
            result_lines.append(f"❌ 执行错误: {str(e)}")

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    # 原有的方法保持不变...
    async def _handle_compile_and_run(
        self,
        arguments: Dict[str, Any],
        session_id: str
    ) -> List[types.TextContent]:
        """处理编译运行请求。"""
        code = arguments.get("code", "")
        input_data = arguments.get("input", "")
        expected_output = arguments.get("expected_output", "")
        filename = arguments.get("filename", f"program_{session_id}")
        time_limit = arguments.get("time_limit")
        memory_limit = arguments.get("memory_limit")

        result_lines = [
            f"## 编译与运行报告",
            f"会话ID: {session_id}",
            f"文件名: {filename}",
            ""
        ]

        # 1. 编译
        result_lines.append("### 1. 编译阶段")
        compile_result = self.runner.compile_cpp(code, filename)
        if compile_result['success']:
            result_lines.append("✅ 编译成功")
            if compile_result['output']:
                result_lines.extend([
                    "编译输出:",
                    "```",
                    compile_result['output'],
                    "```"
                ])
        else:
            result_lines.append("❌ 编译失败")
            if compile_result['error']:
                result_lines.extend([
                    "错误信息:",
                    "```",
                    compile_result['error'],
                    "```"
                ])
            return [types.TextContent(
                type="text",
                text="\n".join(result_lines)
            )]

        # 2. 运行
        result_lines.append("")
        result_lines.append("### 2. 运行阶段")
        run_result = self.runner.run_with_input(
            compile_result['executable'],
            input_data,
            time_limit,
            memory_limit
        )
        result_lines.append(
            f"运行状态: {'✅ 成功' if run_result['success'] else '❌ 失败'}"
        )
        result_lines.append(f"时间消耗: {run_result['time_used']}ms")
        result_lines.append(f"内存使用: {run_result['memory_used']}KB")
        result_lines.append(f"退出代码: {run_result['exit_code']}")

        if run_result['output']:
            result_lines.extend([
                "",
                "程序输出:",
                "```",
                run_result['output'],
                "```"
            ])
        if run_result['error']:
            result_lines.extend([
                "",
                "错误输出:",
                "```",
                run_result['error'],
                "```"
            ])

        # 3. 输出比较
        if expected_output:
            result_lines.append("")
            result_lines.append("### 3. 输出比较")
            compare_result = self.runner.compare_outputs(
                run_result['output'] or "",
                expected_output
            )
            if compare_result['match']:
                result_lines.append("✅ 输出完全匹配！")
            else:
                result_lines.append("❌ 输出不匹配")
                result_lines.append(
                    f"实际行数: {compare_result['actual_line_count']}"
                )
                result_lines.append(
                    f"预期行数: {compare_result['expected_line_count']}"
                )
                for diff in compare_result['differences'][:5]:
                    result_lines.append(f"第{diff['line']}行:")
                    result_lines.append(f"  实际: {diff['actual']}")
                    result_lines.append(f"  预期: {diff['expected']}")
                if len(compare_result['differences']) > 5:
                    result_lines.append(
                        f"... 还有{len(compare_result['differences']) - 5}处差异未显示"
                    )

        # 4. 文件信息
        temp_dir = self.security.temp_dir
        result_lines.append("")
        result_lines.append("### 4. 文件信息")
        result_lines.append(f"源代码: `{temp_dir}/sources/{filename}.cpp`")
        result_lines.append(f"可执行文件: `{temp_dir}/execute/{filename}.exe`")
        result_lines.append(f"输入文件: `{temp_dir}/inputs/{session_id}.in`")
        result_lines.append(f"输出文件: `{temp_dir}/outputs/{session_id}.out`")

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    async def _handle_debug_with_gdb(
        self,
        arguments: Dict[str, Any],
        session_id: str
    ) -> List[types.TextContent]:
        """处理GDB调试请求。"""
        code = arguments.get("code", "")
        gdb_script = arguments.get("gdb_script")
        filename = f"debug_{session_id}"
        compile_result = self.runner.compile_cpp(code, filename)

        if not compile_result['success']:
            return [types.TextContent(
                type="text",
                text=f"编译失败，无法调试:\n{compile_result['error']}"
            )]

        gdb_result = self.runner.run_gdb(compile_result['executable'], gdb_script)
        result_lines = [
            f"## GDB调试报告",
            f"会话ID: {session_id}",
            ""
        ]

        if gdb_result['success']:
            result_lines.append("✅ 调试完成")
            if gdb_result['output']:
                result_lines.extend([
                    "**GDB输出**:",
                    "```",
                    gdb_result['output'],
                    "```"
                ])
        else:
            result_lines.append("❌ 调试失败")
            if gdb_result['error']:
                result_lines.extend([
                    "错误信息:",
                    "```",
                    gdb_result['error'],
                    "```"
                ])

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    async def _handle_compare_outputs(
        self,
        arguments: Dict[str, Any]
    ) -> List[types.TextContent]:
        """处理输出比较请求。"""
        actual = arguments.get("actual", "")
        expected = arguments.get("expected", "")
        ignore_whitespace = arguments.get("ignore_whitespace", True)
        ignore_case = arguments.get("ignore_case", False)

        compare_result = self.runner.compare_outputs(
            actual,
            expected,
            ignore_whitespace,
            ignore_case
        )
        result_lines = ["## 输出比较结果", ""]

        if compare_result['match']:
            result_lines.append("✅ 输出完全匹配！")
        else:
            result_lines.append("❌ 输出不匹配")
            result_lines.append(
                f"实际行数: {compare_result['actual_line_count']}"
            )
            result_lines.append(
                f"预期行数: {compare_result['expected_line_count']}"
            )
            result_lines.append("差异详情:")

            for diff in compare_result['differences'][:10]:
                result_lines.append(f"第{diff['line']}行:")
                result_lines.append(f"   实际: `{diff['actual']}`")
                result_lines.append(f"   预期: `{diff['expected']}`")

            if len(compare_result['differences']) > 10:
                result_lines.append(
                    f"... 还有{len(compare_result['differences']) - 10}处差异未显示"
                )

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

    async def _handle_read_test_case(
        self,
        arguments: Dict[str, Any]
    ) -> List[types.TextContent]:
        """读取测试用例文件（支持预定义和自定义文件）。"""
        test_case_id = arguments.get("test_case_id", "")
        safe_id = self.security.sanitize_filename(test_case_id)

        sample_cases = {
            "a+b": {
                "input": "3 5\n",
                "output": "8\n",
                "description": "A+B问题示例"
            },
            "fibonacci": {
                "input": "10\n",
                "output": "55\n",
                "description": "斐波那契数列第10项"
            }
        }

        if safe_id in sample_cases:
            case = sample_cases[safe_id]
            result_lines = [
                f"## 测试用例: {test_case_id}",
                f"描述: {case['description']}",
                "输入:",
                "```",
                case['input'],
                "```",
                "输出:",
                "```",
                case['output'],
                "```"
            ]
        else:
            test_file = self.security.temp_dir / "tests" / f"{safe_id}.txt"
            try:
                if test_file.exists():
                    content = test_file.read_text(encoding='utf-8')
                    result_lines = [
                        f"## 测试用例文件: {test_case_id}",
                        "```",
                        content,
                        "```"
                    ]
                else:
                    result_lines = [f"未找到测试用例: {test_case_id}"]
            except (IOError, OSError) as e:
                result_lines = [f"读取测试用例文件失败: {str(e)}"]

        return [types.TextContent(
            type="text",
            text="\n".join(result_lines)
        )]

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