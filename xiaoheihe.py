#!/usr/bin/env python3
"""
小黑盒 API 客户端 — 通过 WARP SOCKS5 代理访问
"""

import os
import hashlib
import time
import random
import re
import json
import logging

import requests

logger = logging.getLogger("xiaoheihe-bot")

# ====== 签名算法 ======

KEY_STR = "AB45STUVWZEFGJ6CH01D237IXYPQRKLMN89"

def vm(n: int) -> int:
    return 255 & ((n << 1) ^ 27) if (n & 128) else n << 1

def qm(n: int) -> int:
    return vm(n) ^ n

def _m(n: int) -> int:
    return qm(vm(n))

def ym(n: int) -> int:
    return _m(qm(vm(n)))

def gm(n: int) -> int:
    return ym(n) ^ _m(n) ^ qm(n)

def mix(e):
    t = [0, 0, 0, 0, 0, 0]
    t[0] = gm(e[0]) ^ ym(e[1]) ^ _m(e[2]) ^ qm(e[3])
    t[1] = qm(e[0]) ^ gm(e[1]) ^ ym(e[2]) ^ _m(e[3])
    t[2] = _m(e[0]) ^ qm(e[1]) ^ gm(e[2]) ^ ym(e[3])
    t[3] = ym(e[0]) ^ _m(e[1]) ^ qm(e[2]) ^ gm(e[3])
    t[4] = e[4] if len(e) > 4 else 0
    t[5] = e[5] if len(e) > 5 else 0
    return t

def av(s: str, key: str, n: int) -> str:
    idx = key[:len(key) + n]
    return ''.join(idx[ord(ch) % len(idx)] for ch in s)

def sv(s: str, key: str) -> str:
    return ''.join(key[ord(ch) % len(key)] for ch in s)

def interleave(arr):
    max_len = max(len(s) for s in arr)
    result = []
    for k in range(max_len):
        for s in arr:
            if k < len(s):
                result.append(s[k])
    return ''.join(result)

def generate_nonce() -> str:
    raw = str(int(time.time())) + str(random.random())
    return hashlib.md5(raw.encode()).hexdigest().upper()

def get_hkey(url_path: str, timestamp: int = 0, nonce: str = '') -> tuple:
    if not timestamp:
        timestamp = int(time.time())
    if not nonce:
        nonce = generate_nonce()

    parts = [p for p in url_path.split('/') if p]
    normalized = '/' + '/'.join(parts) + '/'

    comp1 = av(str(timestamp), KEY_STR, -2)
    comp2 = sv(normalized, KEY_STR)
    comp3 = sv(nonce, KEY_STR)

    interleaved = interleave([comp1, comp2, comp3])
    md5_hash = hashlib.md5(interleaved[:20].encode()).hexdigest()

    hkey_prefix = av(md5_hash[:5], KEY_STR, -4)
    suffix_input = [ord(c) for c in md5_hash[-6:]]
    checksum_val = sum(mix(suffix_input)) % 100

    return hkey_prefix + f"{checksum_val:02d}", timestamp, nonce


# ====== API 客户端 ======

BASE_URL = "https://api.xiaoheihe.cn"
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en-GB;q=0.8,en;q=0.7,en-US;q=0.6',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Connection': 'keep-alive',
    'Origin': 'https://www.xiaoheihe.cn',
    'Referer': 'https://www.xiaoheihe.cn/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0',
    'sec-ch-ua': '"Not;A=Brand";v="8", "Chromium";v="150", "Microsoft Edge";v="150"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}

# ====== 代理配置 ======

PROXY_WARP = "socks5://127.0.0.1:40000"  # WARP SOCKS5
PROXY_MODE = os.environ.get("PROXY_MODE", "auto").lower()  # warp, direct, auto

_sessions = {}
_last_request_time = 0.0
_MIN_INTERVAL = 2.0  # 全局最小请求间隔（秒）
# 可选认证 Cookie
_XHH_TOKEN = os.environ.get("XHH_TOKEN", "")


def _get_session(mode: str):
    """获取指定模式的 session"""
    key = mode
    if key not in _sessions:
        s = requests.Session()
        if mode == 'warp':
            s.proxies = {'http': PROXY_WARP, 'https': PROXY_WARP}
        if _XHH_TOKEN:
            s.cookies.set('x_xhh_tokenid', _XHH_TOKEN)
        s.headers.update(HEADERS)
        _sessions[key] = s
    return _sessions[key]


