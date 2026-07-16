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
        # 复用 HTTP 连接，减少 TCP 握手开销
        self._session = requests.Session() if (requests and self.enabled) else None
        if self._session:
            adapter = requests.adapters.HTTPAdapter(pool_connections=5, pool_maxsize=10)
            self._session.mount('https://', adapter)

    def _make_key(self, key):
        safe_key = hashlib.md5(key.encode('utf-8')).hexdigest()
        return f'cache/{safe_key}.json'

    def _headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

    def get(self, key):
        if not self.enabled or not self._session:
            return None
        try:
            pathname = self._make_key(key)
            blob_url = self._url_cache.get(key)
            if blob_url:
                resp = self._session.get(blob_url, timeout=5)
                if resp.status_code == 200:
                    obj = resp.json()
                    if obj.get('expire_at') and time.time() > obj['expire_at']:
                        self.delete(key)
                        return None
                    return obj.get('value')
            head_url = f'{self.BASE_URL}?url={pathname}'
            resp = self._session.get(head_url, headers=self._headers(), timeout=5)
            if resp.status_code == 404:
                return None
            if resp.status_code == 200:
                blob_info = resp.json()
                download_url = blob_info.get('url') or blob_info.get('downloadUrl')
                if download_url:
                    self._url_cache[key] = download_url
                    data_resp = self._session.get(download_url, timeout=5)
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
        if not self.enabled or not self._session:
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
            resp = self._session.put(put_url, data=data, headers=headers, timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                if result.get('url'):
                    self._url_cache[key] = result['url']
        except:
            pass

    def delete(self, key):
        if not self.enabled or not self._session:
            return
        try:
            pathname = self._make_key(key)
            delete_url = f'{self.BASE_URL}/delete'
            resp = self._session.post(
                delete_url,
                json={'urls': [pathname]},
                headers=self._headers(),
                timeout=5
            )
            if key in self._url_cache:
                del self._url_cache[key]
        except:
            pass


class UpstashRedisCache:
    """基于 Upstash Redis (Vercel KV) 的缓存实现。

    使用 REST API 访问，无需额外 Redis 客户端依赖。
    """

    def __init__(self, enabled=True):
        self.token = os.getenv('KV_REST_API_TOKEN')
        self.base_url = os.getenv('KV_REST_API_URL')
        self.enabled = enabled and bool(self.token) and bool(self.base_url) and requests is not None
        self._session = requests.Session() if (requests and self.enabled) else None
        if self._session:
            adapter = requests.adapters.HTTPAdapter(pool_connections=5, pool_maxsize=10)
            self._session.mount('https://', adapter)

    def _headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

    def get(self, key):
        if not self.enabled or not self._session:
            return None
        try:
            url = f'{self.base_url}/get/{key}'
            resp = self._session.get(url, headers=self._headers(), timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('result') is not None:
                    return data['result']
            return None
        except:
            pass
        return None

    def set(self, key, value, ttl=3600):
        if not self.enabled or not self._session:
            return
        try:
            url = f'{self.base_url}/set/{key}'
            resp = self._session.post(url, headers=self._headers(), json={'value': value, 'ex': ttl}, timeout=5)
            if resp.status_code != 200:
                pass
        except:
            pass

    def delete(self, key):
        if not self.enabled or not self._session:
            return
        try:
            url = f'{self.base_url}/del/{key}'
            self._session.post(url, headers=self._headers(), timeout=3)
        except:
            pass


class TwoLevelCache:
    def __init__(self, lru_capacity=500, lru_ttl=300, blob_enabled=True, blob_ttl=3600):
        self.l1 = LRUCache(capacity=lru_capacity, ttl=lru_ttl)
        self.l2 = VercelBlobCache(enabled=blob_enabled)
        self.blob_ttl = blob_ttl
        # L1 TTL <= 10s 时跳过 Blob（网络延迟远超缓存收益）
        self._skip_blob = (lru_ttl <= 10)

    def get(self, key):
        value = self.l1.get(key)
        if value is not None:
            return value
        if self._skip_blob:
            return None
        value = self.l2.get(key)
        if value is not None:
            self.l1.set(key, value)
            return value
        return None

    def set(self, key, value, l1_ttl=None, l2_ttl=None):
        self.l1.set(key, value, ttl=l1_ttl)
        if not self._skip_blob:
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


static_page_cache = UpstashRedisCache()


def get_static_page(key):
    return static_page_cache.get(key)


def set_static_page(key, content, ttl=300):
    static_page_cache.set(key, content, ttl=ttl)


def delete_static_page(key):
    static_page_cache.delete(key)


def invalidate_all_static_pages():
    try:
        import requests
        token = os.getenv('KV_REST_API_TOKEN')
        base_url = os.getenv('KV_REST_API_URL')
        if token and base_url and requests:
            resp = requests.post(
                f'{base_url}/flushall',
                headers={'Authorization': f'Bearer {token}'},
                timeout=5
            )
    except:
        pass
