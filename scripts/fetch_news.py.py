#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日资讯抓取脚本
每天 09:00 北京时间由 GitHub Actions 自动执行
抓取 Google News RSS → 翻译为中文 → 生成 JSON → 提交仓库
"""

import feedparser
import json
import time
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False
    print("⚠️  deep-translator 未安装，将保留英文原文")

CST = timezone(timedelta(hours=8))


# ── 翻译 ────────────────────────────────────────────────────

def translate_zh(text, max_len=450):
    if not text or not text.strip():
        return ''
    text = text[:max_len].strip()
    if not HAS_TRANSLATOR:
        return text
    for attempt in range(3):
        try:
            result = GoogleTranslator(source='auto', target='zh-CN').translate(text)
            return result or text
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"    ⚠️  翻译失败: {e}")
                return text


# ── 文本处理 ────────────────────────────────────────────────

def clean_html(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    for src, dst in [('&amp;','&'),('&lt;','<'),('&gt;','>'),('&quot;','"'),('&#39;',"'"),('&nbsp;',' ')]:
        text = text.replace(src, dst)
    return re.sub(r'\s+', ' ', text).strip()


def clean_title(title):
    """去掉 Google News 标题末尾的来源，如 ' - TechRadar'"""
    return re.sub(r'\s[-–]\s[^-–]{1,80}$', '', title or '').strip()


# ── 地区识别 ────────────────────────────────────────────────

def detect_regions(text):
    t = (text or '').lower()
    region_map = [
        (['united states', 'amazon.com', ' usa', 'north america'],           '🇺🇸 美国'),
        (['united kingdom', 'amazon.co.uk', ' uk ', 'britain'],               '🇬🇧 英国'),
        (['germany', 'amazon.de', 'deutschland'],                             '🇩🇪 德国'),
        (['japan', 'amazon.co.jp'],                                           '🇯🇵 日本'),
        (['france', 'amazon.fr'],                                             '🇫🇷 法国'),
        (['canada', 'amazon.ca'],                                             '🇨🇦 加拿大'),
        (['australia', 'amazon.com.au'],                                      '🇦🇺 澳大利亚'),
        (['korea', 'coupang'],                                                '🇰🇷 韩国'),
        (['shopee','lazada','singapore','thailand','malaysia',
          'philippines','vietnam','indonesia','southeast asia'],               '🌏 东南亚'),
        (['mercado libre', 'mexico', 'brazil', 'latin america'],              '🌎 拉丁美洲'),
        (['middle east', 'uae', 'saudi', 'dubai'],                            '🌙 中东'),
        (['china', 'jd.com', 'tmall', 'taobao', 'douyin'],                   '🇨🇳 中国'),
        (['europe', 'european'],                                              '🇪🇺 欧洲'),
        (['india', 'amazon.in'],                                              '🇮🇳 印度'),
        (['global', 'worldwide', 'international'],                            '🌍 全球'),
    ]
    found = []
    for keys, tag in region_map:
        if any(k in t for k in keys):
            found.append(tag)
    return found or ['🌍 全球']


# ── 资讯类型识别 ────────────────────────────────────────────

def detect_type(text):
    t = (text or '').lower()
    if any(k in t for k in ['launch', 'release', 'unveil', 'announce', 'new model',
                             'debut', 'reveal', 'introduces', 'coming soon']):
        return '🚀 新品发布'
    if any(k in t for k in ['prime day', 'sale', 'deal', 'discount', 'promotion',
                             'coupon', 'offer', 'black friday', 'holiday']):
        return '📢 促销活动'
    if any(k in t for k in ['game', 'gaming', 'gameplay', 'dlc', 'update',
                             'patch', 'sequel', 'exclusive', 'title']):
        return '🎮 游戏动态'
    if any(k in t for k in ['market', 'trend', 'growth', 'forecast', 'revenue',
                             'shipment', 'industry', 'analyst', 'report']):
        return '📊 市场动态'
    if any(k in t for k in ['tariff', 'ban', 'regulation', 'recall', 'safety',
                             'policy', 'law', 'standard', 'certification']):
        return '⚠️ 政策法规'
    if any(k in t for k in ['partner', 'collab', 'license', 'acquisition',
                             'merger', 'invest', 'fund']):
        return '🤝 品牌合作'
    if any(k in t for k in ['review', 'best', 'compare', 'guide', 'recommend',
                             'test', 'rating']):
        return '📋 评测推荐'
    return '📰 行业资讯'


# ── 日期格式化 ──────────────────────────────────────────────

def fmt_date(entry):
    try:
        pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return pub.astimezone(CST).strftime('%m/%d %H:%M')
    except Exception:
        return ''


def get_source(entry):
    if hasattr(entry, 'source') and entry.source:
        return entry.source.get('title', '')
    return ''


# ── 抓取单版块 ──────────────────────────────────────────────

def fetch_section(query, max_items=4):
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    print(f"  🔍 {query[:65]}")
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            print("     ⚠️  无结果")
            return []

        items = []
        for entry in feed.entries[:max_items]:
            title_raw = clean_title(entry.get('title', ''))
            desc_raw  = clean_html(entry.get('summary', ''))[:400]
            full_text = title_raw + ' ' + desc_raw

            print(f"    → {title_raw[:55]}...")
            title_zh = translate_zh(title_raw)
            time.sleep(0.7)
            desc_zh  = translate_zh(desc_raw[:300]) if desc_raw else ''
            time.sleep(0.7)

            items.append({
                'title':   title_zh or title_raw,
                'link':    entry.get('link', '#'),
                'date':    fmt_date(entry),
                'source':  get_source(entry),
                'type':    detect_type(full_text),
                'summary': desc_zh or desc_raw[:150],
                'regions': detect_regions(full_text),
            })
        return items

    except Exception as e:
        print(f"  ❌ 抓取失败: {e}")
        return []


# ── 版块配置：JSAUX ─────────────────────────────────────────

JSAUX_SECTIONS = [
    {
        'id': 'nintendo', 'title': 'Nintendo Switch', 'icon': '🕹️',
        'badge': '核心赛道', 'sub': '主机生态 · 新品发布 · 配件趋势', 'theme': 'theme-nintendo',
        'query': 'Nintendo Switch 2 accessories games release launch 2026',
        'tips': [
            '新款主机发布后3个月内是配件黄金期，提前布局屏幕保护贴、保护套、底座等核心SKU',
            '日本、美国、欧洲是Switch三大主力市场，优先保障Amazon US/JP/DE备货',
            'TikTok/YouTube上的Switch开箱评测是流量高峰节点，同步启动达人合作',
        ]
    },
    {
        'id': 'valve', 'title': 'Valve / Steam', 'icon': '🖥️',
        'badge': '上市进行中', 'sub': 'Steam Machine · Steam Frame VR · Steam Controller', 'theme': 'theme-valve',
        'query': 'Valve "Steam Machine" OR "Steam Controller" OR "Steam Frame" hardware 2026',
        'tips': [
            'Steam Controller已上市，配套收纳袋/硅胶套/充电底座是当前蓝海，建议快速立项',
            'JSAUX已宣布Steam Machine配件支持计划，需提前布局扩展坞/HDMI线/USB-C线SKU',
            'Steam Frame VR上市后，VR配件可与Quest系列共线开发，降低研发成本',
        ]
    },
    {
        'id': 'nex', 'title': 'NEX Playground', 'icon': '🎯',
        'badge': '新兴机会', 'sub': '体感游戏 · 家庭市场 · 配件机会', 'theme': 'theme-nex',
        'query': '"NEX Playground" gaming console Mattel accessories',
        'tips': [
            '65万台用户基数，配件市场尚早期，先发布局具备显著竞争优势',
            '英国等欧洲市场2026年新开，可与亚马逊欧洲站同步上架配件SKU',
            '夏季联名大游上线是推广窗口，借势做Listing流量',
        ]
    },
    {
        'id': 'pixel', 'title': 'Google Pixel', 'icon': '📱',
        'badge': '手机配件', 'sub': 'Pixel手机 · 配件生态 · 新机发布', 'theme': 'theme-pixel',
        'query': 'Google Pixel smartphone accessories launch release 2026',
        'tips': [
            'Pixel新机发布（通常每年秋季）前后3个月是配件销售黄金期，提前60天上架',
            'Pixel用户偏极客，对配件兼容性和材质要求高，需强调品质背书',
            '桌面模式功能推动USB-C扩展坞需求，与JSAUX线材品类高度协同',
        ]
    },
    {
        'id': 'vr', 'title': 'VR 设备配件', 'icon': '🥽',
        'badge': '新兴赛道', 'sub': 'Meta Quest 3/3S · 头戴绑带 · 充电坞', 'theme': 'theme-vr',
        'query': 'Meta Quest VR headset accessories gaming 2026',
        'tips': [
            'Meta Quest 3/3S是当前VR配件最大增量市场，头带、面罩、充电底座是核心SKU',
            'VR配件复购率高，优先建立价格优势，自然流量最稳定',
            '美国占全球VR设备销量约45%，Amazon US是主战场',
        ]
    },
    {
        'id': 'handheld', 'title': '游戏掌机', 'icon': '🎮',
        'badge': '新品机会', 'sub': 'ROG Ally · Lenovo Legion · 新兴掌机', 'theme': 'theme-handheld',
        'query': 'gaming handheld console "ROG Ally" OR "Lenovo Legion Go" OR AYANEO release 2026',
        'tips': [
            '掌机配件市场高速增长，JSAUX已是Steam Deck配件TOP品牌，可复制打法',
            '新掌机发布首月是抢占Listing的黄金窗口，需在发布前90天做好选品准备',
            '掌机用户黏性高，保护套+散热底座+充电线三件套是标配组合SKU',
        ]
    },
    {
        'id': 'cables', 'title': '线材 & 充电配件', 'icon': '🔌',
        'badge': '基础品类', 'sub': 'USB-C · HDMI · DP · 充电 · 传输 · 视频 · 音频', 'theme': 'theme-cables',
        'query': 'USB-C HDMI DisplayPort cable wireless charging market industry trend 2026',
        'tips': [
            'USB4/Thunderbolt 5认证是线材溢价核心，建议快速拿证，在标题中突出显示',
            'HDMI 2.1线材需求持续增长，4K/120Hz和8K游戏电视普及是主要驱动力',
            '无线充市场差评集中于充电慢/过热，改善这两点可显著提升评分和复购',
        ]
    },
]

# ── 版块配置：Aecooly ───────────────────────────────────────

AECOOLY_SECTIONS = [
    {
        'id': 'market', 'title': '便携风扇市场趋势', 'icon': '📊',
        'badge': '市场洞察', 'sub': '市场规模 · 增长率 · 品类机会', 'theme': 'theme-fan',
        'query': 'portable fan mini fan market trend consumer growth 2026',
        'tips': [
            '全球便携风扇市场CAGR约7.56%，夏季旺季布局窗口已开，现在是广告预算加码时机',
            'USB充电款&无叶片款增速最快，消费者愿意为静音/安全/设计感溢价30-50%',
            '北美、东南亚、中东为三大核心增量市场，优先保障Amazon US/JP及Shopee库存',
        ]
    },
    {
        'id': 'compete', 'title': '竞争对手动态', 'icon': '🔍',
        'badge': '竞品监控', 'sub': '主要竞品 · 新品上架 · 价格变动', 'theme': 'theme-compete',
        'query': 'portable neck fan cooling fan Amazon bestseller Dyson new launch 2026',
        'tips': [
            'JISULIFE、OPOLAR、EasyAcc为亚马逊便携风扇核心竞品，定期追踪其BSR和review变动',
            '竞品集中发力颈挂款&桌面款，差异化机会在：超长续航（50h+）、静音（30dB以下）、多合一',
            'TikTok Shop竞品达人投流明显加速，KOC内容种草是性价比最高的反制手段',
        ]
    },
    {
        'id': 'platform', 'title': '平台运营要点', 'icon': '🛒',
        'badge': '运营情报', 'sub': 'Amazon · Shopee · TikTok · 抖音 · 京东', 'theme': 'theme-platform',
        'query': 'Amazon "Prime Day" summer promotion Shopee TikTok ecommerce 2026',
        'tips': [
            'Amazon：Prime Day窗口临近（预计7月），现在是最后FBA备货窗口，US/UK/DE优先补库',
            'Shopee：东南亚5月促销节密集，直播+Flash Deal组合效果最佳',
            'Mercado Libre：巴西、墨西哥旺季，与北半球并行，需差异化备货策略',
        ]
    },
    {
        'id': 'trend', 'title': '夏季消费趋势', 'icon': '☀️',
        'badge': '趋势预警', 'sub': '热点场景 · 用户需求 · 新兴品类', 'theme': 'theme-trend',
        'query': 'summer heatwave portable cooling fan consumer outdoor trend 2026',
        'tips': [
            '全球极端高温天气频发，"随身降温"需求从可选变刚需，消费者复购率和口碑传播效应增强',
            '户外运动场景（徒步/露营/骑行）带动大容量电池风扇需求，建议开发户外专属款',
            '宠物风扇、宝宝车风扇成新蓝海品类，竞争较弱但搜索量快速上升',
        ]
    },
]

# ── 主程序 ──────────────────────────────────────────────────

def generate_data(sections, output_file, brand_label):
    now_cst = datetime.now(CST)
    data = {
        'updated': now_cst.strftime('%Y-%m-%d %H:%M'),
        'brand':   brand_label,
        'sections': []
    }
    for sec in sections:
        print(f"\n【{sec['title']}】")
        items = fetch_section(sec['query'])
        data['sections'].append({
            'id':    sec['id'],
            'title': sec['title'],
            'icon':  sec['icon'],
            'badge': sec['badge'],
            'sub':   sec['sub'],
            'theme': sec['theme'],
            'tips':  sec['tips'],
            'items': items,
        })
        time.sleep(1.5)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    total = sum(len(s['items']) for s in data['sections'])
    print(f"\n✅ 已生成 {output_file}（{len(data['sections'])} 版块，共 {total} 条资讯）")


if __name__ == '__main__':
    print("=" * 55)
    print("JSAUX 每日资讯抓取")
    print("=" * 55)
    generate_data(JSAUX_SECTIONS, 'jsaux-data.json', 'JSAUX')

    print("\n" + "=" * 55)
    print("Aecooly 每日资讯抓取")
    print("=" * 55)
    generate_data(AECOOLY_SECTIONS, 'aecooly-data.json', 'Aecooly')

    print("\n🎉 全部完成！")
    sys.exit(0)