def _get_proxy_modes() -> list:
    """根据 PROXY_MODE 返回尝试顺序"""
    if PROXY_MODE == 'warp':
        return ['warp']
    elif PROXY_MODE == 'direct':
        return ['direct']
    else:  # auto: warp 优先，限频了切直连
        return ['warp', 'direct']


def sign_params(path: str, extra: dict = None) -> dict:
    timestamp = int(time.time())
    nonce = generate_nonce()
    hkey, _, _ = get_hkey(path, timestamp, nonce)

    params = {
        'app': 'heybox',
        'os_type': 'web',
        'x_app': 'heybox_website',
        'x_client_type': 'web',
        'x_os_type': 'Windows',
        'x_client_version': '',
        'client_type': 'web',
        'web_version': '3.0',
        'version': '999.0.4',
        'hkey': hkey,
        '_time': str(timestamp),
        'nonce': nonce,
    }
    if extra:
        params.update(extra)
    return params


def api_get(path: str, extra: dict = None, retries: int = 3) -> dict:
    """调用小黑盒 API，支持双通道 failover + 全局限速"""
    global _last_request_time

    # 全局速率控制
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()

    api_name = path.split('/')[-1]  # 接口简称
    modes = _get_proxy_modes()
    last_error = ""

    for mode in modes:
        session = _get_session(mode)
        mode_label = {'warp': 'WARP', 'direct': '直连'}.get(mode, mode)
        for attempt in range(retries + 1):
            params = sign_params(path, extra)
            try:
                resp = session.get(BASE_URL + path, params=params, timeout=15)
                data = resp.json()
                if data.get('status') == 'show_captcha':
                    wait = 5 * (2 ** attempt)  # 5s, 10s, 20s, 40s 退避
                    logger.warning(f"[{mode_label}] {api_name} show_captcha, 等待 {wait}s (attempt {attempt+1}/{retries+1})")
                    if attempt < retries:
                        time.sleep(wait)
                        continue
                    last_error = f"限频（{mode_label} {api_name}）"
                    break
                if data.get('status') != 'ok':
                    raise Exception(f"API 错误: {data.get('msg', '未知错误')}")
                return data
            except requests.exceptions.Timeout:
                if attempt < retries:
                    time.sleep(3)
                    continue
                last_error = f"超时（{mode_label} {api_name}）"
                break
            except requests.exceptions.ConnectionError as e:
                if 'SOCKS' in str(e) or 'socks' in str(e):
                    logger.warning(f"WARP 代理 [{api_name}] 不可用，切直连")
                    break
                if attempt < retries:
                    time.sleep(2)
                    continue
                last_error = f"连接错误（{mode_label} {api_name}）: {e}"
                break

    if last_error:
        raise Exception(f"请求失败（{last_error}），请稍后再试")
    raise Exception("请求太频繁被限频，等几分钟再试试")


# ====== 数据获取 ======

def fetch_link_data(link_id: str) -> dict:
    """获取帖子完整数据"""
    data = api_get('/bbs/app/link/tree', {
        'link_id': link_id,
        'page': '1',
        'is_first': '1',
        'limit': '20',
        'owner_only': '0',
        'index': '1',
    })
    return data['result']['link']


def fetch_comments(link_id: str, page: int = 1, limit: int = 50) -> list:
    """获取帖子评论"""
    try:
        data = api_get('/bbs/app/link/tree', {
            'link_id': link_id,
            'page': str(page),
            'is_first': '1' if page == 1 else '0',
            'limit': str(limit),
            'owner_only': '0',
            'index': '1',
        })
        return data['result'].get('comments', [])
    except Exception:
        return []


def fetch_sub_comments(root_comment_id: str, lastval: str = '0') -> list:
    """获取某条主评论的更多附加评论"""
    try:
        data = api_get('/bbs/app/comment/sub/comments', {
            'root_comment_id': root_comment_id,
            'lastval': lastval,
        })
        return data['result'].get('comments', [])
    except Exception:
        return []


# ====== Telegraph ======

TELEGRAPH_API = "https://api.telegra.ph"
# 通过环境变量提供。获取方式：
#   curl -s 'https://api.telegra.ph/createAccount?short_name=xhh&author_name=xhh' | jq -r .result.access_token
TELEGRAPH_TOKEN = os.environ.get('TELEGRAPH_TOKEN', '')


