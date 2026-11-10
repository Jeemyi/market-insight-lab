#!/usr/bin/env python3
"""MARKET BRIEF: public RSS -> prioritized static daily news briefing.

No AI API, account, or push notification is needed. Briefs are excerpts or
publisher RSS descriptions, never invented generative summaries.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlparse

from xml.etree import ElementTree as ET
import requests
from metrics import fetch_metrics, make_features, demo_feature
from deep_analysis import analyze
from data_research import analyze_data
from editorial import discover_issues
from policy_sources import PRIMARY_SOURCES
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'site' / 'index.html'
TEMPLATE = ROOT / 'template.html'
KST = timezone(timedelta(hours=9))
NOW = lambda: datetime.now(KST)
HEADERS = {'User-Agent': 'MarketBriefReader/1.0 (personal reading; RSS attribution; contact via publisher site)'}

SOURCES = [
    ('한국경제·경제', 'https://www.hankyung.com/feed/economy', 'news'),
    ('한국경제·증권', 'https://www.hankyung.com/feed/finance', 'news'),
    ('한국경제·국제', 'https://www.hankyung.com/feed/international', 'news'),
    ('매일경제·경제', 'https://www.mk.co.kr/rss/30100041/', 'news'),
    ('매일경제·증권', 'https://www.mk.co.kr/rss/50200011/', 'news'),
    ('매일경제·국제', 'https://www.mk.co.kr/rss/30300018/', 'news'),
    ('한국은행·통화정책', 'https://www.bok.or.kr/portal/bbs/P0000559/news.rss?menuNo=200690', 'official'),
    ('한국은행·경제통계', 'https://www.bok.or.kr/portal/bbs/B0000501/news.rss?menuNo=201264', 'official'),
    ('한국은행·금융외환', 'https://www.bok.or.kr/portal/bbs/B0000348/news.rss?menuNo=201109', 'official'),
]

CATEGORIES = [
 ('제도·운용산업', ['스튜어드십','수탁자 책임','의결권','주주관여','국민연금','위탁운용사','운용사 평가','규제 개정','이해상충','준법감시','내부통제','지배구조','금융위원회','금융감독원','ESG','활동보고서','기준가 산정','수탁사','펀드 결제'], 2,
  '제도 자체보다 운용사 평가·자금배정·업무 절차에 어떤 변화를 가져오는지 추론'),
 ('금리·통화정책', ['기준금리', '금통위', '통화정책', '연준', 'fomc', '금리인하', '금리인상', '파월', '금리동결', '한국은행', 'fed', '양적긴축', '금리 경로', '국채금리', '정책금리'], 6,
  '정책금리 기대가 채권금리·주식 할인율에 어떻게 반영되는지 보기'),
 ('거시·경기', ['cpi', '소비자물가', '물가상승률', '인플레이션', 'pce', '고용지표', '실업률', '비농업', 'gdp', '경제성장률', '경기침체', '경기둔화', '경기회복', '수출', '산업생산', '소매판매', 'pmi', '관세', '무역수지', '경상수지', '경기전망'], 5,
  '지표가 예상과 어떻게 달랐고, 성장·물가 전망 중 무엇을 바꾸는지 보기'),
 ('환율·외환', ['원달러', '원/달러', '달러/원', '환율', '달러 강세', '달러 약세', '엔화', '외환시장', '달러인덱스', 'dxy', '환헤지', '환차손', '환차익', '외환보유액', '원화', '환율변동'], 5,
  '환율 방향뿐 아니라 외국인 수급·기업 손익·해외자산 환산 가치 연결하기'),
 ('채권·유동성', ['국채', '채권시장', '회사채', '국고채', '채권금리', '수익률곡선', '장단기금리', '스프레드', '크레딧', '유동성', 'mmf', '단기금리', 'cp금리', '발행금리', '국채입찰', '금리차'], 5,
  '채권가격과 금리의 반대 방향, 신용스프레드·자금 수요 확인하기'),
 ('증시·수급', ['코스피', '코스닥', 's&p500', 's&p 500', '나스닥', '지수', '외국인', '기관', '순매수', '순매도', '증시', '주가하락', '급락', '주가상승', '반등', '반도체', '시장 변동성', 'vix', '주도주'], 4,
  '지수 변동의 원인이 이익 전망·금리·수급 중 어디에 있는지 보기'),
 ('자산운용·ETF', ['etf', '펀드', '자산운용', '운용사', '자금유입', '자금유출', '리밸런싱', '패시브', '액티브', '퇴직연금', '채권형', '공모주', 'mmf', '수탁고', '대차거래'], 4,
  '자금 유출입과 포트폴리오 구성 변화가 실제 운용에 주는 의미 보기'),
]
CAT_DATA = {c[0]: {'terms': c[1], 'boost': c[2], 'question': c[3]} for c in CATEGORIES}
NOISE = ['연예인', '로또', '맛집', '날씨', '야구', '축구', '자동차보험', '결혼', '이혼', '아이돌', '부동산 매물', '유튜버']
CLICKBAIT = ['이 주식', '대박', '초대박', '몰빵', '충격', '폭풍 눈물', '이 종목']
TAG_RE = re.compile(r'<[^>]*>')
SENT_RE = re.compile(r'(?<=[.!?。])\s+|\n+')


def clean(value: str) -> str:
    text = BeautifulSoup(str(value or ''), 'html.parser').get_text(' ', strip=True)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def time_of(entry):
    stamp = getattr(entry, 'published_parsed', None) or getattr(entry, 'updated_parsed', None)
    if stamp:
        try:
            return datetime.fromtimestamp(calendar.timegm(stamp), tz=timezone.utc).astimezone(KST)
        except (ValueError, TypeError, OverflowError):
            pass
    for key in ('published', 'updated'):
        raw = entry.get(key)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                return (dt.replace(tzinfo=timezone.utc) if not dt.tzinfo else dt).astimezone(KST)
            except (TypeError, ValueError, IndexError):
                try:
                    iso = raw.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(iso)
                    return (dt.replace(tzinfo=timezone.utc) if not dt.tzinfo else dt).astimezone(KST)
                except (TypeError, ValueError):
                    pass
    return None


def classify(title: str, desc: str, official: bool):
    t = title.lower()
    d = desc.lower()
    scores = []
    for cat, config in CAT_DATA.items():
        a = sum(1 for keyword in config['terms'] if keyword in t)
        b = sum(1 for keyword in config['terms'] if keyword in d)
        score = a * 3 + min(b, 3) * .45
        scores.append((score, cat))
    scores.sort(reverse=True)
    best, cat = scores[0]
    if best < 2.5:
        return None, -999, []
    related = [name for value, name in scores if value >= 2.5][:3]
    score = best + CAT_DATA[cat]['boost'] + (2.4 if official else 0)
    score += min(2, sum(kw in t for kw in ['전망', '발표', '결정', '변동', '회의', '분석', '전환']))
    # Prefer explanatory reports that compare indicators, mechanisms and risk.
    score += min(3.0, sum(kw in t for kw in ['쏠림', '기여도', '구조', '이유', '배경', '괴리', '역설', '주도', '스프레드', '연결', '변수', '리스크', '확산', '엇갈', '편중', '차이', '비중', '흐름', '위험']) * 1.1)
    if len(related) >= 2: score += 1.3
    score -= 3.0 * sum(k in t for k in NOISE)
    score -= 1.5 * sum(k in t for k in CLICKBAIT)
    # Big-picture focus: one-off stock picks should not beat macro/market mechanics.
    if ('종목' in t or '목표주가' in t or '상한가' in t) and not any(k in t for k in ['코스피', '연준', '반도체', '국채', '수급']):
        score -= 3.8
    return cat, round(score, 2), related


def valid_link(link):
    link = str(link or '').strip()
    parts = urlparse(link)
    return link if parts.scheme in ('http', 'https') and parts.netloc else ''


def normalized_title(title):
    # Remove sensational punctuation but preserve Korean characters & digits.
    return re.sub(r'[^0-9a-z가-힣]', '', title.lower())[:110]


def distinct_enough(s: str, title: str) -> bool:
    if len(s) < 48: return False
    a = normalized_title(s)
    b = normalized_title(title)
    if a and b and (a in b or b in a): return False
    if 'Google 뉴스' in s and '관련 기사' in s: return False
    return True


def feed_item(entry, source, kind, generated_at):
    title = clean(entry.get('title'))
    link = valid_link(entry.get('link'))
    if not title or not link:
        return None
    desc = clean(entry.get('summary') or entry.get('description') or '')
    published = time_of(entry)
    if not published: return None  # Do not label undated content as today's news.
    if published > generated_at + timedelta(hours=2): return None
    if published < generated_at - timedelta(days=7): return None
    cat, score, tags = classify(title, desc, kind == 'official')
    if not cat or score < 4: return None
    if generated_at - published <= timedelta(hours=30): score += 2.5
    elif generated_at - published <= timedelta(hours=54): score += 1.0
    if not distinct_enough(desc, title): desc = ''
    article_id = hashlib.sha1(link.encode('utf-8')).hexdigest()[:16]
    return {
        'id': article_id, 'title': title, 'url': link, 'source': source,
        'published': published.isoformat(timespec='minutes'), 'timestamp': int(published.timestamp()),
        'category': cat, 'tags': tags, 'score': round(score, 1),
        'summary': truncate(desc, 290) if desc else '',
        'summary_type': 'RSS 소개문' if desc else '없음',
        'question': CAT_DATA[cat]['question'], 'official': kind == 'official',
    }


def truncate(s, limit=300):
    if len(s) <= limit: return s
    return s[:limit].rsplit(' ', 1)[0].rstrip(' ,.;') + '…'



def parse_feed(content: bytes):
    """Parse standard RSS 2.0 and Atom feeds using only Python's stdlib."""
    root = ET.fromstring(content)
    # RSS item or Atom entry
    entries = [node for node in root.iter() if node.tag.rsplit('}', 1)[-1] in ('item', 'entry')]
    values = []
    for node in entries:
        result = {}
        for child in node:
            name = child.tag.rsplit('}', 1)[-1]
            if name == 'link':
                href = child.attrib.get('href')
                if href and child.attrib.get('rel', 'alternate') in ('alternate', ''):
                    result['link'] = href
                elif child.text and not result.get('link'):
                    result['link'] = child.text.strip()
            elif name in ('title', 'description', 'summary', 'published', 'updated', 'pubDate', 'date', 'encoded'):
                raw = ''.join(child.itertext()).strip()
                key = {'pubDate': 'published', 'description':'description', 'date':'published', 'encoded':'description'}.get(name, name)
                if raw and (key not in result or key == 'summary'):
                    result[key] = raw
        if result.get('title') and result.get('link'):
            values.append(result)
    return values

