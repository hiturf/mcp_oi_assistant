#!/usr/bin/env python3
"""OI助手MCP服务器启动入口。"""

import asyncio
import os
import sys
from logging import getLogger

from mcp_server import OIAssistantServer

logger = getLogger(__name__)


def main() -> None:
    """主函数：检查目录并启动服务器。"""
    print("🚀 OI助手MCP服务器 v1.0")
    print("=" * 50)

    required_dirs = ['tmp', 'mingw64/bin']
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            print(f"⚠️  警告: 目录 '{dir_path}' 不存在")
            if dir_path == 'mingw64/bin':
                print("请确保MinGW已安装并放置在mingw64目录中")

    server = OIAssistantServer()
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    except RuntimeError as e:
        print(f"❌ 服务器运行时错误: {e}", file=sys.stderr)
        logger.exception("服务器运行时错误")
        sys.exit(1)
    except OSError as e:
        print(f"❌ 系统错误: {e}", file=sys.stderr)
        logger.exception("系统错误")
        sys.exit(1)


if __name__ == "__main__":
    main()