def telegraph_create_page(title: str, content: list,
                          author_name: str = None,
                          author_url: str = None) -> str:
    """在 Telegraph 创建页面，返回 URL"""
    payload = {
        'access_token': TELEGRAPH_TOKEN,
        'title': title,
        'author_name': author_name or '小黑盒解析姬',
        'content': json.dumps(content, ensure_ascii=False),
        'return_content': False,
    }
    resp = requests.post(f"{TELEGRAPH_API}/createPage", json=payload, timeout=15)
    result = resp.json()
    if not result.get('ok'):
        raise Exception(f"Telegraph 创建失败: {result.get('error', '未知')}")
    return result['result']['url']


# ====== 内容解析 ======

CUBE_EMOJI = {
    'cube_哭泣': '😢', 'cube_捂脸哭': '😭', 'cube_笑哭': '😂',
    'cube_喜欢': '😍', 'cube_生气': '😡', 'cube_无语': '😓',
    'cube_疑问': '❓', 'cube_震惊': '😱', 'cube_害怕': '😰',
    'cube_尴尬': '😅', 'cube_流汗': '😅', 'cube_翻白眼': '🙄',
    'cube_亲亲': '😘', 'cube_爱心': '❤️', 'cube_心碎': '💔',
    'cube_赞': '👍', 'cube_弱': '👎', 'cube_OK': '👌',
    'cube_抱拳': '🙏', 'cube_握手': '🤝', 'cube_庆祝': '🎉',
    'cube_烟花': '🎆', 'cube_下雨': '🌧️', 'cube_太阳': '☀️',
    'cube_月亮': '🌙', 'cube_星星': '⭐', 'cube_骷髅': '💀',
    'cube_嘴唇': '👄', 'cube_老虎': '🐯', 'cube_猫': '🐱',
    'cube_狗': '🐶', 'cube_火箭': '🚀', 'cube_爆米花': '🍿',
    'cube_啤酒': '🍺', 'cube_蛋糕': '🎂',
}


def parse_cube_emojis(text: str) -> str:
    def replace_cube(m):
        key = 'cube_' + m.group(1)
        return CUBE_EMOJI.get(key, f'[{m.group(1)}]')
    return re.sub(r'\[cube_(\w+)\]', replace_cube, text)


def to_original_url(url: str) -> str:
    """把 CDN 缩略图 URL 转成原图 URL。

    规则: `.../<hash>/thumb.<ext>?params`  →  `.../<hash>.<ext>`
    （去掉查询参数 + 去掉路径中的 `/thumb` 段）

    实测: 原图体积是缩略图的 1~3 倍（同分辨率，压缩更少）。
    转换后若不成立（极少），CDN 仍会返回可用图，不影响显示。
    """
    if not url:
        return url
    u = url.split('?')[0]  # 去查询参数
    m = re.match(r'^(.*/)([0-9a-fA-F]{16,})/thumb\.(\w+)$', u)
    if m:
        return f'{m.group(1)}{m.group(2)}.{m.group(3)}'
    return u


def comment_img_nodes(comment: dict) -> list:
    """提取评论的图片（`imgs` 字段），返回 Telegraph img 节点列表"""
    nodes = []
    for im in (comment.get('imgs') or []):
        if not isinstance(im, dict):
            continue
        u = im.get('url') or im.get('thumb') or ''
        if u:
            nodes.append({'tag': 'img', 'attrs': {'src': to_original_url(u)}})
    return nodes


def parse_comment_html(text: str) -> list:
    """将评论中的 HTML 标签转为 Telegraph Node 列表
    
    返回 list of Telegraph nodes（字符串为纯文本，dict 为富文本节点）
    
    - <a href="URL">text</a> → {"tag":"a","attrs":{"href":"URL"},"children":["text"]}
    - 其他标签剥离
    """
    result = []
    pos = 0
    for m in re.finditer(r'<a\s+[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', text):
        # 链接前的纯文本
        if m.start() > pos:
            result.append(text[pos:m.start()])
        href = m.group(1)
        display = m.group(2)
        result.append({
            'tag': 'a',
            'attrs': {'href': href},
            'children': [display]
        })
        pos = m.end()
    # 剩余纯文本
    if pos < len(text):
        result.append(text[pos:])
    # 过滤空字符串
    return [r for r in result if r != '' and not (isinstance(r, str) and r.strip() == '')]


def parse_comment_text(text: str) -> list:
    """完整解析评论文本：cube 表情 + HTML 标签 → Telegraph nodes"""
    # 先转 cube 表情
    text = parse_cube_emojis(text)
    # 再解析 HTML → nodes
    return parse_comment_html(text)


