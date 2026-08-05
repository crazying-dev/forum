"""验证 SW_VERSION 环境变量接管：设置后 /sw.js 应返回对应版本号。

注意：config 在 import 时读取环境变量，因此本脚本必须独立进程运行。
"""

import os
import sys
from pathlib import Path

os.environ['SW_VERSION'] = '9.9.9'  # 必须在 import main.main 之前设置

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main.main import app


def main() -> int:
	resp = app.test_client().get('/sw.js')
	body = resp.get_data(as_text=True)
	ok = resp.status_code == 200 and "const SW_VERSION = '9.9.9';" in body
	print(f"{'PASS' if ok else 'FAIL'} /sw.js 环境变量版本号（9.9.9）")
	print(f"   -> {resp.status_code} {resp.headers.get('Content-Type')}")
	return 0 if ok else 1


if __name__ == '__main__':
	sys.exit(main())