def fetch_source(source):
    label, url, kind = source
    try:
        response = requests.get(url, timeout=14, headers=HEADERS)
        response.raise_for_status()
        entries = parse_feed(response.content)
        if not entries: raise ValueError('RSS 항목 없음')
        return label, kind, entries[:90], None
    except Exception as exc:
        return label, kind, [], str(exc)[:130]


def extract_body(url):
    # Public pages only. No authentication bypass, paywall circumvention or scraping at scale.
    if 'news.google.com' in url: return ''
    try:
        res = requests.get(url, timeout=7, headers=HEADERS)
        res.raise_for_status()
        if not ('text/html' in res.headers.get('content-type', 'text/html')): return ''
        if len(res.content) > 1_500_000: return ''
        soup = BeautifulSoup(res.text, 'html.parser')
        for tag in soup.select('script,style,nav,footer,aside,form,header,.ad,.advertisement,.related-article'):
            tag.decompose()
        sections = ['#article-body', '#article_body', '#articleBody', '#articletxt',
                    '#newsView', '.news_cnt_detail_wrap', '.article-body', '.article_body',
                    '.article_view', '[itemprop="articleBody"]', 'article']
        for selector in sections:
            node = soup.select_one(selector)
            if not node: continue
            p = [clean(str(x)) for x in node.find_all('p')]
            p = [x for x in p if 50 <= len(x) <= 700 and '기자' not in x[:10]]
            text = ' '.join(p[:9]) if p else clean(str(node))
            if len(text) > 160:
                return text[:3500]
        meta = soup.select_one('meta[property="og:description"]') or soup.select_one('meta[name="description"]')
        return clean(meta.get('content', '')) if meta else ''
    except Exception:
        return ''


