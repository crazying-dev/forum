import time
import json
import os
import hashlib
from collections import OrderedDict
from threading import Lock

try:
    import requests
except ImportError:
    requests = None


class LRUCache:
    def __init__(self, capacity=500, ttl=300):
        self.capacity = capacity
        self.ttl = ttl
        self.cache = OrderedDict()
        self.lock = Lock()

    def get(self, key):
        with self.lock:
            if key not in self.cache:
                return None
            value, expire_at = self.cache[key]
            if expire_at and time.time() > expire_at:
                del self.cache[key]
                return None
            self.cache.move_to_end(key)
            return value

    def set(self, key, value, ttl=None):
        with self.lock:
            expire_at = time.time() + (ttl if ttl is not None else self.ttl)
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = (value, expire_at)
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

    def delete(self, key):
        with self.lock:
            if key in self.cache:
                del self.cache[key]

    def clear(self):
        with self.lock:
            self.cache.clear()

    def has(self, key):
        with self.lock:
            if key not in self.cache:
                return False
            _, expire_at = self.cache[key]
            if expire_at and time.time() > expire_at:
                del self.cache[key]
                return False
            return True


class VercelBlobCache:
    BASE_URL = 'https://blob.vercel-storage.com'

    def __init__(self, enabled=True):
        self.token = os.getenv('BLOB_READ_WRITE_TOKEN')
        self.enabled = enabled and bool(self.token) and requests is not None
        self._url_cache = {}

    def _make_key(self, key):
        safe_key = hashlib.md5(key.encode('utf-8')).hexdigest()
        return f'cache/{safe_key}.json'

    def _headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

    def get(self, key):
        if not self.enabled:
            return None
        try:
            pathname = self._make_key(key)
            blob_url = self._url_cache.get(key)
            if blob_url:
                resp = requests.get(blob_url, timeout=5)
                if resp.status_code == 200:
                    obj = resp.json()
                    if obj.get('expire_at') and time.time() > obj['expire_at']:
                        self.delete(key)
                        return None
                    return obj.get('value')
            head_url = f'{self.BASE_URL}?url={pathname}'
            resp = requests.get(head_url, headers=self._headers(), timeout=5)
            if resp.status_code == 404:
                return None
            if resp.status_code == 200:
                blob_info = resp.json()
                download_url = blob_info.get('url') or blob_info.get('downloadUrl')
                if download_url:
                    self._url_cache[key] = download_url
                    data_resp = requests.get(download_url, timeout=5)
                    if data_resp.status_code == 200:
                        obj = data_resp.json()
                        if obj.get('expire_at') and time.time() > obj['expire_at']:
                            self.delete(key)
                            return None
                        return obj.get('value')
        except:
            pass
        return None

    def set(self, key, value, ttl=3600):
        if not self.enabled:
            return
        try:
            pathname = self._make_key(key)
            data = json.dumps({
                'value': value,
                'expire_at': time.time() + ttl,
                'created_at': time.time()
            }).encode('utf-8')
            put_url = f'{self.BASE_URL}/{pathname}'
            headers = self._headers()
            headers['x-content-type'] = 'application/json'
            resp = requests.put(put_url, data=data, headers=headers, timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                if result.get('url'):
                    self._url_cache[key] = result['url']
        except:
            pass

    def delete(self, key):
        if not self.enabled:
            return
        try:
            pathname = self._make_key(key)
            delete_url = f'{self.BASE_URL}/delete'
            resp = requests.post(
                delete_url,
                json={'urls': [pathname]},
                headers=self._headers(),
                timeout=5
            )
            if key in self._url_cache:
                del self._url_cache[key]
        except:
            pass


class TwoLevelCache:
    def __init__(self, lru_capacity=500, lru_ttl=300, blob_enabled=True, blob_ttl=3600):
        self.l1 = LRUCache(capacity=lru_capacity, ttl=lru_ttl)
        self.l2 = VercelBlobCache(enabled=blob_enabled)
        self.blob_ttl = blob_ttl

    def get(self, key):
        value = self.l1.get(key)
        if value is not None:
            return value
        value = self.l2.get(key)
        if value is not None:
            self.l1.set(key, value)
            return value
        return None

    def set(self, key, value, l1_ttl=None, l2_ttl=None):
        self.l1.set(key, value, ttl=l1_ttl)
        self.l2.set(key, value, ttl=l2_ttl if l2_ttl is not None else self.blob_ttl)

    def delete(self, key):
        self.l1.delete(key)
        self.l2.delete(key)

    def clear(self):
        self.l1.clear()


post_list_cache = TwoLevelCache(lru_capacity=100, lru_ttl=30, blob_ttl=120)
post_detail_cache = TwoLevelCache(lru_capacity=200, lru_ttl=60, blob_ttl=300)
user_info_cache = TwoLevelCache(lru_capacity=200, lru_ttl=300, blob_ttl=1800)
world_cache = TwoLevelCache(lru_capacity=50, lru_ttl=2, blob_ttl=10)
search_cache = TwoLevelCache(lru_capacity=100, lru_ttl=120, blob_ttl=600)
comment_cache = TwoLevelCache(lru_capacity=200, lru_ttl=60, blob_ttl=300)


def invalidate_post_cache(post_id=None):
    if post_id:
        post_detail_cache.delete(f'post:{post_id}')
        comment_cache.delete(f'comments:{post_id}')
    for i in range(1, 10):
        post_list_cache.delete(f'posts:page:{i}:size:20')
        post_list_cache.delete(f'posts:page:{i}:size:20:cat:general')
        post_list_cache.delete(f'posts:page:{i}:size:20:cat:anime')
        post_list_cache.delete(f'posts:page:{i}:size:20:cat:game')
    for i in range(1, 5):
        post_list_cache.delete(f'random:{i}')


def invalidate_user_cache(user_id):
    user_info_cache.delete(f'user:{user_id}')
    for i in range(1, 10):
        user_info_cache.delete(f'user_posts:{user_id}:page:{i}:size:20')


def invalidate_world_cache():
    world_cache.delete('world:all')
