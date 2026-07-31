# -*- coding: utf-8 -*-
"""宝塔面板 API 客户端。

签名规则（来自官方文档）：
  md5_sk = md5(api_sk)
  request_token = md5(str(request_time) + md5_sk)
所有接口使用 POST + Cookie (requests.Session 自动处理)。
宝塔自签名证书需跳过 SSL 验证。
"""
import time
import hashlib
import requests
import urllib3
from typing import Dict, Optional

# 禁用 SSL 警告（宝塔自签名证书）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BtFirewallBlackIp:
	def __init__(self, panel_url: str, api_sk: str):
		"""初始化宝塔 API 客户端。

        :param panel_url: 宝塔面板地址，如 https://127.0.0.1:26460
        :param api_sk: 面板 API 接口密钥
        """
		self.panel_url = panel_url.rstrip("/")
		self.api_sk = api_sk
		self.session = requests.Session()
		self.session.verify = False  # 宝塔自签名证书
	
	def _generate_sign(self) -> Dict:
		"""生成宝塔 API 签名参数。"""
		request_time = int(time.time())
		md5_sk = hashlib.md5(self.api_sk.encode("utf-8")).hexdigest()
		token_raw = f"{request_time}{md5_sk}"
		request_token = hashlib.md5(token_raw.encode("utf-8")).hexdigest()
		return {
			"request_time": request_time,
			"request_token": request_token
		}
	
	def _request(self, uri: str, data: Optional[Dict] = None) -> Dict:
		"""通用 POST 请求（按官方文档要求使用 POST + Cookie）。"""
		sign_params = self._generate_sign()
		post_data = {**sign_params}
		if data:
			post_data.update(data)
		
		full_url = f"{self.panel_url}{uri}"
		resp = self.session.post(url=full_url, data=post_data, timeout=10)
		resp.raise_for_status()
		return resp.json()
	
	def add_black_ip(self, ip: str, remark: str = "API自动封禁") -> Dict:
		"""将 IP 加入宝塔防火墙黑名单。

        :param ip: IPv4 地址，例：111.222.33.44
        :param remark: 封禁备注
        :return: 宝塔接口返回的 JSON
        """
		return self._request("/firewall?action=add_black_ip", data={
			"ip": ip,
			"ps": remark
		})


# 使用示例
if __name__ == "__main__":
	bt = BtFirewallBlackIp("https://127.0.0.1:26460", "your_api_sk")
	result = bt.add_black_ip("123.45.67.89", "恶意扫描攻击")
	print("封禁接口返回：", result)