def brief_from_text(text, title):
    text = clean(text)
    if not distinct_enough(text, title): return ''
    sentences = re.split(r'(?<=[.!?。])\s+|\s*(?<=다\.)\s*', text)
    sentences = [s.strip() for s in sentences if 37 <= len(s.strip()) <= 290]
    if not sentences:
        return truncate(text, 245)
    terms = set(re.findall(r'[가-힣a-zA-Z0-9]{2,}', title.lower()))
    scored = []
    for index, sentence in enumerate(sentences[:18]):
        words = set(re.findall(r'[가-힣a-zA-Z0-9]{2,}', sentence.lower()))
        score = (len(words & terms) / max(1, len(terms))) * 5 + (2 / (1 + index / 3))
        if re.search(r'\d', sentence): score += .4
        scored.append((score, index, sentence))
    chosen = sorted(sorted(scored, reverse=True)[:2], key=lambda x: x[1])
    excerpt = ' '.join(x[2] for x in chosen)
    return truncate(excerpt, 300)


def deduplicate(items):
    unique = []
    seen_urls = set()
    seen_titles = []
    from difflib import SequenceMatcher
    for item in sorted(items, key=lambda x: (x['score'], x['timestamp']), reverse=True):
        title = normalized_title(item['title'])
        if item['url'] in seen_urls: continue
        if any((title in prev or prev in title) and min(len(title), len(prev)) >= 20 or
               SequenceMatcher(None, title, prev).ratio() > .88 for prev in seen_titles):
            continue
        seen_urls.add(item['url'])
        seen_titles.append(title)
        unique.append(item)
    return unique


