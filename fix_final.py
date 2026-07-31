with open('app/security.py', 'r', encoding='utf-8') as f:
    c = f.read()

old = """def detect_malicious():
	"""检测当前请求是否为恶意访问。

	在 before_request 中调用。如果检测到恶意行为，
	记录 IP 并返回一个 404/403 响应阻断请求。

	Returns:

	client_ip = request.remote_addr or 'unknown'"""

new = """def detect_malicious():
	"""检测当前请求是否为恶意访问。

	在 before_request 中调用。如果检测到恶意行为，
	记录 IP 并返回一个 404/403 响应阻断请求。
	"""
	_load_blacklist()
	client_ip = request.remote_addr or 'unknown'"""

c = c.replace(old, new)

with open('app/security.py', 'w', encoding='utf-8') as f:
    f.write(c)
print('OK')