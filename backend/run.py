"""video-strm 启动入口：python run.py（默认 127.0.0.1:8000）。"""

import os
import subprocess
import sys
from pathlib import Path


def main():
    project_root = Path(__file__).parent
    app_path = project_root / "app" / "main.py"
    if not app_path.exists():
        print(f"错误: 找不到应用入口文件 {app_path}")
        sys.exit(1)

    print("正在启动 video-strm ...")
    print("访问地址: http://127.0.0.1:8000")
    print("API文档: http://127.0.0.1:8000/docs")
    print("-" * 40)

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
    ]
    if os.environ.get("DEBUG", "").lower() in ("true", "1"):
        cmd.append("--reload")

    try:
        subprocess.run(cmd, cwd=str(project_root))
    except KeyboardInterrupt:
        print("\n服务已停止")
    except Exception as exc:
        print(f"启动失败: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