def choose(items, limit=44):
    # Round-robin category coverage means important but less-reported themes surface.
    buckets = {cat[0]: [] for cat in CATEGORIES}
    for item in items:
        buckets[item['category']].append(item)
    for values in buckets.values():
        values.sort(key=lambda x: (x['score'], x['timestamp']), reverse=True)
    chosen, per_source = [], {}
    while len(chosen) < limit:
        next_round = []
        for cat, *_ in CATEGORIES:
            options = buckets[cat]
            if options:
                candidate = options.pop(0)
                # Cap domination by one publisher only for front-page selection.
                if len(chosen) < 16 and per_source.get(candidate['source'], 0) >= 7:
                    options.append(candidate)
                    continue
                next_round.append(candidate)
        if not next_round: break
        next_round.sort(key=lambda i: (i['score'], i['timestamp']), reverse=True)
        for item in next_round:
            if len(chosen) >= limit: break
            chosen.append(item)
            per_source[item['source']] = per_source.get(item['source'], 0) + 1
    return chosen


def build_data(demo=False):
    now = NOW()
    if demo:
        samples = [
            ('금리·통화정책', '중앙은행 기준금리 결정과 채권시장 영향 살펴보기', '시장의 관심은 금리 결정 자체뿐 아니라 향후 금리 경로에 모입니다. 결정문과 시장 금리의 움직임을 나란히 비교해 보는 연습용 콘텐츠입니다.'),
            ('환율·외환', '원/달러 환율과 외국인 자금 흐름의 연결 고리', '환율은 해외 자산의 원화 환산 가치와 외국인 투자자의 수익률에 영향을 줍니다. 환율 방향과 증시 수급이 함께 움직이는지 확인해 보세요.'),
            ('거시·경기', '미국 물가와 고용지표를 함께 읽는 방법', '물가가 예상보다 높아도 고용 상황이 약하면 정책 해석이 달라질 수 있습니다. 실제 수치와 시장 예상치의 차이를 우선 확인하세요.'),
            ('증시·수급', '지수 등락 뒤에 숨은 외국인·기관 수급', '코스피 지수가 움직였다는 사실보다 어느 투자자가 어떤 업종을 샀는지 확인하는 연습입니다. 특정 날짜의 실제 시장 기사 내용은 아닙니다.'),
            ('채권·유동성', '국고채 금리와 회사채 스프레드 비교', '국고채와 회사채의 금리 차이는 시장의 위험 선호도를 해석하는 단서가 됩니다. 차이가 확대되거나 축소된 원인을 찾아보세요.'),
            ('자산운용·ETF', 'ETF 자금 유입으로 읽는 투자자 선택', '자금이 유입되는 자산군과 실제 수익률 상승은 항상 같지 않습니다. 자산별 자금 흐름과 지수 구성의 차이를 확인해 보세요.'),
        ]
        articles=[]
        for n, (cat, title, summary) in enumerate(samples):
            articles.append({'id':f'demo-{n}', 'title': title, 'url':'', 'source':'데모 예시',
             'published': (now-timedelta(hours=n)).isoformat(timespec='minutes'), 'timestamp':int((now-timedelta(hours=n)).timestamp()),
             'category':cat,'tags':[cat],'score':10-n*.5, 'summary':summary, 'summary_type':'데모 텍스트',
             'question':CAT_DATA[cat]['question'],'official':False,'demo':True})
        # Fictional independent-source articles to test cross-source issue discovery.
        # They are *never* passed off as actual market news.
        mock_stories = [
            ('금리·통화정책','가상매체 A','연준 금리 인하 전망과 장기국채 금리의 다른 방향', '시장 참가자들은 금리 경로와 재정 부담을 별개 요인으로 평가했다는 가상의 사례입니다.'),
            ('채권·유동성','가상매체 B','미국 국채 발행 물량과 장기금리 기간프리미엄 점검', '가상의 두 번째 기사입니다. 국채 수급과 물가 전망을 구분해 보는 것이 핵심입니다.'),
            ('증시·수급','가상매체 C','코스피 반도체 종목 쏠림과 외국인 매매의 연결', '가상의 기사입니다. 주가지수 등락과 상승 종목 수의 차이를 따져봅니다.'),
            ('환율·외환','가상매체 D','달러 강세와 한국 주식시장의 외국인 순매도 비교', '가상의 기사입니다. 달러·원화·외국인 자금의 공통 원인을 생각해 봅니다.'),
            ('거시·경기','가상매체 E','소비자물가 예상과 성장 전망의 차이가 채권에 미치는 효과', '가상 기사로, 물가와 고용의 예상치 차이를 비교해 봅니다.'),
            ('금리·통화정책','가상매체 F','고용 둔화에도 국채금리가 반등한 이유에 대한 시장 해석', '가상 기사로, 중앙은행 기대와 장기채 수급 설명을 나란히 검토합니다.'),
        ]
        for n,(cat,source,title,summary) in enumerate(mock_stories):
            articles.append({'id':f'demo-research-{n}', 'title':title,'url':'','source':source,
             'published':(now-timedelta(hours=n+1)).isoformat(timespec='minutes'),
             'timestamp':int((now-timedelta(hours=n+1)).timestamp()),
             'category':cat,'tags':[cat],'score':17-n*.4,'summary':summary,
             'summary_type':'가상 기사 (시연용)','question':'교차 검증할 지표·경로를 정해보기',
             'official':False,'demo':True})
        # Extra clearly fictional titles make clustering visible in an offline demo.
        articles.extend([
            {'id':'demo-concentration','title':'연습 사례: 대형주가 지수에 미치는 비중과 상승 종목 수','url':'','source':'가상 기사 · 데이터 없음',
             'published':now.isoformat(timespec='minutes'),'timestamp':int(now.timestamp()),'category':'증시·수급','tags':['증시·수급'],'score':11,
             'summary':'시가총액가중 지수의 움직임과 실제 상승종목 수를 함께 확인한다는 가상의 교육 사례입니다. 실제 오늘의 통계는 아닙니다.',
             'summary_type':'학습 예시','official':False,'demo':True},
            {'id':'demo-rates','title':'연습 사례: 고용·물가 지표와 연준 금리 기대','url':'','source':'가상 기사 · 데이터 없음',
             'published':now.isoformat(timespec='minutes'),'timestamp':int(now.timestamp()),'category':'금리·통화정책','tags':['금리·통화정책'],'score':11,
             'summary':'경제지표와 예상 차이가 채권금리에 어떻게 반영될 수 있는지 배우는 예시입니다.',
             'summary_type':'학습 예시','official':False,'demo':True},
        ])
        demo_features=[demo_feature()]
        return {'generated_at':now.isoformat(timespec='minutes'),'articles':articles,
                'issue_candidates':discover_issues(articles, demo_features, now),
                'insights':[], 'deep_reports':[], 'deep_status':'시연 데이터: 실제 AI 분석은 포함하지 않음', 'data_reports':[], 'data_ai_status':'시연 데이터: AI 생성 없음', 'features':demo_features, 'analysis_status':'과거 수치 사례 · 오늘의 실시간 수치 아님',
                'sources_ok':0,'sources_total':len(SOURCES),'errors':[], 'demo':True, 'policy_sources':[]}

    statuses=[]
    items=[]
    with ThreadPoolExecutor(max_workers=7) as pool:
        futures = [pool.submit(fetch_source, source) for source in SOURCES]
        for future in as_completed(futures):
            label,kind,entries,error = future.result()
            statuses.append((label,error))
            for entry in entries:
                item = feed_item(entry,label,kind,now)
                if item: items.append(item)
    candidates=deduplicate(items)
    selected=choose(candidates)
    # Fetch a modest number of public article pages; never make up a summary.
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures={pool.submit(extract_body, item['url']): item for item in selected[:30]
                 if not item['summary'] or len(item['summary']) < 145}
        for future in as_completed(futures):
            item=futures[future]
            body=future.result()
            snippet=brief_from_text(body,item['title'])
            if snippet and len(snippet) > len(item['summary']):
                item['summary']=snippet
                item['summary_type']='공개 본문 발췌'
    errors=[f'{label}: {error}' for label,error in statuses if error]
    if not selected:  # preserve truthful status; do not publish fictional 'latest' stories
        return {'generated_at':now.isoformat(timespec='minutes'),'articles':[],
                'insights':[], 'issue_candidates':[], 'deep_reports':[], 'deep_status':'수집 데이터 부족으로 교차분석 보류', 'data_reports':[], 'data_ai_status':'수집 지표 없음', 'features':[], 'analysis_status':'분석 보류: 수집된 기사 없음', 'sources_ok':len(SOURCES)-len(errors),'sources_total':len(SOURCES),'errors':errors,'demo':False, 'policy_sources':PRIMARY_SOURCES}
    # Evidence first: never headline a pre-written textbook explanation.
    series, series_errors = fetch_metrics(now)
    features = make_features(series, selected, now)
    issue_candidates=discover_issues(selected, features, now)
    deep_reports, deep_status = analyze(selected, features, now, issue_candidates)
    data_reports, data_ai_status = analyze_data(features, selected, deep_reports, now)
    analysis_status = (f'실제 수치 기반 {len(features)}건 · FRED {len(series)}/6개 시계열 · ' +
                       ('지표 일부 미확보' if series_errors else '지표 수집 완료'))
    return {'generated_at':now.isoformat(timespec='minutes'),'articles':selected,
            'insights':[], 'issue_candidates':issue_candidates, 'deep_reports':deep_reports, 'deep_status':deep_status, 'data_reports':data_reports, 'data_ai_status':data_ai_status, 'features':features, 'analysis_status':analysis_status,
            'metric_errors':series_errors,
            'sources_ok':len(SOURCES)-len(errors),'sources_total':len(SOURCES),'errors':errors,'demo':False, 'policy_sources':PRIMARY_SOURCES}


def publish(data):
    template=TEMPLATE.read_text(encoding='utf-8')
    serialized=json.dumps(data, ensure_ascii=False, separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    assert '/*__INITIAL_DATA__*/' in template
    page=template.replace('/*__INITIAL_DATA__*/', f'const NEWS_DATA={serialized};')
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(page,encoding='utf-8')
    (ROOT/'site'/'data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Created:',OUT, 'stories:',len(data['articles']),'feed sources OK:',data['sources_ok'],'/',data['sources_total'])
    if data['errors']:
        print('Unavailable sources:',*data['errors'],sep='\n - ')
    return 0


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='Generate clearly labeled offline demonstration (not live news)')
    args=parser.parse_args()
    return publish(build_data(demo=args.demo))

if __name__ == '__main__':
    sys.exit(main())
