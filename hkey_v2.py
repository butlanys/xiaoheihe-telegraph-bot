#!/usr/bin/env python3
"""
小黑盒 API hkey 签名生成（新版算法）
移植自 https://github.com/luckylca/xhhBackCrack 和 https://github.com/ljxme/heybox-robot
"""

import hashlib
import os
import time
import random
import string

KEY_STR = "AB45STUVWZEFGJ6CH01D237IXYPQRKLMN89"


def vm(n: int) -> int:
    """byte confusion function"""
    if n & 128:
        return 255 & ((n << 1) ^ 27)
    return n << 1


def qm(n: int) -> int:
    return vm(n) ^ n


def _m(n: int) -> int:
    """dollar_m in JS"""
    return qm(vm(n))


def ym(n: int) -> int:
    return _m(qm(vm(n)))


def gm(n: int) -> int:
    return ym(n) ^ _m(n) ^ qm(n)


def mix(e):
    """Km_full - confusion function on array"""
    t = [0, 0, 0, 0, 0, 0]
    t[0] = gm(e[0]) ^ ym(e[1]) ^ _m(e[2]) ^ qm(e[3])
    t[1] = qm(e[0]) ^ gm(e[1]) ^ ym(e[2]) ^ _m(e[3])
    t[2] = _m(e[0]) ^ qm(e[1]) ^ gm(e[2]) ^ ym(e[3])
    t[3] = ym(e[0]) ^ _m(e[1]) ^ qm(e[2]) ^ gm(e[3])
    t[4] = e[4] if len(e) > 4 else 0
    t[5] = e[5] if len(e) > 5 else 0
    return t


def av(s: str, key: str, n: int) -> str:
    """
    Map each char of s to a char in key[:len(key)+n]
    n is negative: slice from start to len(key)+n
    """
    idx = key[:len(key) + n]
    result = ''
    for ch in s:
        p = idx[ord(ch) % len(idx)]
        result += p
    return result


def sv(s: str, key: str) -> str:
    """Map each char of s to a char in full key"""
    result = ''
    for ch in s:
        p = key[ord(ch) % len(key)]
        result += p
    return result


def interleave(arr):
    """Interleave strings position by position"""
    max_len = max(len(s) for s in arr)
    result = ''
    for k in range(max_len):
        for s in arr:
            if k < len(s):
                result += s[k]
    return result


def generate_nonce() -> str:
    """Generate random nonce"""
    raw = str(int(time.time())) + str(random.random())
    return hashlib.md5(raw.encode()).hexdigest().upper()


def get_hkey(url_path: str, timestamp: int = 0, nonce: str = '',
             sort_by_length: bool = False) -> str:
    """
    Generate hkey for the given URL path.

    Args:
        url_path: API path like '/bbs/app/link/tree'
        timestamp: Unix timestamp (seconds), auto if 0
        nonce: Random nonce, auto if empty
        sort_by_length: If True, sort components by length before interleaving (Go version)

    Returns:
        hkey string
    """
    if not timestamp:
        timestamp = int(time.time())
    if not nonce:
        nonce = generate_nonce()

    ts_str = str(timestamp)

    # Normalize path
    parts = [p for p in url_path.split('/') if p]
    normalized = '/' + '/'.join(parts) + '/'

    # Generate 3 components
    comp1 = av(ts_str, KEY_STR, -2)  # key[:34]
    comp2 = sv(normalized, KEY_STR)
    comp3 = sv(nonce, KEY_STR)

    comps = [comp1, comp2, comp3]

    if sort_by_length:
        # Go version: sort by length ascending
        comps.sort(key=len)

    # Interleave
    interleaved = interleave(comps)

    # First 20 chars
    md5_input = interleaved[:20]

    # MD5
    md5_hash = hashlib.md5(md5_input.encode()).hexdigest()

    # hkey prefix: av(md5[:5], key, -4) => key[:32]
    hkey_prefix = av(md5_hash[:5], KEY_STR, -4)

    # hkey suffix: mix(md5[-6:] ascii) sum % 100
    suffix_part = md5_hash[-6:]
    suffix_input = [ord(c) for c in suffix_part]
    mixed = mix(suffix_input)
    checksum_val = sum(mixed) % 100
    hkey_suffix = f"{checksum_val:02d}"

    return hkey_prefix + hkey_suffix, timestamp, nonce


def sign_request(url_path: str, extra_params: dict = None,
                 sort_by_length: bool = False) -> dict:
    """
    Generate all params for a xiaoheihe API request.

    Args:
        url_path: API path like '/bbs/app/link/tree'
        extra_params: Additional query parameters
        sort_by_length: Use Go-style sorting (True) or JS-style (False)

    Returns:
        dict of query parameters
    """
    timestamp = int(time.time())
    nonce = generate_nonce()
    hkey, _, _ = get_hkey(url_path, timestamp, nonce, sort_by_length)

    params = {
        'os_type': 'web',
        'app': 'heybox',
        'client_type': 'web',
        'version': '999.0.4',
        'web_version': '3.0',
        'x_client_type': 'web',
        'x_app': 'heybox_website',
        'heybox_id': '',
        'x_os_type': 'Windows',
        'device_info': 'Chrome',
        'device_id': os.environ.get('XHH_DEVICE_ID', '00000000000000000000000000000000'),
        'hkey': hkey,
        '_time': str(timestamp),
        'nonce': nonce,
    }

    if extra_params:
        params.update(extra_params)

    return params


if __name__ == '__main__':
    # Test with known path
    path = '/bbs/app/link/tree'
    hkey, ts, nonce = get_hkey(path)
    print(f'JS-style (no sort): hkey={hkey}, _time={ts}, nonce={nonce}')
    
    hkey2, ts2, nonce2 = get_hkey(path, sort_by_length=True)
    print(f'Go-style (sorted): hkey={hkey2}, _time={ts2}, nonce={nonce2}')
    
    # Test specific values
    test_ts = 1784856352
    test_nonce = '4043F843B703AE9B7A13D06C62BBFCC2'
    hkey3, _, _ = get_hkey(path, test_ts, test_nonce)
    print(f'Test with user params: hkey={hkey3}')
    hkey4, _, _ = get_hkey(path, test_ts, test_nonce, sort_by_length=True)
    print(f'Test with user params (sorted): hkey={hkey4}')