def build_telegraph_content(link_data: dict, comments: list = None,
                            max_top_level: int = 15,
                            max_replies: int = 5) -> list:
    """构建 Telegraph 内容节点列表
    
    Args:
        link_data: 帖子数据
        comments: 评论列表（顶层 group 结构）
        max_top_level: 显示前 N 条主评论
        max_replies: 每条主评论带 N 条附加评论（引用格式）
    """
    content = []

    # ── 元信息 ──
    author = link_data.get('user', {}).get('username', '未知')
    create_at = link_data.get('create_at', 0)
    topic_name = ''
    if link_data.get('topics'):
        topic_name = link_data['topics'][0].get('name', '')
    time_str = time.strftime('%Y-%m-%d %H:%M',
                             time.localtime(create_at)) if create_at else '未知'

    meta_parts = [f'作者：{author}']
    if topic_name:
        meta_parts.append(f'社区：{topic_name}')
    meta_parts.append(time_str)
    content.append({'tag': 'p', 'children': [{'tag': 'b', 'children': [' | '.join(meta_parts)]}]})

    stats = []
    for k, v in [('link_award_num', '👍'), ('favour_count', '⭐'), ('comment_num', '💬')]:
        val = link_data.get(k, 0)
        if val:
            stats.append(f'{v} {val}')
    if stats:
        content.append({'tag': 'p', 'children': ['  '.join(stats)]})
    content.append({'tag': 'hr', 'children': []})

    # ── 正文 ──
    raw_text = link_data.get('text', '[]')
    blocks = []
    if isinstance(raw_text, str):
        if raw_text.startswith('{'):
            # 可能是嵌套结构 {"blocks": [...]}
            try:
                obj = json.loads(raw_text)
                if 'blocks' in obj:
                    blocks = obj['blocks']
                elif 'content' in obj:
                    blocks = obj['content']
            except json.JSONDecodeError:
                blocks = []
        elif raw_text.startswith('['):
            try:
                blocks = json.loads(raw_text)
            except json.JSONDecodeError:
                blocks = []
    elif isinstance(raw_text, list):
        blocks = raw_text
    elif isinstance(raw_text, dict):
        blocks = raw_text.get('blocks', raw_text.get('content', []))

    _has_html_block = False  # 追踪是否已有内嵌图片的 html 块

    for block in blocks:
        if not isinstance(block, dict):
            continue
        t = block.get('type', '')
        # 兼容无 type 字段的文本块: {"text": "<html>..."}
        if not t and 'text' in block:
            t = 'text'

        if t in ('text', 'p', 'paragraph', 'html'):
            raw = block.get('text', block.get('content', block.get('data', '')))
            # 处理 HTML 内容：提取 <p> 段落和 <img>
            if '<p>' in raw or '<br' in raw:
                # HTML 格式 — 解析 <p> 标签和 <img>
                paras = re.findall(r'<p[^>]*>(.*?)</p>', raw, re.DOTALL)
                if not paras:
                    paras = [raw]
                has_inline_img = False
                for para_html in paras:
                    # 提取段落中的 <img>（src 或 data-original）
                    img_match = re.search(r'<img[^>]*src="([^"]*)"', para_html)
                    if not img_match:
                        img_match = re.search(r'<img[^>]*data-original="([^"]*)"', para_html)
                    if img_match:
                        img_url = to_original_url(img_match.group(1))
                        content.append({'tag': 'img', 'attrs': {'src': img_url}})
                        has_inline_img = True
                    else:
                        # 纯文本段落
                        text = re.sub(r'<[^>]+>', '', para_html)
                        text = parse_cube_emojis(text.strip())
                        if text:
                            content.append({'tag': 'p', 'children': [text]})
                if has_inline_img:
                    _has_html_block = True  # 有内嵌图片，后续重复的 img 块跳过
            else:
                # 纯文本格式
                text = parse_cube_emojis(raw.strip())
                if text:
                    for para in text.split('\n'):
                        para = para.strip()
                        if para:
                            content.append({'tag': 'p', 'children': [para]})

        elif t in ('img', 'image', 'picture'):
            if _has_html_block:
                # html 块已解析，里面的 <img> 已经在行内输出，跳过重复
                continue
            img_url = block.get('url', block.get('src', block.get('data', '')))
            if img_url:
                content.append({'tag': 'img', 'attrs': {'src': to_original_url(img_url)}})

        elif t in ('video',):
            # 视频暂时跳过，或者放个链接
            pass

        elif t == 'title':
            text = parse_cube_emojis(block.get('text', '')).strip()
            if text:
                content.append({'tag': 'h4', 'children': [text]})

        elif t == 'reply':
            # 引用其他帖子的回复结构
            pass

    content.append({'tag': 'hr', 'children': []})

    # ── 评论 ──
    total_comments = link_data.get('comment_num', 0)
    content.append({
        'tag': 'h3',
        'children': [f'💬 热门评论（共 {total_comments} 条）']
    })

    if not comments:
        comments = []

    shown = 0
    for comment_group in comments:
        if shown >= max_top_level:
            break
        try:
            all_c = comment_group.get('comment', [])
            if not all_c:
                continue

            # 主评论（第一个）
            main = all_c[0]
            main_text = parse_comment_text(main.get('text', ''))
            main_user = main.get('user', {})
            main_name = main_user.get('username', '匿名')
            main_up = main.get('up', 0)
            main_floor = main.get('floor_num', 0)
            main_time = main.get('create_at', 0)
            main_id = main.get('commentid', '')

            header = f'#{main_floor} {main_name}'
            if main_up:
                header += f'  👍{main_up}'
            if main_time:
                header += f'  {time.strftime("%m/%d %H:%M", time.localtime(main_time))}'

            content.append({
                'tag': 'p',
                'children': [{'tag': 'b', 'children': [header]}]
            })
            content.append({'tag': 'p', 'children': main_text})
            # 主评论的图片
            content.extend(comment_img_nodes(main))

            # 收集回复：先用主 API 已有的回复
            replies = list(all_c[1:])  # 主 API 已返回的回复
            # 只在主 API 返回的回复实在不够时才调子评论 API（最多查 5 条主评论）
            if len(replies) < max_replies and main_id and shown < 5:
                try:
                    more = fetch_sub_comments(str(main_id))
                    seen_ids = {r.get('commentid') for r in replies}
                    for r in more:
                        if r.get('commentid') not in seen_ids:
                            replies.append(r)
                            seen_ids.add(r.get('commentid'))
                            if len(replies) >= max_replies:
                                break
                except Exception:
                    pass  # 子评论 API 失败不影响主评论
                # 请求间隔，避免触发频率限制
                time.sleep(0.5)

            for r in replies[:max_replies]:
                r_text = parse_comment_text(r.get('text', ''))
                r_user = r.get('user', {})
                r_name = r_user.get('username', '匿名')
                r_up = r.get('up', 0)

                r_header = f'{r_name}'
                if r_up:
                    r_header += f' 👍{r_up}'

                content.append({
                    'tag': 'blockquote',
                    'children': [{
                        'tag': 'p',
                        'children': [
                            {'tag': 'b', 'children': [r_header + '  ']},
                            *([r_text] if isinstance(r_text, str) else r_text)
                        ]
                    }, *comment_img_nodes(r)]
                })

            shown += 1
        except (KeyError, IndexError):
            continue

    return content


