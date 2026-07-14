#!/usr/bin/env python3
import json
import hashlib
import time
import requests


class AdminAPIClient:

    def __init__(self, base_url, admin_id, admin_token):
        self.base_url = base_url
        if not self.base_url.startswith('http'):
            self.base_url = 'https://' + self.base_url
        self.admin_id = admin_id
        self.admin_token = admin_token

    def _generate_signature(self, send_time):
        raw = f"{self.admin_id}{self.admin_token}{send_time}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def _generate_time_token(self, send_time):
        raw = f"{self.admin_id}{send_time}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    def _generate_time_password(self):
        from datetime import datetime
        now = datetime.now()
        return f"{now.year}-{now.month:02d}-{now.day:02d}-{now.hour:02d}"

    def call(self, action, **args):
        send_time = str(time.time())
        signature = self._generate_signature(send_time)
        time_token = self._generate_time_token(send_time)
        password = self._generate_time_password()
        run_msg = json.dumps({'action': action, 'args': args})

        data = {
            'password': password,
            'AdminID': self.admin_id,
            'AdminToken': self.admin_token,
            'TimeToken': time_token,
            'SendTime': send_time,
            'RunMessage': run_msg,
            'adminId': self.admin_id,
            'signature': signature,
            'sendTime': send_time,
            'runMessage': run_msg,
        }

        try:
            resp = requests.post(self.base_url, json=data, timeout=30)
            result = resp.json()
            if result.get('success'):
                return result.get('data')
            else:
                print(f"[API错误] {result.get('message', '未知错误')}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"[网络错误] {e}")
            if hasattr(e, 'response') and e.response:
                try:
                    err_data = e.response.json()
                    print(f"[服务器响应] {err_data}")
                except:
                    print(f"[服务器响应] {e.response.text[:300]}")
            return None

    def list_reports(self, status=None):
        return self.call('list_reports', status=status)

    def resolve_report(self, report_id):
        return self.call('resolve_report', report_id=report_id)

    def list_users(self):
        return self.call('list_users')

    def find_user(self, key, value):
        return self.call('find_user', key=key, value=value)

    def find_user_smart(self, identifier):
        return self.call('find_user_smart', identifier=identifier)

    def update_user(self, user_id, key, value):
        return self.call('update_user', user_id=user_id, key=key, value=value)

    def ban_user(self, user_id):
        return self.call('ban_user', user_id=user_id)

    def unban_user(self, user_id):
        return self.call('unban_user', user_id=user_id)

    def get_post_detail(self, post_id):
        return self.call('get_post_detail', post_id=post_id)

    def delete_post(self, post_id):
        return self.call('delete_post', post_id=post_id)

    def get_post_comments(self, post_id):
        return self.call('get_post_comments', post_id=post_id)

    def delete_comment(self, comment_id):
        return self.call('delete_comment', comment_id=comment_id)

    def get_stats(self):
        return self.call('get_stats')

    def ping(self):
        try:
            resp = requests.get(f"{self.base_url}/ping", timeout=5)
            return resp.json()
        except Exception:
            return None