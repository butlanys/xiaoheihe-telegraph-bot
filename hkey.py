#!/usr/bin/env python3
"""小黑盒 API hkey 签名生成"""

import hashlib
import math
import time
import struct

DICT = 'JKMNPQRTX1234OABCDFG56789H'  # 31 chars


def md5_digest(data: str) -> bytes:
    """MD5 hash"""
    return hashlib.md5(data.encode('utf-8')).digest()


def md5_hex(data: str) -> str:
    """MD5 hex string"""
    return hashlib.md5(data.encode('utf-8')).hexdigest()


def gen_nonce(length: int = 32) -> str:
    """Generate random nonce string"""
    import random
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    return ''.join(random.choice(chars) for _ in range(length))


def _checksum(data):
    """Calculate checksum for 4 bytes (reproduces JS array reduce behavior)"""
    def _convert_byte(v):
        return (0xff & ((v << 1) ^ 0x1b)) if (v & 0x80) else (v << 1)
    def c3(v):
        return _convert_byte(v) ^ v
    def c2(v):
        return c3(_convert_byte(v))
    def c1(v):
        return c2(c3(_convert_byte(v)))
    def c0(v):
        return c1(v) ^ c2(v) ^ c3(v)

    arr = [
        c0(data[0]) ^ c1(data[1]) ^ c2(data[2]) ^ c3(data[3]),
        c3(data[0]) ^ c0(data[1]) ^ c1(data[2]) ^ c2(data[3]),
        c2(data[0]) ^ c3(data[1]) ^ c0(data[2]) ^ c1(data[3]),
        c1(data[0]) ^ c2(data[1]) ^ c3(data[2]) ^ c0(data[3]),
    ]
    return sum(arr) % 100


def calculate_hkey(url: str, timestamp: int = 0, nonce: str = '') -> str:
    """
    计算小黑盒 API 的 hkey 签名
    
    返回: (hkey_value, _time, nonce) 元组
    """
    if not timestamp:
        timestamp = int(time.time())
    if not nonce:
        nonce = md5_hex(str(time.time())).upper()
    
    # 提取 pathname
    from urllib.parse import urlparse
    pathname = urlparse(url).path
    # Normalize: /a/b/c/
    u = '/' + '/'.join([p for p in pathname.split('/') if p]) + '/'
    
    ts = timestamp + 1
    
    # nonceHash = MD5 of (nonce + dict) filtered to digits only
    nonce_digits = ''.join(c for c in (nonce + DICT) if c.isdigit())
    nonce_hash = md5_hex(nonce_digits).lower()
    
    # rnd = MD5(ts + u + nonceHash), then only digits, first 9 chars
    rnd_raw = md5_hex(str(ts) + u + nonce_hash)
    rnd = ''.join(c for c in rnd_raw if c.isdigit())[:9].ljust(9, '0')
    
    # Generate 5-char key from rnd
    key = ''
    c_val = int(rnd)
    for _ in range(5):
        idx = c_val % len(DICT)
        c_val = c_val // len(DICT)
        key += DICT[idx]
    
    # Checksum over last 4 chars
    suffix = _checksum([ord(c) for c in key[-4:]])
    
    hkey = f"{key}{suffix:02d}"
    return hkey, timestamp, nonce


def sign_url(url: str) -> str:
    """给 URL 加上 hkey/_time/nonce 参数"""
    hkey, t, nonce = calculate_hkey(url)
    from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs['hkey'] = [hkey]
    qs['_time'] = [str(t)]
    qs['nonce'] = [nonce]
    new_qs = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=new_qs))


if __name__ == '__main__':
    url = 'https://api.xiaoheihe.cn/bbs/app/link/tree?link_id=3fd472330d18'
    hkey, t, nonce = calculate_hkey(url)
    print(f'hkey={hkey}')
    print(f'_time={t}')
    print(f'nonce={nonce}')
    print()
    print(sign_url(url))