# ====== URL 解析 ======

def parse_link_id(text: str) -> str | None:
    """从文本中提取小黑盒 link_id（仅限 xiaoheihe.cn 相关域名）"""
    # 仅当消息包含小黑盒域名才匹配
    if 'xiaoheihe' not in text.lower():
        return None

    m = re.search(r'link_id=([a-f0-9]+)', text)
    if m:
        return m.group(1)
    m = re.search(r'/link/([a-f0-9]+)', text)
    if m:
        return m.group(1)
    return None


# ====== 主流程 ======

def process_share(share_text: str) -> dict:
    """
    处理小黑盒分享链接，返回 Telegraph 页面信息
    """
    link_id = parse_link_id(share_text)
    if not link_id:
        raise ValueError("无法识别 link_id")

    link_data = fetch_link_data(link_id)
    title = (link_data.get('title') or '').strip()
    author = link_data.get('user', {}).get('username', '未知')

    # Telegraph 要求标题非空且 <= 256 字符
    if not title:
        # 用正文首段兜底
        try:
            raw = link_data.get('text', '[]')
            blocks = json.loads(raw) if isinstance(raw, str) else raw
            for b in (blocks or []):
                if isinstance(b, dict):
                    t = b.get('text', '') or b.get('content', '')
                    t = re.sub(r'<[^>]+>', '', t).strip()
                    if t:
                        title = t.split('\n')[0][:50]
                        break
        except Exception:
            pass
    if not title:
        title = f'小黑盒帖子 {link_id}'
    title = title[:256]

    comments = fetch_comments(link_id)
    content = build_telegraph_content(link_data, comments)

    url = telegraph_create_page(
        title=title,
        content=content,
        author_name=f'{author} @ 小黑盒',
    )

    return {
        'title': title,
        'author': author,
        'url': url,
        'comments': link_data.get('comment_num', 0),
    }
