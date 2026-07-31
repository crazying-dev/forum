import time
import hashlib
import requests
from typing import Dict, Optional


class BtFirewallBlackIp:
	def __init__(self, panel_url: str, api_sk: str):
		"""
        初始化宝塔API客户端，仅用于添加IP黑名单
        :param panel_url: 宝塔面板地址，如 http://127.0.0.1:8888
        :param api_sk: 面板API接口密钥
        """
		self.panel_url = panel_url.rstrip("/")
		self.api_sk = api_sk
		self.session = requests.Session()
	
	def _generate_sign(self) -> Dict:
		"""生成宝塔API签名参数"""
		request_time = int(time.time())
		md5_sk = hashlib.md5(self.api_sk.encode("utf-8")).hexdigest()
		token_raw = f"{request_time}{md5_sk}"
		request_token = hashlib.md5(token_raw.encode("utf-8")).hexdigest()
		return {
			"request_time": request_time,
			"request_token": request_token
		}
	
	def _request(self, uri: str, data: Optional[Dict] = None) -> Dict:
		"""通用POST请求封装"""
		sign_params = self._generate_sign()
		post_data = {**sign_params}
		if data:
			post_data.update(data)
		
		full_url = f"{self.panel_url}{uri}"
		resp = self.session.post(url=full_url, data=post_data, timeout=10)
		resp.raise_for_status()
		return resp.json()
	
	def add_black_ip(self, ip: str, remark: str = "API自动封禁") -> Dict:
		"""
        将IP加入宝塔防火墙黑名单
        :param ip: 单个IPv4地址，例：111.222.33.44
        :param remark: 封禁备注信息
        :return: 宝塔接口返回原始JSON
        """
		params = {
			"ip": ip,
			"ps": remark
		}
		return self._request("/firewall?action=add_black_ip", data=params)


# 使用示例
if __name__ == "__main__":
	# 配置你的面板信息
	PANEL_URL = "http://127.0.0.1:26460"
	API_SK = "dnvKff1WgmlB4JpngHhuz3tQXryWreXq"
	
	bt = BtFirewallBlackIp(PANEL_URL, API_SK)
	# 封禁指定IP
	result = bt.add_black_ip("123.45.67.89", "恶意扫描攻击")
	print("封禁接口返回：", result)
