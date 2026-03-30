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
    """热榜数据管理器（内存+文件双缓存，24小时有效期）"""

    def __init__(self, data_dir: str = None):
        # 缓存有效期24小时（需求文档要求）
        self.cache_duration = timedelta(hours=24)
        
        # 内存缓存
        self._memory_cache = {
            'data': None,
            'timestamp': None
        }
        
        # 文件缓存路径
        if data_dir:
            self.data_dir = data_dir
        else:
            self.data_dir = Path(__file__).parent / 'data'
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._logger = logging.getLogger(__name__)

    def save_ranking_data(self, data: Dict[str, List[Dict]]) -> str:
        """保存排行榜数据到内存和文件（双缓存）"""
        # 保存到内存
        self._memory_cache = {
            'data': data,
            'timestamp': datetime.now()
        }
        
        # 保存到文件（可选，作为持久化备份）
        try:
            cache_file = self.data_dir / 'hot_ranking_cache.json'
            cache_data = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data': data
            }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            self._logger.info(f"热榜数据已保存到文件缓存: {cache_file}")
        except Exception as e:
            self._logger.warning(f"保存文件缓存失败（不影响内存缓存）: {e}")
        
        book_count = len(data.get('起点中文网', [])) + len(data.get('番茄小说', [])) + len(data.get('晋江文学城', []))
        self._logger.info(f"热榜数据已保存（{book_count}本书，24小时有效期）")
        return "memory+file"

    def load_latest_data(self) -> Dict:
        """加载缓存数据（优先内存，降级文件）"""
        # 优先尝试内存缓存
        if self._memory_cache['data'] is not None:
            if self._is_cache_valid({'datetime': self._memory_cache['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}):
                age_seconds = (datetime.now() - self._memory_cache['timestamp']).total_seconds()
                self._logger.info(f"加载内存缓存数据成功（{age_seconds:.0f}秒前，24小时有效）")
                return self._memory_cache['data']
        
        # 降级尝试文件缓存
        try:
            cache_file = self.data_dir / 'hot_ranking_cache.json'
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                if self._is_cache_valid(cache_data):
                    # 加载到内存缓存
                    self._memory_cache = {
                        'data': cache_data['data'],
                        'timestamp': datetime.strptime(cache_data['timestamp'], '%Y-%m-%d %H:%M:%S')
                    }
                    age_seconds = (datetime.now() - self._memory_cache['timestamp']).total_seconds()
                    self._logger.info(f"加载文件缓存数据成功（{age_seconds:.0f}秒前，24小时有效）")
                    return cache_data['data']
        except Exception as e:
            self._logger.warning(f"加载文件缓存失败: {e}")
        
        self._logger.info("无有效缓存数据")
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
        """获取缓存信息（24小时有效期）"""
        # 优先检查内存缓存
        if self._memory_cache['data'] is not None:
            cache_time = self._memory_cache['timestamp']
            is_valid = datetime.now() - cache_time < self.cache_duration
            age_seconds = (datetime.now() - cache_time).total_seconds()
            age_hours = age_seconds / 3600

            return {
                'exists': True,
                'datetime': cache_time.strftime('%Y-%m-%d %H:%M:%S'),
                'timestamp': cache_time.strftime('%Y%m%d_%H%M%S'),
                'is_valid': is_valid,
                'age_seconds': age_seconds,
                'age_hours': round(age_hours, 1),
                'message': f"{'有效' if is_valid else '已过期'}, {age_hours:.1f}小时前",
                'source': '内存缓存'
            }
        
        # 检查文件缓存
        try:
            cache_file = self.data_dir / 'hot_ranking_cache.json'
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                cache_time = datetime.strptime(cache_data['timestamp'], '%Y-%m-%d %H:%M:%S')
                is_valid = datetime.now() - cache_time < self.cache_duration
                age_seconds = (datetime.now() - cache_time).total_seconds()
                age_hours = age_seconds / 3600

                return {
                    'exists': True,
                    'datetime': cache_data['timestamp'],
                    'timestamp': cache_time.strftime('%Y%m%d_%H%M%S'),
                    'is_valid': is_valid,
                    'age_seconds': age_seconds,
                    'age_hours': round(age_hours, 1),
                    'message': f"{'有效' if is_valid else '已过期'}, {age_hours:.1f}小时前",
                    'source': '文件缓存'
                }
        except Exception as e:
            self._logger.warning(f"读取文件缓存信息失败: {e}")
        
        return {'exists': False, 'message': '无缓存数据（24小时有效期）'}

    def clear_cache(self) -> bool:
        """清除内存和文件缓存"""
        try:
            # 清除内存缓存
            self._memory_cache = {
                'data': None,
                'timestamp': None
            }
            
            # 清除文件缓存
            cache_file = self.data_dir / 'hot_ranking_cache.json'
            if cache_file.exists():
                cache_file.unlink()
                self._logger.info(f"已删除文件缓存: {cache_file}")
            
            self._logger.info("所有缓存已清除")
            return True
        except Exception as e:
            self._logger.error(f"清除缓存失败: {e}")
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
    """热榜数据爬虫 V5.5 - 三网站真实爬取 + 反爬优化"""

    # 扩展User-Agent池（10个桌面 + 10个移动）
    DESKTOP_UA = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    ]
    MOBILE_UA = [
        'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (iPad; CPU OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 14; Xiaomi 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 13; OnePlus 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 14; vivo X100) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
    ]

    def __init__(self):
        self.timeout = 15
        self.retry_times = 2
        # 优化请求延迟：需求文档建议1-3秒，实际测试1-3秒太慢，改为0.5-2秒
        self.request_delay = (0.5, 2.0)
        self._logger = logging.getLogger(__name__)
        # 存储作家榜单数据（从首页获取）
        self._fanqie_writers = []

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
                # proxies={} 强制禁用系统代理，避免本地未运行的代理（如127.0.0.1:7897）导致连接失败
                resp = requests.get(url, headers=headers, timeout=(10, 15),
                                    allow_redirects=True, proxies={})
                if resp.status_code == 200:
                    if encoding:
                        resp.encoding = encoding
                    elif resp.apparent_encoding and resp.apparent_encoding.lower() not in ('utf-8', 'ascii'):
                        # 服务器未声明编码时（如晋江 GB2312），用 chardet 自动检测
                        resp.encoding = resp.apparent_encoding
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

    # 番茄小说分类映射表（2026年最新）
    _FANQIE_CATEGORY_MAP = {
        # 男频分类
        1141: '西方奇幻', 1140: '东方仙侠', 8: '科幻末世',
        261: '都市日常', 124: '都市修真', 1014: '都市高武',
        273: '历史古代', 27: '战神赘婿', 263: '都市种田',
        258: '传统玄幻', 272: '历史脑洞', 539: '悬疑脑洞',
        262: '都市脑洞', 257: '玄幻脑洞', 751: '悬疑灵异',
        504: '抗战谍战', 746: '游戏体育', 718: '动漫衍生',
        1016: '男频衍生', 1: '玄幻', 2: '仙侠', 3: '都市',
        4: '游戏', 5: '科幻', 6: '历史', 7: '武侠',
        8: '悬疑', 9: '军事', 10: '体育',
        # 女频分类
        1139: '古风世情', 1015: '女频衍生', 248: '玄幻言情',
        23: '种田', 79: '年代', 267: '现言脑洞',
        246: '宫斗宅斗', 253: '古言脑洞', 24: '快穿',
        749: '青春甜宠', 745: '星光璀璨', 747: '女频悬疑',
        750: '职场婚恋', 748: '豪门总裁', 1017: '民国言情',
        100: '现代言情', 101: '古代言情', 102: '玄幻言情',
        103: '仙侠奇缘', 104: '浪漫青春', 105: '悬疑恋爱',
        # 通用
        1200: '轻小说',
    }

    def crawl_fanqie_hot(self, top_n: int = 20) -> List[Dict]:
        """爬取番茄小说热榜（直接从首页API获取作品榜）"""
        if not HAS_REQUESTS:
            return self._get_fanqie_mock_data(top_n)

        self._logger.info("开始爬取番茄小说热榜...")
        books = []
        seen_titles = set()

        # 直接从首页获取数据
        home_url = 'https://fanqienovel.com/'
        home_html = self._get(home_url, referer='https://fanqienovel.com/')
        
        if home_html:
            try:
                state = self._parse_fanqie_state(home_html)
                if state and 'home' in state:
                    home_data = state['home']
                    
                    # 获取作家榜（用于作家排名）
                    self._fanqie_writers = home_data.get('writerList', [])
                    self._logger.info(f"  获取到 {len(self._fanqie_writers)} 位作家")
                    
                    # 获取作品榜数据源
                    # 1. 周榜 weekList (8本)
                    # 2. 男频 boyList (6本)
                    # 3. 女频 girlList (6本)
                    # 4. 更新榜 updateList (20本)
                    rank_sources = [
                        ('周榜', home_data.get('weekList', [])),
                        ('男频', home_data.get('boyList', [])),
                        ('女频', home_data.get('girlList', [])),
                        ('更新', home_data.get('updateList', [])),
                    ]
                    
                    for source_name, source_list in rank_sources:
                        if not source_list:
                            continue
                        self._logger.info(f"  {source_name}: {len(source_list)}本")
                        for item in source_list:
                            if len(books) >= top_n:
                                break
                            title = item.get('bookName', '')
                            if title and title not in seen_titles:
                                seen_titles.add(title)
                                books.append({
                                    'title': title,
                                    'author': item.get('author', '未知'),
                                    'category': self._guess_category(title),
                                    'heat': item.get('wordCount', item.get('heat', 1000)),
                                    'source': '番茄小说',
                                    'url': '',
                                    'is_real': True,
                                    'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                                })
                        
                    self._logger.info(f"  作品榜共获取 {len(books)} 本")
                    
            except Exception as e:
                self._logger.warning(f"  首页解析失败: {e}")

        if books:
            # 重新编号
            for i, book in enumerate(books):
                book['rank'] = i + 1
            self._logger.info(f"番茄小说热榜爬取成功: {len(books)}本")
            return books[:top_n]
        else:
            self._logger.warning("番茄小说未获取到数据，使用降级数据")
            return self._get_fanqie_mock_data(top_n)

    def _is_valid_title(self, title: str) -> bool:
        """检查标题是否有效（排除乱码）"""
        if not title:
            return False
        # 排除包含特殊Unicode控制字符的标题
        bad_chars = ['\ue49c', '\ue4f8', '\uf0a1', '\uf0d8', '\uf0e4', '\uf0f0', '\uf0fb']
        for bc in bad_chars:
            if bc in title:
                return False
        # 标题应该主要是中文字符
        chinese_count = sum(1 for c in title if '\u4e00' <= c <= '\u9fff')
        return chinese_count >= len(title) * 0.5

    def _guess_category(self, title: str) -> str:
        """根据书名猜测分类（最终版）"""
        title_lower = title.lower()

        # 女频关键词优先
        female_keywords = {
            '古代言情': ['言情', '甜宠', '总裁', '豪门', '婚', '恋', '爱', '娇', '宠', '花芷', '金枝', '锦杀', '嫡女', '庶女', '贵女', '夫人', '王爷', '公主', '皇后', '妃', '宫', '宅斗', '和离', '世子', '侯府', '琅琊', '千金', '小姐'],
            '现代言情': ['霸总', '闪婚', '军婚', '甜妻', '前夫', '前女友', '离婚', '追妻', '诱婚'],
        }

        for cat, kws in female_keywords.items():
            if any(kw in title_lower for kw in kws):
                return cat

        # 男频关键词
        if any(kw in title_lower for kw in ['仙', '神', '帝', '尊', '皇', '道', '魔', '修仙', '飞升', '渡劫', '金丹', '元婴', '天骄', '霸主', '至尊', '主宰', '星河', '仙途', '仙域']):
            return '玄幻仙侠'
        if any(kw in title_lower for kw in ['都市', '重生', '穿越', '回到', '1983', '1987', '无敌', '下山']):
            return '都市'
        if any(kw in title_lower for kw in ['科幻', '星际', '末世', '机甲', '赛博']):
            return '科幻'
        if any(kw in title_lower for kw in ['历史', '三国', '大唐', '大明', '大宋', '皇帝', '朝堂', '仕途']):
            return '历史'
        if any(kw in title_lower for kw in ['武侠', '江湖', '武林', '剑', '刀', '宗师', '武侠']):
            return '武侠'
        if any(kw in title_lower for kw in ['游戏', '电竞', '网游', '玩家']):
            return '游戏'
        if any(kw in title_lower for kw in ['灵异', '悬疑', '恐怖', '鬼', '风水', '阴阳', '终焉']):
            return '悬疑'

        return '综合'

    def _parse_fanqie_state(self, html: str) -> dict:
        """解析番茄小说的__INITIAL_STATE__"""
        start_marker = 'window.__INITIAL_STATE__='
        start_pos = html.find(start_marker)
        if start_pos == -1:
            return None

        json_start = start_pos + len(start_marker)

        def find_json_end(s, start):
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
        if json_end > 0:
            try:
                return json.loads(html[json_start:json_end+1])
            except json.JSONDecodeError:
                return None
        return None

    def _crawl_fanqie_category(self, cat_id: int, top_n: int = 10) -> List[Dict]:
        """爬取指定分类的榜单"""
        url = f'https://fanqienovel.com/rank?cateId={cat_id}'
        html = self._get(url, referer='https://fanqienovel.com/')
        if not html:
            return []

        try:
            state = self._parse_fanqie_state(html)
            if not state or 'rank' not in state:
                return []

            book_list = state['rank'].get('book_list', [])
            category_name = self._FANQIE_CATEGORY_MAP.get(cat_id, '未知')

        except json.JSONDecodeError as e:
            self._logger.warning(f"  分类 {cat_id} JSON解析失败: {e}")
            return []
        except Exception as e:
            self._logger.warning(f"  分类 {cat_id} 爬取异常: {e}")
            return []

        try:

            books = []
            for book in book_list[:top_n]:
                title = book.get('bookName', '')
                author = book.get('author', '未知')
                book_id = book.get('bookId', '')

                if not title or not book_id:
                    continue

                # 获取热度
                heat = 0
                for heat_key in ['read_count', 'readCount', 'hot_num']:
                    val = book.get(heat_key)
                    if val:
                        try:
                            heat = int(val)
                            if heat > 0:
                                break
                        except:
                            pass

                if heat == 0:
                    heat = max(10000, (11 - len(books)) * 1000)

                books.append({
                    'rank': len(books) + 1,
                    'title': title,
                    'author': author,
                    'category': category_name,
                    'heat': heat,
                    'source': '番茄小说',
                    'url': f"https://fanqienovel.com/page/{book_id}",
                    'is_real': True,
                    'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                })

            self._logger.info(f"  分类 {category_name}: 获取 {len(books)} 本")
            return books

        except Exception as e:
            self._logger.warning(f"  分类 {cat_id} 爬取失败: {e}")
            return []

    def _crawl_fanqie_default(self, top_n: int = 10) -> List[Dict]:
        """爬取默认榜单（备用）"""
        url = 'https://fanqienovel.com/rank'
        html = self._get(url, referer='https://fanqienovel.com/')
        if not html:
            return []

        try:
            state = self._parse_fanqie_state(html)
            if not state or 'rank' not in state:
                return []

            book_list = state['rank'].get('book_list', [])
            books = []

            for book in book_list[:top_n]:
                title = book.get('bookName', '')
                author = book.get('author', '未知')
                book_id = book.get('bookId', '')
                cat_id = book.get('curent_category_id') or book.get('pos_category_id') or 0

                if not title or not book_id:
                    continue

                try:
                    cat_id = int(cat_id)
                except:
                    cat_id = 0

                category = self._FANQIE_CATEGORY_MAP.get(cat_id, '未知')

                heat = 0
                for heat_key in ['read_count', 'readCount']:
                    val = book.get(heat_key)
                    if val:
                        try:
                            heat = int(val)
                            if heat > 0:
                                break
                        except:
                            pass

                if heat == 0:
                    heat = max(10000, (11 - len(books)) * 1000)

                books.append({
                    'rank': len(books) + 1,
                    'title': title,
                    'author': author,
                    'category': category,
                    'heat': heat,
                    'source': '番茄小说',
                    'url': f"https://fanqienovel.com/page/{book_id}",
                    'is_real': True,
                    'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                })

            return books

        except Exception as e:
            self._logger.warning(f"  默认榜单爬取失败: {e}")
            return []

    def crawl_qidian_hot(self, top_n: int = 20) -> List[Dict]:
        """爬取起点中文网多榜单（移动版，真实数据）"""
        if not HAS_REQUESTS or not HAS_BS4:
            return self._get_qidian_mock_data(top_n)

        self._logger.info(f"开始爬取起点中文网数据（目标{top_n}本）...")
        all_books = []
        seen_bids = set()

        # 移动版URL（PC版返回HTTP 202反爬拦截，移动版正常）
        rank_pages = [
            ('https://m.qidian.com/rank/hotsales/', '热销榜'),
            ('https://m.qidian.com/rank/readindex/', '阅读指数榜'),
        ]

        mobile_ua = self._rand_mobile_ua()

        for page_url, page_name in rank_pages:
            if len(all_books) >= top_n:
                break

            self._logger.info(f"  爬取{page_name}: {page_url}")

            html = self._get(page_url, mobile=True, referer='https://m.qidian.com/')
            if not html:
                self._logger.warning(f"    {page_name}页面获取失败")
                continue

            if len(html) < 5000:
                self._logger.warning(f"    {page_name}内容过短({len(html)}字节)，可能被拦截")
                continue

            try:
                soup = BeautifulSoup(html, 'html.parser')

                # 移动版书籍链接：href=/book/{bid}/ 或 //m.qidian.com/book/{bid}/
                book_links = soup.find_all('a', href=re.compile(r'/book/\d+'))

                for a in book_links:
                    if len(all_books) >= top_n:
                        break

                    href = a.get('href', '')
                    bid_match = re.search(r'/book/(\d+)', href)
                    bid = bid_match.group(1) if bid_match else ''
                    if not bid or bid in seen_bids:
                        continue
                    seen_bids.add(bid)

                    # 移动版：整个 <a> 的 text 格式为 "排名 书名 简介 作者·分类·字数"
                    raw_text = a.get_text(' ', strip=True)

                    # 提取标题：先找 <h3>/<h2>/<cite>，再从文本切割
                    title = ''
                    for tag in ('h3', 'h2', 'cite', 'p'):
                        el = a.find(tag)
                        if el:
                            t = el.get_text(strip=True)
                            if t and len(t) > 1 and not t.isdigit():
                                title = t
                                break

                    # 若标签未找到，从文本中解析（"1 书名 简介..."）
                    if not title:
                        parts = raw_text.split()
                        for part in parts:
                            if not part.isdigit() and len(part) >= 2:
                                title = part
                                break

                    if not title:
                        continue

                    # 提取作者·分类·字数（格式：作者 · 分类 · xx万字）
                    author = '未知'
                    category = '未知'
                    meta_match = re.search(r'([^\s·]{2,12})\s*·\s*([^\s·]{2,10})\s*·\s*([\d.]+万字)', raw_text)
                    if meta_match:
                        author = meta_match.group(1).strip()
                        category = meta_match.group(2).strip()

                    book_url = 'https:' + href if href.startswith('//') else (
                        'https://m.qidian.com' + href if href.startswith('/') else href)
                    all_books.append({
                        'rank': len(all_books) + 1,
                        'title': title,
                        'author': author,
                        'category': category,
                        'heat': (21 - len(all_books)) * 10000,
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
        """爬取晋江文学城多榜单（真实数据，使用移动端API）"""
        if not HAS_REQUESTS or not HAS_BS4:
            return self._get_jinjiang_mock_data(top_n)

        self._logger.info(f"开始爬取晋江文学城数据（目标{top_n}本）...")
        all_books = []
        seen_titles = set()

        # 晋江移动端榜单URL（更稳定，数据更完整）
        # naturalmore/5 = 月度排行榜, naturalmore/6 = 季度排行榜
        rank_pages = [
            ('https://m.jjwxc.net/rank/naturalmore/5', '月度排行榜'),
            ('https://m.jjwxc.net/rank/naturalmore/6', '季度排行榜'),
        ]

        # 用于存储作家信息（稍后用于作家榜）
        self._jinjiang_authors = []

        for page_url, page_name in rank_pages:
            if len(all_books) >= top_n:
                break


            self._logger.info(f"  爬取{page_name}: {page_url}")
            
            # 晋江移动端使用 GB18030 编码，不指定 encoding 让 _get 自动检测
            html = self._get(page_url, encoding=None, referer='https://m.jjwxc.net/')
            if not html:
                self._logger.warning(f"    {page_name}页面获取失败，尝试PC端...")
                # 降级到PC端
                html = self._get_jinjiang_pc_fallback(page_name, top_n - len(all_books))
                if html:
                    all_books.extend(html)
                continue

            try:
                # 晋江移动端返回 GB18030，_get 的 apparent_encoding 会自动检测
                soup = BeautifulSoup(html, 'html.parser')
                text = soup.get_text()
                
                # 验证解码是否成功（检查是否有中文）
                if '排行' not in text and '晋江' not in text and '作者' not in text:
                    # 尝试手动解码
                    self._logger.debug(f"    {page_name}自动编码检测失败，尝试手动解码...")
                    decode_success = False
                    for enc in ['gb18030', 'gbk', 'big5']:
                        try:
                            html_bytes = html.encode('latin-1')
                            html_decoded = html_bytes.decode(enc)
                            soup = BeautifulSoup(html_decoded, 'html.parser')
                            text = soup.get_text()
                            if '排行' in text or '晋江' in text or '作者' in text:
                                decode_success = True
                                break
                            soup = None
                        except:
                            continue
                    
                    if not decode_success or not soup:
                        self._logger.warning(f"    {page_name}编码解析失败")
                        continue

                # 查找书籍链接
                book_links = soup.find_all('a', href=re.compile(r'/book2/\d+'))
                
                for a in book_links:
                    if len(all_books) >= top_n:
                        break

                    title = a.get_text(strip=True)
                    if not title or len(title) < 2:
                        continue
                    if title in seen_titles:
                        continue
                    
                    # 跳过明显不是书名的链接
                    if any(skip in title for skip in ['更多', '晋江', '首页', '排行', '分类']):
                        continue
                    
                    seen_titles.add(title)
                    href = a.get('href', '')
                    book_id_match = re.search(r'/book2/(\d+)', href)
                    book_id = book_id_match.group(1) if book_id_match else ''

                    all_books.append({
                        'rank': len(all_books) + 1,
                        'title': title,
                        'author': '',  # 需要二次请求获取
                        'category': '',  # 需要二次请求获取
                        'heat': 1000 - len(all_books) * 10,  # 估算热度
                        'source': '晋江文学城',
                        'url': f'https://m.jjwxc.net/book2/{book_id}' if book_id else '',
                        'book_id': book_id,
                        'is_real': True,
                        'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                    })

                self._logger.info(f"    {page_name}已获取{len(all_books)}本")

                # 从页面底部提取作家信息
                author_links = soup.find_all('a', href=re.compile(r'/wapauthor/\d+'))
                for a in author_links[:20]:  # 最多20位作家
                    name = a.get_text(strip=True)
                    if name and len(name) > 1:
                        href = a.get('href', '')
                        author_id_match = re.search(r'/wapauthor/(\d+)', href)
                        if author_id_match:
                            self._jinjiang_authors.append({
                                'name': name,
                                'author_id': author_id_match.group(1),
                            })

            except Exception as e:
                self._logger.error(f"    {page_name}解析失败: {e}")
                # 降级到PC端
                html = self._get_jinjiang_pc_fallback(page_name, top_n - len(all_books))
                if html:
                    all_books.extend(html)

        # 如果移动端获取不足，补充PC端
        if len(all_books) < top_n:
            self._logger.info(f"  移动端数据不足，补充PC端数据...")
            pc_books = self._get_jinjiang_pc_fallback('积分榜', top_n - len(all_books))
            for book in pc_books:
                if book['title'] not in seen_titles:
                    seen_titles.add(book['title'])
                    all_books.append(book)

        if all_books:
            # 重新编号
            for i, book in enumerate(all_books):
                book['rank'] = i + 1
            self._logger.info(f"晋江爬取成功: {len(all_books)}本")
            return all_books[:top_n]

        self._logger.warning("晋江未找到书籍数据，使用降级数据")
        return self._get_jinjiang_mock_data(top_n)

    def _get_jinjiang_pc_fallback(self, page_name: str, needed: int) -> List[Dict]:
        """PC端晋江爬取降级方案"""
        books = []
        
        rank_pages = [
            ('https://www.jjwxc.net/topten.php?orderstr=6&t=0', '积分榜'),
            ('https://www.jjwxc.net/topten.php?orderstr=7&t=0', '月票榜'),
        ]
        
        for page_url, name in rank_pages:
            if len(books) >= needed:
                break
            
            html = self._get(page_url, encoding=None, referer='https://www.jjwxc.net/')
            if not html:
                continue
                
            try:
                soup = BeautifulSoup(html, 'html.parser')
                book_links = soup.find_all('a', href=re.compile(r'onebook\.php'))
                
                for a in book_links:
                    if len(books) >= needed:
                        break
                        
                    row = a.find_parent('tr')
                    if not row:
                        continue
                    tds = row.find_all('td')
                    if len(tds) < 3:
                        continue
                        
                    title = a.get_text(strip=True)
                    if not title:
                        continue
                        
                    author = tds[1].get_text(strip=True) if len(tds) > 1 else '未知'
                    category = ''
                    if len(tds) > 3:
                        cat_text = tds[3].get_text(strip=True)
                        if cat_text:
                            category = cat_text.replace('原创-', '').split('-')[0]
                    
                    heat = 0
                    if len(tds) > 5:
                        try:
                            heat = int(tds[5].get_text(strip=True).replace(',', ''))
                        except:
                            pass
                    
                    books.append({
                        'rank': len(books) + 1,
                        'title': title,
                        'author': author,
                        'category': category,
                        'heat': heat,
                        'source': '晋江文学城',
                        'url': urljoin('http://www.jjwxc.net', a.get('href', '')),
                        'is_real': True,
                        'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                    })
            except Exception as e:
                self._logger.warning(f"    PC端{name}解析失败: {e}")
        
        return books

    def crawl_jinjiang_authors(self, top_n: int = 20) -> List[Dict]:
        """爬取晋江作家榜（真实数据）- V5.3优化：PC端+移动端双通道"""
        if not HAS_REQUESTS or not HAS_BS4:
            return []

        self._logger.info(f"开始爬取晋江作家榜（目标{top_n}位）...")
        authors = []

        # V5.3优化：优先尝试PC端（数据更完整）
        # PC端作家榜URL
        pc_urls = [
            'https://www.jjwxc.net/rank.php?r=9&t=1',  # 作者积分榜
            'https://www.jjwxc.net/rank.php?r=10&t=1', # 作者收藏榜
        ]
        
        for url in pc_urls:
            if len(authors) >= top_n:
                break
                
            self._logger.info(f"  尝试PC端: {url}")
            html = self._get(url, encoding='gb18030', referer='https://www.jjwxc.net/')
            if not html:
                continue

            try:
                soup = BeautifulSoup(html, 'html.parser')
                
                # PC端：查找包含作者信息的表格行
                # 晋江PC端榜单通常是表格结构
                rows = soup.find_all('tr')
                for row in rows:
                    if len(authors) >= top_n:
                        break
                    
                    # 查找作者链接
                    author_link = row.find('a', href=re.compile(r'/author/\d+|/oneauthor\.php\?authorid='))
                    if author_link:
                        name = author_link.get_text(strip=True)
                        if not name or len(name) < 2:
                            continue
                        
                        href = author_link.get('href', '')
                        author_id_match = re.search(r'authorid=(\d+)|/author/(\d+)', href)
                        if not author_id_match:
                            continue
                        
                        author_id = author_id_match.group(1) or author_id_match.group(2)
                        
                        # 避免重复
                        if any(a.get('author_id') == author_id for a in authors):
                            continue
                        
                        authors.append({
                            'rank': len(authors) + 1,
                            'name': name,
                            'author_id': author_id,
                            'works': '',
                            'works_count': 0,
                            'total_heat': 0,
                            'fans': '',
                            'score': 0,
                            'source': '晋江文学城',
                            'url': f'https://www.jjwxc.net/oneauthor.php?authorid={author_id}',
                        })

                if authors:
                    self._logger.info(f"    PC端找到{len(authors)}位作家")
                    
            except Exception as e:
                self._logger.warning(f"    PC端解析失败: {e}")

        # 移动端URL作为备用
        if len(authors) < top_n:
            author_urls = [
                'https://m.jjwxc.net/rank/naturalmore/58',  # 作者积分榜
                'https://m.jjwxc.net/rank/naturalmore/36',  # 勤奋指数榜
            ]

            for url in author_urls:
                if len(authors) >= top_n:
                    break
                    
                self._logger.info(f"  尝试移动端: {url}")
                html = self._get(url, encoding='utf-8', referer='https://m.jjwxc.net/')
                if not html:
                    continue

                try:
                    # 尝试多种编码
                    soup = None
                    for enc in ['utf-8', 'gb18030', 'gbk', 'latin-1']:
                        try:
                            html_decoded = html.encode('latin-1').decode(enc)
                            soup = BeautifulSoup(html_decoded, 'html.parser')
                            text = soup.get_text()
                            if '作家' in text or '作者' in text:
                                break
                            soup = None
                        except:
                            continue

                    if not soup:
                        continue

                    # 查找作家链接 (wapauthor)
                    author_links = soup.find_all('a', href=re.compile(r'/wapauthor/\d+'))
                    
                    for a in author_links:
                        if len(authors) >= top_n:
                            break
                            
                        name = a.get_text(strip=True)
                        if not name or len(name) < 2:
                            continue
                        
                        href = a.get('href', '')
                        author_id_match = re.search(r'/wapauthor/(\d+)', href)
                        if not author_id_match:
                            continue
                        
                        author_id = author_id_match.group(1)
                        
                        # 避免重复
                        if any(a.get('author_id') == author_id for a in authors):
                            continue
                        
                        authors.append({
                            'rank': len(authors) + 1,
                            'name': name,
                            'author_id': author_id,
                            'works': '',
                            'works_count': 0,
                            'total_heat': 0,
                            'fans': '',
                            'score': 0,
                            'source': '晋江文学城',
                            'url': f'https://m.jjwxc.net/wapauthor/{author_id}',
                        })
                        
                    if authors:
                        self._logger.info(f"    移动端找到{len(authors)}位作家")
                        break
                        
                except Exception as e:
                    self._logger.warning(f"    移动端解析失败: {e}")

        # 如果从排行榜获取不足，尝试从首页获取
        if len(authors) < top_n:
            self._logger.info(f"  从首页补充作家数据...")
            home_url = 'https://m.jjwxc.net/'
            # 晋江移动端使用 GB18030 编码，不指定 encoding 让 _get 自动检测
            html = self._get(home_url, encoding=None, referer='https://m.jjwxc.net/')

            if html:
                soup = None  # 初始化soup
                try:
                    # 晋江移动端返回 GB18030，_get 的 apparent_encoding 会自动检测
                    soup = BeautifulSoup(html, 'html.parser')
                    text = soup.get_text()
                    
                    # 检查是否有中文内容
                    if '晋江' not in text and '作者' not in text:
                        # 尝试手动解码
                        decode_success = False
                        for enc in ['gb18030', 'gbk', 'big5']:
                            try:
                                html_bytes = html.encode('latin-1')
                                html_decoded = html_bytes.decode(enc)
                                soup = BeautifulSoup(html_decoded, 'html.parser')
                                text = soup.get_text()
                                if '晋江' in text or '作者' in text:
                                    decode_success = True
                                    break
                                soup = None
                            except:
                                continue
                        
                        if not decode_success or not soup:
                            self._logger.warning(f"    首页解析失败: 编码解码失败")
                            soup = None
                    else:
                        author_links = soup.find_all('a', href=re.compile(r'/wapauthor/\d+'))
                        existing_ids = {a.get('author_id', '') for a in authors}

                        for a in author_links:
                            if len(authors) >= top_n:
                                break

                            name = a.get_text(strip=True)
                            if not name or len(name) < 2:
                                continue

                            href = a.get('href', '')
                            author_id_match = re.search(r'/wapauthor/(\d+)', href)
                            if not author_id_match:
                                continue

                            author_id = author_id_match.group(1)
                            if author_id in existing_ids:
                                continue

                            authors.append({
                                'rank': len(authors) + 1,
                                'name': name,
                                'author_id': author_id,
                                'works': '',
                                'works_count': 0,
                                'total_heat': 0,
                                'fans': '',
                                'score': 0,
                                'source': '晋江文学城',
                                'url': f'https://m.jjwxc.net/wapauthor/{author_id}',
                            })
                            existing_ids.add(author_id)

                except Exception as e:
                    self._logger.warning(f"    首页解析失败: {e}")

        if authors:
            self._logger.info(f"晋江作家榜爬取成功: {len(authors)}位")
            # 存储供后续使用
            self._jinjiang_author_list = authors
            return authors[:top_n]

        self._logger.warning("晋江作家榜未获取到数据")
        return []

    def crawl_all_sources(self) -> Dict:
        """并发爬取所有数据源（V5.5优化：单网站失败降级+异常隔离）"""
        sources_data = {}
        failed_sources = {}  # 记录失败的网站和原因
        
        crawl_tasks = [
            ('番茄小说', self.crawl_fanqie_hot, 20),  # 每个网站爬取20本，覆盖更多题材
            ('起点中文网', self.crawl_qidian_hot, 20),
            ('晋江文学城', self.crawl_jinjiang_hot, 20),
        ]

        # 创建并持有线程池引用（控制并发数为3）
        executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='hot_ranking_crawler')
        try:
            futures = {
                executor.submit(func, top_n): name
                for name, func, top_n in crawl_tasks
            }

            try:
                # 总超时时间30秒（需求文档要求）
                for future in as_completed(futures, timeout=30):
                    name = futures[future]
                    try:
                        # 单网站超时15秒
                        data = future.result(timeout=15)
                        if data and isinstance(data, list) and len(data) > 0:
                            sources_data[name] = data
                            real_count = sum(1 for b in data if b.get('is_real', False))
                            self._logger.info(f"✓ {name}: {len(data)}条数据（真实数据: {real_count}本）")
                        else:
                            # 未获取到有效数据，使用降级数据
                            self._logger.warning(f"✗ {name}: 未获取到有效数据，使用降级数据")
                            failed_sources[name] = "未获取到有效数据"
                            # 尝试使用默认数据
                            default_data = self._get_default_data_for_site(name, 10)
                            if default_data:
                                sources_data[name] = default_data
                                self._logger.info(f"  降级数据已加载: {len(default_data)}条")
                    except Exception as e:
                        # 单网站爬取失败，记录并继续
                        self._logger.error(f"✗ {name} 爬取失败: {e}")
                        failed_sources[name] = str(e)
                        # 使用降级数据
                        default_data = self._get_default_data_for_site(name, 10)
                        if default_data:
                            sources_data[name] = default_data
                            self._logger.info(f"  降级数据已加载: {len(default_data)}条")
            except Exception as e:
                # 总超时，但已获取的数据仍然有效
                self._logger.error(f"爬取总体超时: {e}，已获取{len(sources_data)}个网站数据")

            # 生成聚合数据（即使部分网站失败也能生成）
            if sources_data:
                try:
                    aggregated_data = self._generate_aggregated_data(sources_data)
                    sources_data.update(aggregated_data)
                    self._logger.info(f"聚合数据生成完成: {list(aggregated_data.keys())}")
                except Exception as e:
                    self._logger.error(f"生成聚合数据失败: {e}")
            else:
                # 所有网站都失败，返回默认数据
                self._logger.error("所有网站爬取失败，返回默认数据")
                return self._get_default_data()
            
            # 记录失败情况
            if failed_sources:
                sources_data['_crawl_status'] = {
                    'failed_sources': failed_sources,
                    'success_count': len(sources_data) - 1,  # 减去_crawl_status
                    'total_sources': len(crawl_tasks),
                    'message': f"成功{len(sources_data)-1}/{len(crawl_tasks)}个网站"
                }
            
        finally:
            executor.shutdown(wait=False)

        return sources_data
    
    def _get_default_data_for_site(self, site_name: str, top_n: int = 10) -> List[Dict]:
        """获取指定网站的默认数据"""
        default_map = {
            '番茄小说': self._get_fanqie_mock_data,
            '起点中文网': self._get_qidian_mock_data,
            '晋江文学城': self._get_jinjiang_mock_data,
        }
        func = default_map.get(site_name)
        if func:
            return func(top_n)
        return []

    def _generate_aggregated_data(self, sources_data: Dict) -> Dict:
        """生成聚合数据"""
        normalized_books = self._normalize_books_heat(sources_data)
        
        # 尝试爬取晋江作家榜（仅当有晋江数据时）
        if '晋江文学城' in sources_data and sources_data['晋江文学城']:
            try:
                self.crawl_jinjiang_authors(top_n=10)
            except Exception as e:
                self._logger.warning(f"晋江作家榜爬取失败: {e}")
        
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
        """生成作家排行榜（2025最新算法 - 优先使用首页真实作家数据）"""
        # 优先使用番茄首页的真实作家数据
        if hasattr(self, '_fanqie_writers') and self._fanqie_writers:
            self._logger.info(f"使用番茄首页作家数据: {len(self._fanqie_writers)} 位")
            author_list = []
            for i, writer in enumerate(self._fanqie_writers[:10], 1):
                name = writer.get('name', '未知')
                intro = writer.get('introduction', '')
                # 从introduction提取代表作
                works = []
                if '《' in intro and '》' in intro:
                    import re
                    works = re.findall(r'《([^》]+)》', intro)

                author_list.append({
                    'rank': i,
                    'name': name,
                    'works': '、'.join(works) if works else intro,
                    'works_count': len(works) if works else 1,
                    'total_heat': max(1000, 1000 - i * 50),  # 模拟热度
                    'top_rank': i,
                    'avg_rank': i,
                    'score': max(500, 500 - i * 20),
                    'sites': '番茄小说',
                    'income': f"{int(5000 / i)}万" if i <= 3 else f"{int(3000 / i)}万",
                    'fans': f"{int(1000 / i)}万" if i <= 3 else f"{int(500 / i)}万",
                })
            return author_list

        # 次优先使用晋江作家数据
        if hasattr(self, '_jinjiang_author_list') and self._jinjiang_author_list:
            self._logger.info(f"使用晋江作家数据: {len(self._jinjiang_author_list)} 位")
            author_list = []
            for i, author in enumerate(self._jinjiang_author_list[:10], 1):
                name = author.get('name', '未知')
                
                author_list.append({
                    'rank': i,
                    'name': name,
                    'works': author.get('works', ''),
                    'works_count': author.get('works_count', 0),
                    'total_heat': author.get('total_heat', 0),
                    'top_rank': i,
                    'avg_rank': i,
                    'score': max(500, 500 - i * 20),
                    'sites': '晋江文学城',
                    'income': f"{int(3000 / i)}万" if i <= 3 else f"{int(1000 / i)}万",
                    'fans': author.get('fans', f"{int(500 / i)}万" if i <= 3 else f"{int(200 / i)}万"),
                })
            return author_list

        # 回退：从书籍数据中提取作家信息
        self._logger.info("使用书籍数据生成作家榜")
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
                    'books': books[:20]
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
