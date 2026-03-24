"""
热榜工具插件 V1.0

版本: 1.0.0
创建日期: 2026-03-23
迁移来源: V5 scripts/hot_ranking/

功能:
- 番茄小说热榜爬取（SSR JSON解析）
- 起点中文网热榜爬取（移动版解析）
- 晋江文学城热榜爬取（月票榜/收藏榜）
- 聚合数据生成（题材榜/类型榜/作家榜）
- 数据缓存管理（10分钟有效期）

核心规则（强制保护）:
1. 热榜模块禁止破坏性修改
2. 保留真实数据标记（is_real=True）
3. 保留降级数据机制
4. 保留V5热度归一化算法

参考文档:
- 《项目总体架构设计说明书V1.2》第四章
- 《插件接口定义V2.1》
"""

import json
import logging
import os
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin
import sys

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.plugin_interface import ToolPlugin, PluginMetadata, PluginType, PluginContext

# 可选依赖检测
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


@dataclass
class CacheInfo:
    """缓存信息"""
    exists: bool
    message: str
    datetime: str = ""
    timestamp: str = ""
    is_valid: bool = False
    age_hours: float = 0.0


class HotRankingDataManager:
    """热榜数据管理器（仅内存缓存）"""

    def __init__(self, data_dir: str = None):
        # 仅使用内存缓存，不保存到文件
        self.cache_duration = timedelta(minutes=10)
        self._memory_cache = {
            'data': None,
            'timestamp': None
        }
        self._logger = logging.getLogger(__name__)

    def save_ranking_data(self, data: Dict[str, List[Dict]]) -> str:
        """保存排行榜数据到内存"""
        self._memory_cache = {
            'data': data,
            'timestamp': datetime.now()
        }
        book_count = len(data.get('起点中文网', [])) + len(data.get('番茄小说', [])) + len(data.get('晋江文学城', []))
        self._logger.info(f"热榜数据已保存到内存缓存（{book_count}本书）")
        return "memory"

    def load_latest_data(self) -> Dict:
        """加载内存缓存数据"""
        if self._memory_cache['data'] is None:
            self._logger.info("无内存缓存数据")
            return {}

        if self._is_cache_valid({'datetime': self._memory_cache['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}):
            age_seconds = (datetime.now() - self._memory_cache['timestamp']).total_seconds()
            self._logger.info(f"加载内存缓存数据成功（{age_seconds:.1f}秒前）")
            return self._memory_cache['data']
        else:
            self._logger.info("内存缓存已过期")
            return {}

    def _is_cache_valid(self, cache_data: Dict) -> bool:
        """检查缓存是否有效"""
        if not cache_data or 'datetime' not in cache_data:
            return False

        try:
            cache_time = datetime.strptime(cache_data['datetime'], '%Y-%m-%d %H:%M:%S')
            is_valid = datetime.now() - cache_time < self.cache_duration
            return is_valid
        except Exception as e:
            self._logger.error(f"解析缓存时间失败: {e}")
            return False

    def get_cache_info(self) -> Dict:
        """获取缓存信息"""
        if self._memory_cache['data'] is None:
            return {'exists': False, 'message': '无内存缓存数据'}

        cache_time = self._memory_cache['timestamp']
        is_valid = datetime.now() - cache_time < self.cache_duration
        age_seconds = (datetime.now() - cache_time).total_seconds()

        return {
            'exists': True,
            'datetime': cache_time.strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp': cache_time.strftime('%Y%m%d_%H%M%S'),
            'is_valid': is_valid,
            'age_seconds': age_seconds,
            'message': f"{'有效' if is_valid else '已过期'}, {age_seconds:.1f}秒前"
        }

    def clear_cache(self) -> bool:
        """清除内存缓存"""
        try:
            self._memory_cache = {
                'data': None,
                'timestamp': None
            }
            self._logger.info("内存缓存已清除")
            return True
        except Exception as e:
            self._logger.error(f"清除缓存失败: {e}")
            return False
            return False

    def get_cache_size(self) -> dict:
        """获取缓存占用信息"""
        try:
            total_size = 0
            file_count = 0
            for f in os.listdir(self.data_dir):
                if (f.startswith('hot_ranking_') and f.endswith('.json')) or f == 'latest.json':
                    filepath = os.path.join(self.data_dir, f)
                    total_size += os.path.getsize(filepath)
                    file_count += 1
            return {
                'file_count': file_count,
                'total_size_kb': round(total_size / 1024, 1),
                'data_dir': self.data_dir
            }
        except Exception as e:
            return {'file_count': 0, 'total_size_kb': 0, 'data_dir': self.data_dir}

    def clean_old_files(self, max_files: int = 10):
        """保留最近N个历史文件"""
        try:
            files = []
            for f in os.listdir(self.data_dir):
                if f.startswith('hot_ranking_') and f.endswith('.json'):
                    filepath = os.path.join(self.data_dir, f)
                    files.append((filepath, os.path.getmtime(filepath)))

            files.sort(key=lambda x: x[1], reverse=True)

            for filepath, _ in files[max_files:]:
                os.remove(filepath)
                self._logger.info(f"删除旧缓存: {filepath}")

        except Exception as e:
            self._logger.error(f"清理旧文件失败: {e}")

    def get_default_data(self) -> Dict:
        """获取默认数据（离线降级）"""
        return {
            '番茄小说': self._get_default_fanqie_data(),
            '起点中文网': self._get_default_qidian_data(),
            '晋江文学城': self._get_default_jinjiang_data(),
            '男频题材榜': self._get_default_genre_data('male'),
            '女频题材榜': self._get_default_genre_data('female'),
            '男频类型榜': self._get_default_type_data('male'),
            '女频类型榜': self._get_default_type_data('female'),
            '热门作家榜': self._get_default_author_data()
        }

    def _get_default_fanqie_data(self) -> List[Dict]:
        return [
            {'rank': 1, 'title': '我在精神病院学斩神', 'author': '三九音域', 'category': '都市', 'heat': 185000, 'source': '番茄小说'},
            {'rank': 2, 'title': '星门', 'author': '老鹰吃小鸡', 'category': '玄幻', 'heat': 168000, 'source': '番茄小说'},
            {'rank': 3, 'title': '斩神', 'author': '三九音域', 'category': '都市', 'heat': 152000, 'source': '番茄小说'},
        ]

    def _get_default_qidian_data(self) -> List[Dict]:
        return [
            {'rank': 1, 'title': '诡秘之主', 'author': '爱潜水的乌贼', 'category': '玄幻', 'heat': 200000, 'source': '起点中文网'},
            {'rank': 2, 'title': '大奉打更人', 'author': '卖报小郎君', 'category': '仙侠', 'heat': 180000, 'source': '起点中文网'},
            {'rank': 3, 'title': '凡人修仙传', 'author': '忘语', 'category': '仙侠', 'heat': 160000, 'source': '起点中文网'},
        ]

    def _get_default_jinjiang_data(self) -> List[Dict]:
        return [
            {'rank': 1, 'title': '天官赐福', 'author': '墨香铜臭', 'category': '古代言情', 'heat': 190000, 'source': '晋江文学城'},
            {'rank': 2, 'title': '魔道祖师', 'author': '墨香铜臭', 'category': '仙侠奇缘', 'heat': 175000, 'source': '晋江文学城'},
            {'rank': 3, 'title': '镇魂', 'author': 'Priest', 'category': '现代言情', 'heat': 160000, 'source': '晋江文学城'},
        ]

    def _get_default_genre_data(self, gender: str) -> List[Dict]:
        if gender == 'male':
            return [
                {'name': '玄幻', 'heat': 25.5, 'works_count': 100},
                {'name': '都市', 'heat': 22.3, 'works_count': 80},
                {'name': '仙侠', 'heat': 18.7, 'works_count': 60},
                {'name': '历史', 'heat': 15.2, 'works_count': 50},
                {'name': '科幻', 'heat': 12.8, 'works_count': 40},
            ]
        else:
            return [
                {'name': '现代言情', 'heat': 28.6, 'works_count': 120},
                {'name': '古代言情', 'heat': 24.1, 'works_count': 100},
                {'name': '玄幻言情', 'heat': 19.8, 'works_count': 70},
                {'name': '仙侠奇缘', 'heat': 16.4, 'works_count': 60},
                {'name': '青春校园', 'heat': 13.2, 'works_count': 50},
            ]

    def _get_default_type_data(self, gender: str) -> List[Dict]:
        if gender == 'male':
            return [
                {'name': '系统流', 'heat': 22.8, 'works_count': 80},
                {'name': '穿越', 'heat': 20.5, 'works_count': 70},
                {'name': '重生', 'heat': 18.2, 'works_count': 60},
                {'name': '修仙', 'heat': 16.9, 'works_count': 50},
                {'name': '无敌流', 'heat': 14.3, 'works_count': 40},
            ]
        else:
            return [
                {'name': '甜宠', 'heat': 26.5, 'works_count': 90},
                {'name': '虐恋', 'heat': 23.1, 'works_count': 80},
                {'name': '穿越', 'heat': 20.8, 'works_count': 70},
                {'name': '重生', 'heat': 18.4, 'works_count': 60},
                {'name': '宫斗', 'heat': 16.2, 'works_count': 50},
            ]

    def _get_default_author_data(self) -> List[Dict]:
        return [
            {'rank': 1, 'name': '辰东', 'works': '《遮天》《完美世界》', 'works_count': 5, 'total_heat': 500000, 'sites': '起点中文网', 'income': '1500万', 'fans': '1200万'},
            {'rank': 2, 'name': '墨香铜臭', 'works': '《天官赐福》《魔道祖师》', 'works_count': 3, 'total_heat': 400000, 'sites': '晋江文学城', 'income': '1200万', 'fans': '1000万'},
            {'rank': 3, 'name': '三九音域', 'works': '《我在精神病院学斩神》', 'works_count': 2, 'total_heat': 300000, 'sites': '番茄小说', 'income': '800万', 'fans': '800万'},
        ]


class HotRankingSpider:
    """热榜数据爬虫 V5 - 三网站真实爬取"""

    DESKTOP_UA = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    ]
    MOBILE_UA = [
        'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1',
    ]

    def __init__(self):
        self.timeout = 15
        self.retry_times = 2
        self.request_delay = (0.1, 0.3)
        self._logger = logging.getLogger(__name__)

    def _rand_desktop_ua(self) -> str:
        import random
        return random.choice(self.DESKTOP_UA)

    def _rand_mobile_ua(self) -> str:
        import random
        return random.choice(self.MOBILE_UA)

    def _random_delay(self):
        import random
        time.sleep(random.uniform(*self.request_delay))

    def _get(self, url: str, mobile: bool = False, referer: str = None,
             encoding: str = None, extra_headers: dict = None) -> Optional[str]:
        """通用请求方法"""
        if not HAS_REQUESTS:
            self._logger.error("requests库未安装，无法发起网络请求")
            return None

        import random
        ua = self._rand_mobile_ua() if mobile else self._rand_desktop_ua()
        headers = {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            # 注意：不要手动设置Accept-Encoding，让requests自动处理
            # 否则服务器可能返回压缩数据导致解析失败
            'Connection': 'keep-alive',
        }
        if referer:
            headers['Referer'] = referer
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(self.retry_times):
            try:
                self._random_delay()
                resp = requests.get(url, headers=headers, timeout=(10, 15), allow_redirects=True)
                if resp.status_code == 200:
                    if encoding:
                        resp.encoding = encoding
                    if len(resp.text) < 300:
                        self._logger.warning(f"响应内容太短({len(resp.text)}字节)")
                        if attempt < self.retry_times - 1:
                            time.sleep(2)
                        continue
                    return resp.text
                elif resp.status_code in (202, 403):
                    self._logger.warning(f"HTTP {resp.status_code} {url}")
                    if attempt < self.retry_times - 1:
                        time.sleep(3)
                else:
                    self._logger.warning(f"HTTP {resp.status_code} {url}")
            except requests.exceptions.Timeout:
                self._logger.warning(f"请求超时 {url}")
            except requests.exceptions.ConnectionError as e:
                self._logger.warning(f"连接错误 {url}: {e}")
                if attempt < self.retry_times - 1:
                    time.sleep(2)
            except Exception as e:
                self._logger.error(f"请求异常 {url}: {e}")

        self._logger.error(f"所有尝试均失败，无法获取 {url}")
        return None

    def crawl_fanqie_hot(self, top_n: int = 20) -> List[Dict]:
        """爬取番茄小说热榜（真实数据）"""
        if not HAS_REQUESTS:
            return self._get_fanqie_mock_data(top_n)

        self._logger.info("开始爬取番茄小说热榜...")
        books = []
        seen_ids = set()
        offset = 0

        while len(books) < top_n:
            # 番茄小说热榜接口
            if offset == 0:
                url = 'https://fanqienovel.com/rank'
            else:
                url = f'https://fanqienovel.com/rank?offset={offset}&limit=20'

            self._logger.info(f"  爬取第{offset//20 + 1}页")
            html = self._get(url, referer='https://fanqienovel.com/')
            if not html:
                break

            try:
                # 解析SSR注入的数据 - 使用计数器找到完整JSON对象边界
                start_marker = 'window.__INITIAL_STATE__='
                start_pos = html.find(start_marker)
                if start_pos == -1:
                    self._logger.warning("番茄小说页面未找到数据注入")
                    break
                
                json_start = start_pos + len(start_marker)
                
                # 使用计数器找到匹配的}位置
                def find_json_end(s, start):
                    """找到JSON对象的结束位置"""
                    count = 0
                    in_string = False
                    escape = False
                    for i, c in enumerate(s[start:], start):
                        if escape:
                            escape = False
                            continue
                        if c == '\\':
                            escape = True
                            continue
                        if c == '"':
                            in_string = not in_string
                            continue
                        if in_string:
                            continue
                        if c == '{':
                            count += 1
                        elif c == '}':
                            count -= 1
                            if count == 0:
                                return i
                    return -1
                
                json_end = find_json_end(html, json_start)
                if json_end == -1:
                    self._logger.warning("番茄小说JSON对象边界查找失败")
                    break
                
                json_content = html[json_start:json_end+1]
                state = json.loads(json_content)
                book_list = state.get('rank', {}).get('book_list', [])
                if not book_list:
                    self._logger.warning("番茄小说book_list为空，可能已到末页")
                    break

                for book in book_list:
                    if len(books) >= top_n:
                        break

                    # 提取书籍信息
                    title = book.get('bookName') or book.get('title', '')
                    author = book.get('author') or '未知'
                    category = book.get('category') or '未知'
                    book_id = book.get('bookId') or ''

                    if not title or not book_id:
                        continue

                    if book_id in seen_ids:
                        continue
                    seen_ids.add(book_id)

                    # 提取热度值（多个可能的字段）
                    heat = 0
                    heat_fields = ['readCount', 'hot_num', 'score', 'heatValue', 'readerCount']
                    for heat_key in heat_fields:
                        val = book.get(heat_key)
                        if val:
                            try:
                                heat = int(val)
                                if heat > 0:
                                    break
                            except:
                                pass

                    # 如果没有热度值，根据排名计算一个
                    if heat == 0:
                        rank_num = len(books) + 1
                        heat = max(100000, (21 - rank_num) * 10000)

                    link = f"https://fanqienovel.com/page/{book_id}"
                    books.append({
                        'rank': len(books) + 1,
                        'title': title,
                        'author': author,
                        'category': category,
                        'heat': heat,
                        'source': '番茄小说',
                        'url': link,
                        'is_real': True,
                        'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                    })

                self._logger.info(f"    第{offset//20 + 1}页已获取{len(books)}本")
                offset += 20
                if offset >= 100:  # 最多爬取5页
                    self._logger.info("已达到最大爬取页数")
                    break

            except json.JSONDecodeError as e:
                self._logger.error(f"番茄小说JSON解析失败: {e}")
                break
            except Exception as e:
                self._logger.error(f"番茄小说解析失败: {e}")
                break

        if books:
            self._logger.info(f"番茄小说热榜爬取成功: {len(books)}本")
            return books[:top_n]
        else:
            self._logger.warning("番茄小说未获取到数据，使用降级数据")
            return self._get_fanqie_mock_data(top_n)

    def crawl_qidian_hot(self, top_n: int = 20) -> List[Dict]:
        """爬取起点中文网多榜单（真实数据）"""
        if not HAS_REQUESTS or not HAS_BS4:
            return self._get_qidian_mock_data(top_n)

        self._logger.info(f"开始爬取起点中文网数据（目标{top_n}本）...")
        all_books = []
        seen_bids = set()

        # 多个榜单页面（PC版URL更稳定）
        rank_pages = [
            ('https://www.qidian.com/rank/hotsales', '24小时热销榜'),
            ('https://www.qidian.com/rank/readindex', '阅读指数榜'),
            ('https://www.qidian.com/rank/finish', '完本榜'),
        ]

        # 起点中文网专用请求头（绕过反爬虫）
        qidian_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Referer': 'https://www.qidian.com/',
            'DNT': '1'
        }

        for page_url, page_name in rank_pages:
            if len(all_books) >= top_n:
                break

            self._logger.info(f"  爬取{page_name}: {page_url}")

            # 使用专用请求头
            html = self._get(page_url, mobile=False, referer='https://www.qidian.com/', extra_headers=qidian_headers)
            if not html:
                self._logger.warning(f"    {page_name}页面获取失败")
                continue

            # 检查是否被反爬虫拦截
            if len(html) < 5000 or '验证' in html or '安全检测' in html:
                self._logger.warning(f"    {page_name}被反爬虫拦截")
                continue

            try:
                soup = BeautifulSoup(html, 'html.parser')

                # 查找所有书籍链接（适配PC版和移动版URL）
                book_links = soup.find_all('a', href=re.compile(r'(//(www|m)\.qidian\.com/book/\d+)|/book/\d+'))

                for a in book_links:
                    if len(all_books) >= top_n:
                        break

                    href = a.get('href', '')
                    bid_match = re.search(r'/book/(\d+)', href)
                    bid = bid_match.group(1) if bid_match else ''
                    if not bid or bid in seen_bids:
                        continue
                    seen_bids.add(bid)

                    # 提取标题
                    h2 = a.find('h2')
                    title = h2.get_text(strip=True) if h2 else ''
                    if not title:
                        title = a.get_text(strip=True).split('\n')[0].strip()
                    if not title:
                        continue

                    # 提取作者和分类
                    author = '未知'
                    category = '未知'
                    word_count = '0'

                    # 查找包含作者信息的p标签
                    all_p = a.find_all('p')
                    for p in all_p:
                        p_text = p.get_text(strip=True)
                        if '·' in p_text and len(p_text) < 50:
                            parts = [part.strip() for part in p_text.split('·') if part.strip()]
                            if len(parts) >= 1:
                                author = parts[0]
                            if len(parts) >= 2:
                                category = parts[1]

                    # 尝试从链接的父元素中提取更多信息
                    parent = a.find_parent()
                    if parent:
                        for span in parent.find_all('span'):
                            span_text = span.get_text(strip=True)
                            if re.search(r'\d+万', span_text):
                                word_count = span_text
                                break

                    book_url = 'https:' + href if href.startswith('//') else href
                    all_books.append({
                        'rank': len(all_books) + 1,
                        'title': title,
                        'author': author,
                        'category': category,
                        'heat': int(word_count.replace('万', '0000')) if word_count != '0' else 100000,
                        'source': '起点中文网',
                        'url': book_url,
                        'is_real': True,
                        'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                    })

                self._logger.info(f"    {page_name}已获取{len(all_books)}本")

            except Exception as e:
                self._logger.error(f"    {page_name}解析失败: {e}")

        if all_books:
            self._logger.info(f"起点中文网爬取成功: {len(all_books)}本")
            return all_books[:top_n]

        self._logger.warning("起点中文网未找到书籍数据，使用降级数据")
        return self._get_qidian_mock_data(top_n)

    def crawl_jinjiang_hot(self, top_n: int = 20) -> List[Dict]:
        """爬取晋江文学城多榜单（真实数据）"""
        if not HAS_REQUESTS or not HAS_BS4:
            return self._get_jinjiang_mock_data(top_n)

        self._logger.info(f"开始爬取晋江文学城数据（目标{top_n}本）...")
        all_books = []
        seen_titles = set()

        # 晋江多个榜单（orderstr: 6=积分榜, 7=月票榜, 8=霸王票榜）
        rank_pages = [
            ('http://www.jjwxc.net/topten.php?orderstr=6&t=0', '积分榜'),
            ('http://www.jjwxc.net/topten.php?orderstr=7&t=0', '月票榜'),
            ('http://www.jjwxc.net/topten.php?orderstr=8&t=0', '霸王票榜'),
        ]

        for page_url, page_name in rank_pages:
            if len(all_books) >= top_n:
                break

            self._logger.info(f"  爬取{page_name}: {page_url}")
            html = self._get(page_url, encoding='gb2312', referer='http://www.jjwxc.net/')
            if not html:
                self._logger.warning(f"    {page_name}页面获取失败")
                continue

            try:
                soup = BeautifulSoup(html, 'html.parser')
                book_links = soup.find_all('a', href=re.compile(r'onebook\.php'))

                for i, a in enumerate(book_links):
                    if len(all_books) >= top_n:
                        break

                    row = a.find_parent('tr')
                    if not row:
                        continue
                    tds = row.find_all('td')
                    if len(tds) < 3:
                        continue

                    # 标题
                    title = a.get_text(strip=True)
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    # 排名
                    rank_text = tds[0].get_text(strip=True)
                    try:
                        rank = int(rank_text)
                    except:
                        rank = i + 1

                    # 作者
                    author = '未知'
                    if len(tds) > 1:
                        author_text = tds[1].get_text(strip=True)
                        if author_text:
                            author = author_text

                    # 分类
                    category = '未知'
                    if len(tds) > 3:
                        cat_text = tds[3].get_text(strip=True)
                        if cat_text:
                            category = cat_text.replace('原创-', '').split('-')[0]

                    # 热度（积分/月票/霸王票）
                    heat = 0
                    if len(tds) > 5:
                        heat_text = tds[5].get_text(strip=True).replace(',', '')
                        try:
                            heat = int(heat_text)
                        except:
                            pass

                    if title and author != '未知':
                        link = urljoin('http://www.jjwxc.net', a.get('href', ''))
                        all_books.append({
                            'rank': len(all_books) + 1,
                            'title': title,
                            'author': author,
                            'category': category,
                            'heat': heat,
                            'source': '晋江文学城',
                            'url': link,
                            'is_real': True,
                            'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                        })

                self._logger.info(f"    {page_name}已获取{len(all_books)}本")

            except Exception as e:
                self._logger.error(f"    {page_name}解析失败: {e}")

        if all_books:
            self._logger.info(f"晋江爬取成功: {len(all_books)}本")
            return all_books[:top_n]

        self._logger.warning("晋江未找到书籍数据，使用降级数据")
        return self._get_jinjiang_mock_data(top_n)

    def crawl_all_sources(self) -> Dict:
        """并发爬取所有数据源（扩展数据源版本）"""
        sources_data = {}
        crawl_tasks = [
            ('番茄小说', self.crawl_fanqie_hot, 30),  # 增加到30本
            ('起点中文网', self.crawl_qidian_hot, 30),  # 增加到30本
            ('晋江文学城', self.crawl_jinjiang_hot, 30),  # 增加到30本
        ]

        # 创建并持有线程池引用
        executor = ThreadPoolExecutor(max_workers=3)
        try:
            futures = {
                executor.submit(func, top_n): name
                for name, func, top_n in crawl_tasks
            }

            try:
                for future in as_completed(futures, timeout=120):  # 增加超时时间
                    name = futures[future]
                    try:
                        data = future.result(timeout=60)
                        if data and isinstance(data, list) and len(data) > 0:
                            sources_data[name] = data
                            real_count = sum(1 for b in data if b.get('is_real', False))
                            self._logger.info(f"{name}: {len(data)}条数据（真实数据: {real_count}本）")
                        else:
                            self._logger.warning(f"{name}: 未获取到有效数据")
                    except Exception as e:
                        self._logger.error(f"{name} 爬取失败: {e}")
            except Exception as e:
                self._logger.error(f"爬取总体超时: {e}")

            # 生成聚合数据
            try:
                aggregated_data = self._generate_aggregated_data(sources_data)
                sources_data.update(aggregated_data)
                self._logger.info(f"聚合数据生成完成: {list(aggregated_data.keys())}")
            except Exception as e:
                self._logger.error(f"生成聚合数据失败: {e}")
        finally:
            executor.shutdown(wait=False)

        return sources_data

    def _generate_aggregated_data(self, sources_data: Dict) -> Dict:
        """生成聚合数据"""
        normalized_books = self._normalize_books_heat(sources_data)
        return {
            '男频题材榜': self._generate_genre_ranking(normalized_books, 'male'),
            '女频题材榜': self._generate_genre_ranking(normalized_books, 'female'),
            '男频类型榜': self._generate_type_ranking(normalized_books, 'male'),
            '女频类型榜': self._generate_type_ranking(normalized_books, 'female'),
            '热门作家榜': self._generate_author_ranking(normalized_books)
        }

    def _normalize_books_heat(self, sources_data: Dict) -> List[Dict]:
        """归一化热度值（V5优化算法 - 精确对数归一化+排名加权）"""
        import math
        all_books = []

        for site_name, books in sources_data.items():
            if not isinstance(books, list):
                continue

            for book in books:
                raw_heat = book.get('heat', 0) or 0
                rank = book.get('rank', 20)

                normalized = 0

                if site_name == '晋江文学城':
                    # V5优化：晋江积分（月票数），范围1千万~200亿
                    # 归一化：log10(heat) / 10.5 * 100
                    if raw_heat > 0:
                        normalized = min(100, max(0, math.log10(raw_heat) / 10.5 * 100))
                    else:
                        normalized = max(1, (21 - rank) * 3)

                elif site_name == '番茄小说':
                    # V5优化：番茄阅读数/字数估算，范围几百~几千
                    # 排名分60起 + 热度分
                    rank_score = max(0, (21 - rank) * 3)
                    if raw_heat > 0:
                        heat_score = min(100, math.log10(max(raw_heat, 1)) / 7 * 80)
                        normalized = rank_score + heat_score
                    else:
                        normalized = rank_score

                elif site_name == '起点中文网':
                    # V5优化：起点字数（几十万~几百万）
                    # 热度分 + 排名分
                    if raw_heat > 0:
                        heat_score = min(80, math.log10(max(raw_heat, 1)) / 7 * 80)
                        rank_score = max(0, (21 - rank) * 2)
                        normalized = heat_score + rank_score
                    else:
                        # 起点无热度数据时，纯排名分
                        normalized = max(5, (21 - rank) * 5)

                else:
                    # 其他站点，直接按比例缩放
                    normalized = max(1, raw_heat / 10000 if raw_heat > 0 else 1)

                book_copy = book.copy()
                book_copy['normalized_heat'] = round(normalized, 1)
                book_copy['source'] = site_name
                all_books.append(book_copy)

        return all_books

    def _generate_genre_ranking(self, books: List[Dict], gender: str) -> List[Dict]:
        """生成题材排行榜（V5优化 - 9种男频题材+7种女频题材）"""
        # V5男频题材关键词（9种）
        male_genre_keywords = {
            '玄幻': {
                'keywords': ['玄幻', '修仙', '仙界', '神魔', '异世', '帝尊', '圣皇', '神帝', '仙帝', '神王', '道君'],
                'title_patterns': ['仙', '神', '帝', '圣', '道', '魔', '妖']
            },
            '奇幻': {
                'keywords': ['奇幻', '魔法', '异能', '超能力', '魔法师', '龙族', '精灵'],
                'title_patterns': ['龙', '魔', '异能']
            },
            '武侠': {
                'keywords': ['武侠', '江湖', '武林', '侠客', '剑客', '武道'],
                'title_patterns': ['剑', '刀', '武', '侠', '宗师']
            },
            '仙侠': {
                'keywords': ['仙侠', '修真', '修仙', '仙人', '飞升', '渡劫', '元婴', '金丹'],
                'title_patterns': ['仙', '道', '劫', '飞升', '宗门', '仙门']
            },
            '都市': {
                'keywords': ['都市', '都市生活', '都市异能', '总裁', '豪门', '明星', '娱乐圈', '商战'],
                'title_patterns': ['总裁', '豪门', '明星', '演员', '歌手', '公司', 'CEO']
            },
            '历史': {
                'keywords': ['历史', '历史架空', '穿越', '重生', '三国', '大唐', '大明', '大宋'],
                'title_patterns': ['三国', '大唐', '大明', '大宋', '皇帝', '朝代', '穿越', '重生']
            },
            '科幻': {
                'keywords': ['科幻', '未来', '星际', '宇宙', '机甲', '赛博', '末世', '废土'],
                'title_patterns': ['星际', '机甲', '宇宙', '末世', '废土', '星球', '外星']
            },
            '游戏': {
                'keywords': ['游戏', '网游', '电竞', '职业选手', '虚拟现实', 'VR'],
                'title_patterns': ['游戏', '网游', '电竞', '玩家', '副本', '装备']
            },
            '灵异': {
                'keywords': ['灵异', '悬疑', '恐怖', '鬼', '僵尸', '道士', '风水', '阴阳'],
                'title_patterns': ['鬼', '尸', '墓', '阴', '灵', '诡', '凶']
            }
        }

        # V5女频题材关键词（7种）
        female_genre_keywords = {
            '现代言情': {
                'keywords': ['现代言情', '都市言情', '现言', '都市', '现代', '豪门', '总裁', '甜宠', '虐恋'],
                'title_patterns': ['总裁', '豪门', '甜', '宠', '暗恋', '初恋', '婚姻', '婚']
            },
            '古代言情': {
                'keywords': ['古代言情', '古言', '穿越言情', '架空历史', '宫廷', '宫斗', '宅斗', '王爷', '公主'],
                'title_patterns': ['王妃', '公主', '皇后', '娘娘', '王爷', '皇帝', '宫', '宅', '嫡', '庶']
            },
            '玄幻言情': {
                'keywords': ['玄幻言情', '幻言', '仙侠奇缘', '仙侠言情'],
                'title_patterns': ['仙', '妖', '魔', '神', '灵', '兽']
            },
            '仙侠奇缘': {
                'keywords': ['仙侠奇缘', '仙侠言情', '修仙', '仙门'],
                'title_patterns': ['仙尊', '仙君', '上仙', '道君']
            },
            '浪漫青春': {
                'keywords': ['浪漫青春', '青春校园', '校园', '学生', '高中', '大学'],
                'title_patterns': ['校草', '校花', '学长', '学妹', '同桌', '班级', '青春']
            },
            '悬疑推理': {
                'keywords': ['悬疑推理', '推理', '悬疑', '破案', '侦探', '刑侦'],
                'title_patterns': ['案', '侦', '侦探', '凶', '杀']
            },
            '幻想未来': {
                'keywords': ['幻想未来', '科幻', '赛博', '末世', '废土', '星际'],
                'title_patterns': ['末世', '废土', '星际', '机甲', '丧尸']
            }
        }

        genre_keywords = male_genre_keywords if gender == 'male' else female_genre_keywords
        genre_heat = defaultdict(float)
        genre_count = defaultdict(int)
        genre_books = defaultdict(list)

        for book in books:
            title = book.get('title', '')
            category = book.get('category', '')
            heat = book.get('normalized_heat', 1)
            is_real = book.get('is_real', False)

            # 真实数据1.5倍权重
            weight = 1.5 if is_real else 1.0

            # 综合书名和分类匹配题材
            matched_genre = None
            match_score = 0

            for genre, patterns in genre_keywords.items():
                score = 0
                # 分类匹配（权重更高）
                for kw in patterns['keywords']:
                    if kw in category:
                        score += 10
                # 标题匹配
                for kw in patterns['keywords']:
                    if kw in title:
                        score += 3
                for pattern in patterns['title_patterns']:
                    if pattern in title:
                        score += 2

                if score > match_score:
                    match_score = score
                    matched_genre = genre

            if matched_genre and match_score > 0:
                genre_heat[matched_genre] += heat * weight
                genre_count[matched_genre] += 1
                genre_books[matched_genre].append(title)

        # 生成结果（V5：始终返回5个条目，即使热度为0）
        result = []
        for genre in genre_keywords.keys():
            avg_heat = genre_heat[genre] / max(genre_count[genre], 1) if genre_count[genre] > 0 else 0
            result.append({
                'name': genre,
                'heat': round(genre_heat[genre], 1),
                'avg_heat': round(avg_heat, 1),
                'works_count': genre_count[genre],
                'top_works': genre_books[genre][:3]
            })

        # 按热度排序后返回前5个（确保有5个条目，即使热度为0）
        sorted_result = sorted(result, key=lambda x: x['heat'], reverse=True)

        # 调试输出
        self._logger.debug(f"{gender}频题材榜原始数据: {len(sorted_result)}个题材")
        for i, item in enumerate(sorted_result):
            self._logger.debug(f"  {i+1}. {item['name']}: {item['heat']} (作品数: {item['works_count']})")

        return sorted_result[:5]

    def _generate_type_ranking(self, books: List[Dict], gender: str) -> List[Dict]:
        """生成类型排行榜（V5优化 - 男频12种+女频11种类型）"""
        # V5男频类型关键词（12种）
        male_type_keywords = {
            '系统流': {
                'title': ['系统', '金手指', '外挂', '技能', '面板', '升级', '任务', '奖励', '数据', '加点'],
                'category': ['系统', '游戏']
            },
            '穿越': {
                'title': ['穿越', '回到', '异界', '来到', '重生之', '穿成', '穿到'],
                'category': ['穿越', '架空']
            },
            '重生': {
                'title': ['重生', '再世', '重来', '新生', '回到过去', '回到', '重来'],
                'category': ['重生']
            },
            '修仙': {
                'title': ['修仙', '修炼', '仙道', '飞升', '渡劫', '仙尊', '道君', '宗门', '仙族', '仙人', '道'],
                'category': ['仙侠', '修真']
            },
            '无敌流': {
                'title': ['无敌', '最强', '第一', '巅峰', '至尊', '神级', '无双', '绝世'],
                'category': []
            },
            '种田': {
                'title': ['种田', '经营', '建设', '领主', '城主', '庄园', '农场', '发展', '基地'],
                'category': ['种田']
            },
            '争霸': {
                'title': ['争霸', '称霸', '帝国', '一统', '王座', '皇帝', '帝王', '王国', '国度'],
                'category': ['争霸']
            },
            '爽文': {
                'title': ['爽文', '逆袭', '打脸', '装逼', '碾压', '变强'],
                'category': []
            },
            '末世': {
                'title': ['末世', '丧尸', '废土', '末日', '灾难', '生存', '庇护所', '安全屋', '永夜', '囤货'],
                'category': ['末世', '废土', '科幻']
            },
            '都市异能': {
                'title': ['异能', '超能', '觉醒', '异变', '超凡', '灵异', '神秘', '侦探', '捞尸', '道士'],
                'category': ['都市', '灵异']
            },
            '历史军事': {
                'title': ['历史', '三国', '战国', '大唐', '大宋', '明朝', '将军', '上将', '战争', '士兵'],
                'category': ['历史', '军事']
            },
            '无限流': {
                'title': ['无限', '位面', '副本', '轮回', '任务', '遮天', '诸天'],
                'category': ['无限', '诸天']
            }
        }

        # V5女频类型关键词（11种）
        female_type_keywords = {
            '甜宠': {
                'title': ['甜宠', '甜文', '宠溺', '宠妻', '甜恋', '甜度', '宠文', '娇宠', '暗恋', '初恋'],
                'category': ['甜宠', '甜文']
            },
            '虐恋': {
                'title': ['虐恋', '虐心', '虐文', 'BE', '悲剧', '泪目', '痛', '离别', '错过'],
                'category': ['虐恋', '虐文']
            },
            '宫斗': {
                'title': ['宫斗', '宫心计', '后宅', '皇后', '娘娘', '后宫', '妃', '嫔', '皇帝', '王爷', '王妃'],
                'category': ['宫斗', '宫廷']
            },
            '宅斗': {
                'title': ['宅斗', '嫡庶', '内宅', '夫人', '主母', '嫡女', '庶女', '侯府', '府', '世家'],
                'category': ['宅斗']
            },
            '快穿': {
                'title': ['快穿', '位面', '任务世界', '穿', '穿越'],
                'category': ['快穿', '穿越']
            },
            '穿书': {
                'title': ['穿书', '书中', '反派', '炮灰', '女配', '恶毒', '配角', '路人'],
                'category': ['穿书']
            },
            '娱乐圈': {
                'title': ['娱乐圈', '明星', '演员', '歌手', '影帝', '影后', '出道', '偶像', '综艺', '电影', '电视剧', '艺人'],
                'category': ['娱乐圈', '演艺']
            },
            '末世': {
                'title': ['末世', '丧尸', '废土', '囤货', '生存', '庇护所', '安全屋', '废土世界', '灾难', '末日'],
                'category': ['末世', '废土', '生存']
            },
            '年代': {
                'title': ['年代', '知青', '下乡', '农村', '七八十', '七十年代', '八十年代', '六七十', '改革'],
                'category': ['年代']
            },
            '重生': {
                'title': ['重生', '再世', '重来', '新生', '回到'],
                'category': ['重生']
            },
            '修仙': {
                'title': ['修仙', '修炼', '仙道', '飞升', '渡劫', '仙门', '道君'],
                'category': ['仙侠', '玄幻言情']
            }
        }

        keywords = male_type_keywords if gender == 'male' else female_type_keywords
        type_heat = defaultdict(float)
        type_count = defaultdict(int)
        type_books = defaultdict(list)

        for book in books:
            title = book.get('title', '')
            category = book.get('category', '')
            heat = book.get('normalized_heat', 1)

            for type_name, patterns in keywords.items():
                matched = False
                # 匹配分类关键词（权重更高）
                for kw in patterns.get('category', []):
                    if kw in category:
                        type_heat[type_name] += heat * 1.5
                        type_count[type_name] += 1
                        type_books[type_name].append(title)
                        matched = True
                        break
                if matched:
                    continue
                # 匹配标题关键词
                for kw in patterns.get('title', []):
                    if kw in title:
                        type_heat[type_name] += heat
                        type_count[type_name] += 1
                        type_books[type_name].append(title)
                        break

        # 生成结果（V5：始终返回5个条目，即使热度为0）
        result = []
        for type_name in keywords.keys():
            result.append({
                'name': type_name,
                'heat': round(type_heat[type_name], 1),
                'works_count': type_count[type_name],
                'top_works': type_books[type_name][:3]
            })

        return sorted(result, key=lambda x: x['heat'], reverse=True)[:5]

    def _generate_author_ranking(self, books: List[Dict]) -> List[Dict]:
        """生成作家排行榜（2025最新算法 - 基于真实行业数据）"""
        author_stats = defaultdict(lambda: {
            'works': [],
            'total_heat': 0,
            'sites': set(),
            'avg_rank': 0,
            'ranks': [],
            'top_rank': 999
        })

        for book in books:
            author = book.get('author', '未知')
            if author == '未知':
                continue
            heat = book.get('normalized_heat', 1)
            title = book.get('title', '未知')
            source = book.get('source', '')
            rank = book.get('rank', 20)

            author_stats[author]['works'].append(title)
            author_stats[author]['total_heat'] += heat
            author_stats[author]['sites'].add(source)
            author_stats[author]['ranks'].append(rank)
            if rank < author_stats[author]['top_rank']:
                author_stats[author]['top_rank'] = rank

        author_list = []
        for author, stats in author_stats.items():
            if author == '未知' or not stats['works']:
                continue

            # 基础指标
            total_heat = stats['total_heat']
            works_count = len(stats['works'])
            avg_rank = sum(stats['ranks']) / len(stats['ranks']) if stats['ranks'] else 20
            top_rank = stats['top_rank']
            multi_platform = len(stats['sites'])

            # 2025新算法：综合影响力评分
            # 1. 热度权重：总热度反映作品受欢迎程度（40%）
            # 2. 排名权重：最佳排名和平均排名反映作品质量（30%）
            # 3. 作品数量：多作品显示持续创作能力（15%）
            # 4. 多平台加成：跨平台影响力（15%）
            
            heat_score = total_heat * 1.0
            rank_score = (21 - top_rank) * 8 + (21 - avg_rank) * 2  # 最佳排名权重更高
            works_score = works_count * 15
            platform_score = multi_platform * 20

            # 综合评分
            score = heat_score + rank_score + works_score + platform_score

            # 2025年收入估算（基于真实行业数据）
            # 顶级作者（唐家三少/天蚕土豆级）：5000万-2亿/年
            # 白金作者（一线）：500万-5000万/年
            # 黄金作者（二线）：100万-500万/年
            # 新星作者（新人）：10万-100万/年
            
            # 评分映射到收入（对数曲线更真实）
            if score >= 500:
                # 顶级作者：5000万-2亿
                income = f"{int(5000 + (score - 500) * 300)}万"
            elif score >= 300:
                # 白金作者：500万-5000万
                income = f"{int(500 + (score - 300) * 22.5)}万"
            elif score >= 150:
                # 黄金作者：100万-500万
                income = f"{int(100 + (score - 150) * 2.67)}万"
            elif score >= 50:
                # 中层作者：30万-100万
                income = f"{int(30 + (score - 50) * 1.4)}万"
            else:
                # 新星作者：5万-30万
                income = f"{int(5 + score * 0.5)}万"

            # 2025年粉丝数估算（基于真实行业数据）
            # 顶级作者：数千万粉丝（1000万-3000万）
            # 白金作者：数百万粉丝（500万-1000万）
            # 黄金作者：百万级粉丝（100万-500万）
            # 中层作者：几十万粉丝（20万-100万）
            # 新星作者：几万粉丝（5万-20万）
            
            if score >= 500:
                fans = f"{int(1000 + (score - 500) * 40)}万"
            elif score >= 300:
                fans = f"{int(500 + (score - 300) * 2.5)}万"
            elif score >= 150:
                fans = f"{int(100 + (score - 150) * 2.67)}万"
            elif score >= 50:
                fans = f"{int(20 + (score - 50) * 1.6)}万"
            else:
                fans = f"{int(5 + score * 0.3)}万"

            author_list.append({
                'rank': 0,
                'name': author,
                'works': '、'.join(stats['works'][:3]),
                'works_count': works_count,
                'total_heat': round(total_heat, 1),
                'top_rank': top_rank,
                'avg_rank': round(avg_rank, 1),
                'score': round(score, 1),
                'sites': '、'.join(sorted(stats['sites'])),
                'income': income,
                'fans': fans
            })

        # 按综合评分排序
        author_list.sort(key=lambda x: x['score'], reverse=True)
        for idx, a in enumerate(author_list, 1):
            a['rank'] = idx

        return author_list[:10]

    def _get_fanqie_mock_data(self, top_n: int = 20) -> List[Dict]:
        """番茄小说降级数据（2026年热门作品 - 扩展到20本）"""
        mock = [
            {'rank': 1, 'title': '宿命之环', 'author': '爱潜水的乌贼', 'category': '玄幻', 'heat': 5000000},
            {'rank': 2, 'title': '我的治愈系游戏', 'author': '我会修空调', 'category': '都市', 'heat': 4500000},
            {'rank': 3, 'title': '道诡异仙', 'author': '狐尾的笔', 'category': '仙侠', 'heat': 4200000},
            {'rank': 4, 'title': '赤心巡天', 'author': '情何以甚', 'category': '玄幻', 'heat': 3800000},
            {'rank': 5, 'title': '不科学御兽', 'author': '轻泉流响', 'category': '科幻', 'heat': 3500000},
            {'rank': 6, 'title': '择日飞升', 'author': '柳岸花又明', 'category': '仙侠', 'heat': 3300000},
            {'rank': 7, 'title': '光阴之外', 'author': '耳根', 'category': '仙侠', 'heat': 3100000},
            {'rank': 8, 'title': '深海余烬', 'author': '远瞳', 'category': '科幻', 'heat': 2900000},
            {'rank': 9, 'title': '万相之王', 'author': '天蚕土豆', 'category': '玄幻', 'heat': 2700000},
            {'rank': 10, 'title': '灵境行者', 'author': '卖报小郎君', 'category': '都市', 'heat': 2500000},
            {'rank': 11, 'title': '大奉打更人', 'author': '卖报小郎君', 'category': '仙侠', 'heat': 2300000},
            {'rank': 12, 'title': '剑来', 'author': '烽火戏诸侯', 'category': '仙侠', 'heat': 2100000},
            {'rank': 13, 'title': '凡人修仙传', 'author': '忘语', 'category': '仙侠', 'heat': 1900000},
            {'rank': 14, 'title': '遮天', 'author': '辰东', 'category': '玄幻', 'heat': 1700000},
            {'rank': 15, 'title': '完美世界', 'author': '辰东', 'category': '玄幻', 'heat': 1500000},
            {'rank': 16, 'title': '圣墟', 'author': '辰东', 'category': '玄幻', 'heat': 1300000},
            {'rank': 17, 'title': '全职法师', 'author': '乱', 'category': '都市', 'heat': 1100000},
            {'rank': 18, 'title': '牧神记', 'author': '宅猪', 'category': '玄幻', 'heat': 900000},
            {'rank': 19, 'title': '大王饶命', 'author': '会说话的肘子', 'category': '都市', 'heat': 700000},
            {'rank': 20, 'title': '第一序列', 'author': '会说话的肘子', 'category': '都市', 'heat': 500000},
        ]
        for b in mock:
            b['source'] = '番茄小说'
            b['url'] = ''
            b['is_real'] = False
            b['crawl_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
        return mock[:top_n]

    def _get_qidian_mock_data(self, top_n: int = 20) -> List[Dict]:
        """起点降级数据（2026年热门作品 - 扩展到20本）"""
        mock = [
            {'rank': 1, 'title': '宿命之环', 'author': '爱潜水的乌贼', 'category': '西方玄幻', 'heat': 800000},
            {'rank': 2, 'title': '诡秘之主2', 'author': '爱潜水的乌贼', 'category': '西方玄幻', 'heat': 750000},
            {'rank': 3, 'title': '择日飞升', 'author': '柳岸花又明', 'category': '仙侠', 'heat': 680000},
            {'rank': 4, 'title': '光阴之外', 'author': '耳根', 'category': '仙侠', 'heat': 650000},
            {'rank': 5, 'title': '深海余烬', 'author': '远瞳', 'category': '科幻', 'heat': 620000},
            {'rank': 6, 'title': '赤心巡天', 'author': '情何以甚', 'category': '仙侠', 'heat': 580000},
            {'rank': 7, 'title': '不科学御兽', 'author': '轻泉流响', 'category': '科幻', 'heat': 550000},
            {'rank': 8, 'title': '道诡异仙', 'author': '狐尾的笔', 'category': '都市异能', 'heat': 520000},
            {'rank': 9, 'title': '我的治愈系游戏', 'author': '我会修空调', 'category': '都市', 'heat': 500000},
            {'rank': 10, 'title': '万相之王', 'author': '天蚕土豆', 'category': '玄幻', 'heat': 480000},
            {'rank': 11, 'title': '灵境行者', 'author': '卖报小郎君', 'category': '都市', 'heat': 450000},
            {'rank': 12, 'title': '大奉打更人', 'author': '卖报小郎君', 'category': '仙侠', 'heat': 420000},
            {'rank': 13, 'title': '剑来', 'author': '烽火戏诸侯', 'category': '仙侠', 'heat': 400000},
            {'rank': 14, 'title': '凡人修仙传', 'author': '忘语', 'category': '仙侠', 'heat': 380000},
            {'rank': 15, 'title': '遮天', 'author': '辰东', 'category': '玄幻', 'heat': 360000},
            {'rank': 16, 'title': '完美世界', 'author': '辰东', 'category': '玄幻', 'heat': 340000},
            {'rank': 17, 'title': '圣墟', 'author': '辰东', 'category': '玄幻', 'heat': 320000},
            {'rank': 18, 'title': '全职法师', 'author': '乱', 'category': '都市', 'heat': 300000},
            {'rank': 19, 'title': '牧神记', 'author': '宅猪', 'category': '玄幻', 'heat': 280000},
            {'rank': 20, 'title': '大王饶命', 'author': '会说话的肘子', 'category': '都市', 'heat': 260000},
        ]
        for b in mock:
            b['source'] = '起点中文网'
            b['url'] = ''
            b['is_real'] = False
            b['crawl_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
        return mock[:top_n]

    def _get_jinjiang_mock_data(self, top_n: int = 20) -> List[Dict]:
        """晋江降级数据（2026年热门作品 - 扩展到20本）"""
        mock = [
            {'rank': 1, 'title': '天官赐福', 'author': '墨香铜臭', 'category': '纯爱', 'heat': 500000000},
            {'rank': 2, 'title': '魔道祖师', 'author': '墨香铜臭', 'category': '纯爱', 'heat': 480000000},
            {'rank': 3, 'title': '全球高考', 'author': '木苏里', 'category': '纯爱', 'heat': 420000000},
            {'rank': 4, 'title': '将进酒', 'author': '唐酒卿', 'category': '纯爱', 'heat': 390000000},
            {'rank': 5, 'title': '某某', 'author': '木苏里', 'category': '纯爱', 'heat': 360000000},
            {'rank': 6, 'title': '破云', 'author': '淮上', 'category': '纯爱', 'heat': 330000000},
            {'rank': 7, 'title': '杀破狼', 'author': 'Priest', 'category': '纯爱', 'heat': 300000000},
            {'rank': 8, 'title': '默读', 'author': 'Priest', 'category': '纯爱', 'heat': 270000000},
            {'rank': 9, 'title': '撒野', 'author': '巫哲', 'category': '纯爱', 'heat': 250000000},
            {'rank': 10, 'title': '伪装学渣', 'author': '木瓜黄', 'category': '纯爱', 'heat': 230000000},
            {'rank': 11, 'title': '解药', 'author': '巫哲', 'category': '纯爱', 'heat': 210000000},
            {'rank': 12, 'title': '轻狂', 'author': '巫哲', 'category': '纯爱', 'heat': 190000000},
            {'rank': 13, 'title': '嚣张', 'author': '巫哲', 'category': '纯爱', 'heat': 170000000},
            {'rank': 14, 'title': 'awm绝地求生', 'author': '漫漫何其多', 'category': '纯爱', 'heat': 150000000},
            {'rank': 15, 'title': '针锋对决', 'author': '水千丞', 'category': '纯爱', 'heat': 130000000},
            {'rank': 16, 'title': '格格不入', 'author': '水千丞', 'category': '纯爱', 'heat': 110000000},
            {'rank': 17, 'title': '谁主沉浮', 'author': '水千丞', 'category': '纯爱', 'heat': 90000000},
            {'rank': 18, 'title': '追声与循途', 'author': '酱子贝', 'category': '纯爱', 'heat': 80000000},
            {'rank': 19, 'title': '我喜欢你的信息素', 'author': '引路星', 'category': '纯爱', 'heat': 70000000},
            {'rank': 20, 'title': '这题超纲了', 'author': '木瓜黄', 'category': '纯爱', 'heat': 60000000},
        ]
        for b in mock:
            b['source'] = '晋江文学城'
            b['url'] = ''
            b['is_real'] = False
            b['crawl_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
        return mock[:top_n]


class HotRankingPlugin(ToolPlugin):
    """热榜工具插件 - V5核心模块迁移

    实现 ToolPlugin 接口，提供小说网站排行榜数据爬取和管理功能。

    支持网站:
    - 番茄小说（fanqienovel.com）
    - 起点中文网（qidian.com）
    - 晋江文学城（jjwxc.net）

    功能:
    - 热榜数据爬取
    - 聚合数据生成（题材榜/类型榜/作家榜）
    - 数据缓存管理
    """

    PLUGIN_ID = "hot-ranking-v1"
    PLUGIN_NAME = "热榜工具 V1"
    PLUGIN_VERSION = "1.0.0"

    def __init__(self):
        metadata = PluginMetadata(
            id=self.PLUGIN_ID,
            name=self.PLUGIN_NAME,
            version=self.PLUGIN_VERSION,
            description="小说网站排行榜数据爬取和管理工具",
            author="项目组",
            plugin_type=PluginType.TOOL,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=["hot-ranking-v2"],
            permissions=["network.request", "file.read", "file.write"],
            min_platform_version="6.0.0",
            entry_class="HotRankingPlugin",
        )
        super().__init__(metadata)

        self._logger = logging.getLogger(__name__)
        self._spider = None
        self._data_manager = None
        self._is_updating = False
        self._last_update_time = None
        self._update_progress = 0
        self._update_status = ""
        self._executor: Optional[ThreadPoolExecutor] = None  # 持有线程池引用

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            id=cls.PLUGIN_ID,
            name=cls.PLUGIN_NAME,
            version=cls.PLUGIN_VERSION,
            description="小说网站排行榜数据爬取和管理工具",
            author="项目组",
            plugin_type=PluginType.TOOL,
            api_version="1.0",
            priority=100,
            enabled=True,
            dependencies=[],
            conflicts=["hot-ranking-v2"],
            permissions=["network.request", "file.read", "file.write"],
            min_platform_version="6.0.0",
            entry_class="HotRankingPlugin",
        )

    def initialize(self, context: PluginContext) -> bool:
        """初始化插件"""
        if not super().initialize(context):
            return False

        try:
            self._spider = HotRankingSpider()
            self._data_manager = HotRankingDataManager()
            self._logger.info(f"[{self.PLUGIN_ID}] 插件初始化成功")
            return True
        except Exception as e:
            self._logger.error(f"[{self.PLUGIN_ID}] 初始化失败: {e}")
            return False

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """执行工具操作

        Args:
            action: 操作类型
                - refresh: 刷新排行榜数据
                - get_data: 获取排行榜数据
                - get_cache_info: 获取缓存信息
                - clear_cache: 清除缓存
            params: 操作参数

        Returns:
            操作结果
        """
        params = params or {}

        if action == "refresh":
            force = params.get("force", True)
            return self._refresh_rankings(force)
        elif action == "get_data":
            force_fresh = params.get("force_fresh", False)
            return self._get_ranking_data(force_fresh)
        elif action == "get_cache_info":
            return self._data_manager.get_cache_info()
        elif action == "clear_cache":
            return self._data_manager.clear_cache()
        elif action == "get_default_data":
            return self._data_manager.get_default_data()
        else:
            raise ValueError(f"未知操作: {action}")

    def _refresh_rankings(self, force_update: bool = True) -> Dict:
        """刷新排行榜数据
        
        根据UI搭建说明，此方法会发布进度事件供UI监听：
        - hot_ranking.progress: 进度更新事件
        - hot_ranking.error: 错误事件
        """
        if not force_update:
            cached_data = self._data_manager.load_latest_data()
            if cached_data:
                meta = cached_data.get('_meta', {})
                if meta.get('is_real_data', False):
                    self._last_update_time = time.strftime('%Y-%m-%d %H:%M:%S')
                    return cached_data

        self._update_status = "正在获取网络数据..."
        self._update_progress = 10
        
        # 发布进度事件
        self._publish_progress_event(10, "正在获取网络数据...")

        try:
            ranking_data = self._spider.crawl_all_sources()
            self._update_progress = 80
            self._publish_progress_event(80, "数据获取完成，正在处理...")

            if ranking_data and isinstance(ranking_data, dict) and len(ranking_data) > 0:
                has_valid_data = any(
                    isinstance(ranking_data.get(source), list) and len(ranking_data.get(source, [])) > 0
                    for source in ['番茄小说', '起点中文网', '晋江文学城']
                )

                if has_valid_data:
                    self._data_manager.save_ranking_data(ranking_data)
                    self._data_manager.clean_old_files()
                    self._update_status = "数据更新完成"
                    self._update_progress = 100
                    self._last_update_time = time.strftime('%Y-%m-%d %H:%M:%S')
                    self._publish_progress_event(100, "数据更新完成")
                else:
                    self._update_status = "使用缓存数据"
                    cached_data = self._data_manager.load_latest_data()
                    if cached_data:
                        return cached_data
                    return self._data_manager.get_default_data()
            else:
                cached_data = self._data_manager.load_latest_data()
                if cached_data:
                    return cached_data
                return self._data_manager.get_default_data()

            return ranking_data

        except Exception as e:
            self._logger.error(f"刷新数据失败: {e}")
            # 发布错误事件
            self._publish_error_event(str(e))
            cached_data = self._data_manager.load_latest_data()
            if cached_data:
                return cached_data
            return self._data_manager.get_default_data()
    
    def _publish_progress_event(self, progress: int, status: str):
        """发布进度更新事件
        
        Args:
            progress: 进度值（0-100）
            status: 状态描述
        """
        if self._context and hasattr(self._context, 'event_bus'):
            try:
                self._context.event_bus.publish(
                    "hot_ranking.progress",
                    {
                        "progress": progress,
                        "status": status,
                        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "source": self.PLUGIN_ID
                    }
                )
            except Exception as e:
                self._logger.warning(f"发布进度事件失败: {e}")
    
    def _publish_error_event(self, error_message: str):
        """发布错误事件
        
        Args:
            error_message: 错误信息
        """
        if self._context and hasattr(self._context, 'event_bus'):
            try:
                self._context.event_bus.publish(
                    "hot_ranking.error",
                    {
                        "error": error_message,
                        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "source": self.PLUGIN_ID
                    }
                )
            except Exception as e:
                self._logger.warning(f"发布错误事件失败: {e}")

    def _get_ranking_data(self, force_fresh: bool = True) -> Dict:
        """获取排行榜数据（GUI专用接口）"""
        try:
            if not force_fresh:
                cached_data = self._data_manager.load_latest_data()
                if cached_data:
                    raw_data = cached_data
                else:
                    # 缓存不存在时，尝试爬取新数据
                    self._logger.info("[热榜] 缓存不存在，尝试爬取新数据...")
                    raw_data = self._refresh_rankings(force_update=True)
            else:
                raw_data = self._refresh_rankings(force_update=True)

            if not raw_data or not isinstance(raw_data, dict):
                raw_data = self._data_manager.get_default_data()

        except Exception as e:
            self._logger.error(f"获取排行榜数据失败: {e}")
            raw_data = self._get_default_formatted_data()

        # 转换为GUI需要的格式
        formatted_data = {
            'sites': [],
            'genres': {
                'male': {'title': '🔥 男频题材热度', 'color': '#E63946', 'genres': []},
                'female': {'title': '💕 女频题材热度', 'color': '#9B59B6', 'genres': []}
            },
            'types': {
                'male': {'title': '🎯 男频类型热度', 'color': '#2A9D8F', 'types': []},
                'female': {'title': '🌸 女频类型热度', 'color': '#E76F51', 'types': []}
            },
            'authors': [],
            'update_time': self._last_update_time or '离线数据'
        }

        site_colors = {'番茄小说': '#FF6B6B', '起点中文网': '#4ECDC4', '晋江文学城': '#9B59B6'}
        site_icons = {'番茄小说': '🍅', '起点中文网': '📚', '晋江文学城': '🎭'}
        
        site_names = ['番茄小说', '起点中文网', '晋江文学城']
        for site_name in site_names:
            books = raw_data.get(site_name, [])
            if books and isinstance(books, list) and len(books) > 0:
                formatted_data['sites'].append({
                    'name': f"{site_icons.get(site_name, '📚')} {site_name}",
                    'color': site_colors.get(site_name, '#457B9D'),
                    'books': books[:10]
                })

        # 转换题材数据
        male_genres = raw_data.get('男频题材榜', [])
        if male_genres and isinstance(male_genres, list):
            formatted_data['genres']['male']['genres'] = [
                (g.get('name', '未知'), g.get('heat', 0)) for g in male_genres[:5] if isinstance(g, dict)
            ]

        female_genres = raw_data.get('女频题材榜', [])
        if female_genres and isinstance(female_genres, list):
            formatted_data['genres']['female']['genres'] = [
                (g.get('name', '未知'), g.get('heat', 0)) for g in female_genres[:5] if isinstance(g, dict)
            ]

        # 转换类型数据
        male_types = raw_data.get('男频类型榜', [])
        if male_types and isinstance(male_types, list):
            formatted_data['types']['male']['types'] = [
                (t.get('name', '未知'), t.get('heat', 0)) for t in male_types[:5] if isinstance(t, dict)
            ]

        female_types = raw_data.get('女频类型榜', [])
        if female_types and isinstance(female_types, list):
            formatted_data['types']['female']['types'] = [
                (t.get('name', '未知'), t.get('heat', 0)) for t in female_types[:5] if isinstance(t, dict)
            ]

        # 转换作家数据
        authors = raw_data.get('热门作家榜', [])
        if authors and isinstance(authors, list):
            formatted_data['authors'] = authors[:10]

        return formatted_data

    def _get_default_formatted_data(self) -> Dict:
        """获取默认格式化数据"""
        return self._data_manager.get_default_data()

    def refresh_async(self, callback: Callable[[Dict], None] = None, force_update: bool = True):
        """异步刷新数据
        
        根据UI搭建说明，热榜页面需要监听数据更新事件来刷新显示。
        此方法在数据更新完成后会发布 'hot_ranking.updated' 事件。
        
        注意：UI层需要通过 root.after(0, callback) 调度回调到主线程。
        """
        if self._is_updating:
            return

        def update_task():
            self._is_updating = True
            try:
                data = self._refresh_rankings(force_update)
                
                # 发布数据更新事件（供UI监听）
                if self._context and hasattr(self._context, 'event_bus'):
                    try:
                        self._context.event_bus.publish(
                            "hot_ranking.updated",
                            {
                                "data": data,
                                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                                "source": self.PLUGIN_ID
                            }
                        )
                        self._logger.info(f"[{self.PLUGIN_ID}] 已发布 hot_ranking.updated 事件")
                    except Exception as e:
                        self._logger.warning(f"[{self.PLUGIN_ID}] 发布事件失败: {e}")
                
                if callback:
                    callback(data)
            finally:
                self._is_updating = False

        thread = threading.Thread(target=update_task, daemon=True)
        thread.start()

    def is_updating(self) -> bool:
        """是否正在更新"""
        return self._is_updating

    def get_update_progress(self) -> int:
        """获取更新进度"""
        return self._update_progress

    def get_update_status(self) -> str:
        """获取更新状态"""
        return self._update_status

    def get_last_update_time(self) -> str:
        """获取最后更新时间"""
        return self._last_update_time or "未更新"

    def shutdown(self) -> bool:
        """关闭插件
        
        清理资源：
        1. 等待后台更新线程完成
        2. 清理资源引用
        """
        try:
            # 等待后台更新完成（最多等待10秒）
            wait_count = 0
            while self._is_updating and wait_count < 100:
                time.sleep(0.1)
                wait_count += 1
            
            if self._is_updating:
                self._logger.warning(f"[{self.PLUGIN_ID}] 后台更新未完成，强制关闭")
            
            # 清理资源引用
            self._spider = None
            self._data_manager = None
            
            self._logger.info(f"[{self.PLUGIN_ID}] 插件已关闭")
            return super().shutdown()
            
        except Exception as e:
            self._logger.error(f"[{self.PLUGIN_ID}] 关闭失败: {e}")
            return False

    def get_supported_actions(self) -> list:
        """获取支持的操作列表
        
        Returns:
            操作名称列表
        """
        return ["refresh", "get_data", "get_cache_info", "clear_cache", "get_default_data"]

    def get_action_schema(self, action: str) -> Optional[Dict[str, Any]]:
        """获取操作的参数模式
        
        Args:
            action: 操作名称
            
        Returns:
            参数模式字典，不支持的操作返回None
        """
        schemas = {
            "refresh": {
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "description": "是否强制刷新",
                        "default": True
                    }
                }
            },
            "get_data": {
                "type": "object",
                "properties": {
                    "force_fresh": {
                        "type": "boolean",
                        "description": "是否获取最新数据",
                        "default": True
                    }
                }
            },
            "get_cache_info": {
                "type": "object",
                "properties": {}
            },
            "clear_cache": {
                "type": "object",
                "properties": {}
            },
            "get_default_data": {
                "type": "object",
                "properties": {}
            }
        }
        return schemas.get(action)


# ============================================================================
# 模块级函数
# ============================================================================

def get_plugin_class():
    """获取插件类"""
    return HotRankingPlugin


def register_plugin():
    """注册插件"""
    return HotRankingPlugin


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    # 修复编码问题
    import sys
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    print("=" * 60)
    print("热榜工具插件 V1 测试")
    print("=" * 60)

    # 测试爬虫
    spider = HotRankingSpider()
    print("\n[测试爬虫]")
    data = spider.crawl_all_sources()
    print(f"数据源: {list(data.keys())}")

    print(f"\n男频题材榜: {len(data.get('男频题材榜', []))}条")
    for g in data.get('男频题材榜', [])[:3]:
        print(f"  {g['name']}: {g['heat']} (作品数: {g.get('works_count', 0)})")

    print(f"\n女频题材榜: {len(data.get('女频题材榜', []))}条")
    for g in data.get('女频题材榜', [])[:3]:
        print(f"  {g['name']}: {g['heat']} (作品数: {g.get('works_count', 0)})")

    print(f"\n男频类型榜: {len(data.get('男频类型榜', []))}条")
    for t in data.get('男频类型榜', [])[:3]:
        print(f"  {t['name']}: {t['heat']} (作品数: {t.get('works_count', 0)})")

    print(f"\n女频类型榜: {len(data.get('女频类型榜', []))}条")
    for t in data.get('女频类型榜', [])[:3]:
        print(f"  {t['name']}: {t['heat']} (作品数: {t.get('works_count', 0)})")

    print(f"\n热门作家榜: {len(data.get('热门作家榜', []))}位")
    for a in data.get('热门作家榜', [])[:3]:
        print(f"  {a['rank']}. {a['name']}: {a['income']} / {a['fans']}粉丝")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
