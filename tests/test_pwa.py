"""PWA 端点验证：manifest / sw.js / 图标路由的状态码与 MIME，以及首页注册代码。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main.main import app


def main() -> int:
	client = app.test_client()
	checks = [
		('/manifest.json', 'application/manifest+json', 200),
		('/sw.js', 'application/javascript', 200),
		('/static/pwa/icon-192.png', 'image/png', 200),
		('/static/pwa/icon-512.png', 'image/png', 200),
		('/static/pwa/maskable-512.png', 'image/png', 200),
		('/static/pwa/apple-touch-icon.png', 'image/png', 200),
	]
	ok = True
	for url, expected_ct, expected_status in checks:
		resp = client.get(url)
		ct = resp.headers.get('Content-Type', '')
		status = resp.status_code
		match = status == expected_status and ct.startswith(expected_ct)
		print(f"{'PASS' if match else 'FAIL'} {url} -> {status} {ct}")
		ok = ok and match

	resp = client.get('/sw.js')
	cc = resp.headers.get('Cache-Control', '')
	print(f"{'PASS' if cc == 'no-cache' else 'FAIL'} /sw.js Cache-Control -> {cc!r}")
	ok = ok and (cc == 'no-cache')

	resp = client.get('/')
	html = resp.get_data(as_text=True)
	for needle in ('rel="manifest"', 'serviceWorker.register', 'apple-touch-icon'):
		found = needle in html
		print(f"{'PASS' if found else 'FAIL'} index contains {needle!r}")
		ok = ok and found

	return 0 if ok else 1


if __name__ == '__main__':
	sys.exit(main())
