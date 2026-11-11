"""Two-pass, source-attributed public research for MARKET INSIGHT LAB.

The Responses web-search output is *not* treated as verified original reporting.
Only individual URL-cited paragraphs enter the candidate evidence pool; the
analysis validator remains responsible for rejecting unsupported reports.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

API_URL = 'https://api.openai.com/v1/responses'
DISCOVERY_QUERIES = [
    '한국은행 기준금리 금통위 결정', 'Federal Reserve FOMC statement rates',
    '미국 CPI PCE 물가 발표', '미국 고용 실업률 발표',
    '한국 소비자물가 고용 경기', '한국 GDP 수출 산업생산',
    '미국 국채 2년 10년 금리 입찰', '한국 국고채 3년 10년 금리',
    '한국 회사채 신용스프레드 CP 시장', '미국 high yield credit spreads',
    '달러 원 환율 외국인 수급', '미국 달러지수 엔화 환율',
    '코스피 외국인 기관 업종별 매매', 'KRX 상승종목 하락종목 지수',
    'S&P 500 Nasdaq earnings sectors', '삼성전자 SK하이닉스 실적 반도체',
    'ETF 자금 유입 채권형 MMF', '한국 IPO 공모주 수요예측',
    '기업 실적 발표 영업이익 전망', '한국 금융위원회 제도 개정',
    '금융감독원 펀드 운용 규제', '기업 주주환원 의결권 스튜어드십',
]
SOURCE_HINTS = ('Federal Reserve', 'BLS', 'Treasury', 'FRED', 'BOK', 'KRX',
                '금융위원회', '금융감독원', '금융투자협회', '통계청', 'DART')
EVENT_STOP = {'속보','단독','종합','기사','뉴스','전망','발표','국내','해외','이유','이슈','최근',
              '장중','마감','급등','급락','주목','확인','따르면','today','market','latest'}


def event_phrase(title: str) -> str:
    """Turn a real headline into a short separate follow-up search intent."""
    words = re.findall(r'[A-Za-z가-힣][A-Za-z가-힣0-9·.-]*', str(title or ''))
    words = [word for word in words if len(word) > 1 and word.casefold() not in EVENT_STOP]
    return ' '.join(words[:6])


def choose_leads(articles: list, maximum: int = 18) -> list:
    """Keep multiple incidents from important categories rather than 1/category."""
    pool = sorted(articles, key=lambda a: (a.get('score', 0), a.get('timestamp', 0)), reverse=True)
    result, used, counts = [], set(), Counter()
    for minimum in (2, 4):
        for article in pool:
            ident = article.get('id')
            category = article.get('category', '')
            if not ident or ident in used or counts[category] >= minimum:
                continue
            result.append(article)
            used.add(ident)
            counts[category] += 1
            if len(result) >= maximum:
                return result
    return result


def query_plan(articles: list, features: list, focus_issues: list | None = None) -> list[str]:
    leads = choose_leads(articles)
    queries = []
    if focus_issues:
        selected = {aid for issue in focus_issues[:5] for aid in issue.get('article_ids', [])[:5]}
        for article in leads:
            if article.get('id') in selected:
                phrase = event_phrase(article.get('title', ''))
                if phrase:
                    queries.append(phrase)
        for issue in focus_issues[:5]:
            theme = issue.get('theme', '')
            if theme:
                queries.append(theme + ' 최신 공식 통계')
        for f in features[:4]:
            label = str(f.get('name', '')).strip()
            if label:
                queries.append(label + ' 관측값 기간 비교')
        # A major event can be absent from keyword clusters; still search it.
        queries.extend(event_phrase(a.get('title', '')) for a in leads[:7])
    else:
        queries.extend(event_phrase(a.get('title', '')) for a in leads[:7])
        queries.extend(DISCOVERY_QUERIES)
        for f in features[:3]:
            label = str(f.get('name', '')).strip()
            if label:
                queries.append(label + ' 공식 시계열')
    return list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:32]


def source_url(value: str) -> str:
    """Strip common tracking parameters; preserve original source URLs."""
    try:
        parsed = urlparse(str(value).strip())
        if parsed.scheme not in ('https', 'http') or not parsed.netloc:
            return ''
        if parsed.netloc.lower().endswith(('news.google.com', 'google.com', 'bing.com')):
            return ''
        params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                  if not k.casefold().startswith('utm_') and k.casefold() not in ('fbclid', 'gclid')]
        return urlunparse(parsed._replace(query=urlencode(params), fragment=''))
    except (ValueError, TypeError):
        return ''


def classify_citation(title: str, excerpt: str):
    """Check each cited paragraph itself, never the unrelated query's category."""
    # This is imported lazily to avoid circular dependencies (build imports us).
    from build import classify
    category, score, _ = classify(str(title), str(excerpt), False)
    # A lone reference to 'stock' or 'bank' without a market event is weak.
    return category if category and score >= 4 else None


def cited_articles(output: dict, now: datetime, maximum: int = 24) -> list[dict]:
    collected, urls = [], set()
    for message in output.get('output', []):
        if message.get('type') != 'message':
            continue
        for part in message.get('content', []):
            if part.get('type') != 'output_text':
                continue
            full = part.get('text', '')
            if not isinstance(full, str):
                continue
            for note in part.get('annotations', []):
                if note.get('type') != 'url_citation':
                    continue
                link = source_url(note.get('url', ''))
                if not link or link in urls:
                    continue
                pos = note.get('start_index')
                if not isinstance(pos, int) or pos < 0 or pos > len(full):
                    continue
                lo = full.rfind('\n', 0, pos) + 1
                hi = full.find('\n', pos)
                excerpt = full[lo:hi if hi >= 0 else len(full)].strip()
                # If the citation is at the start of a newline, use the prior line.
                if len(excerpt) < 40 and lo > 0:
                    prev = full.rfind('\n', 0, lo - 1) + 1
                    excerpt = full[prev:hi if hi >= 0 else len(full)].strip()
                excerpt = re.sub(r'\s+', ' ', excerpt)[:1100]
                if len(excerpt) < 40:
                    continue
                title = str(note.get('title') or '공개 자료').strip()[:180]
                category = classify_citation(title, excerpt)
                if not category:
                    continue
                host = urlparse(link).netloc.lower().removeprefix('www.')
                urls.add(link)
                article_id = hashlib.sha1(link.encode()).hexdigest()[:16]
                collected.append({
                    'id': article_id, 'title': title, 'url': link, 'source': host,
                    # A search citation carries NO verified publication date.
                    'published': '발행일 미확인', 'timestamp': 0,
                    'category': category, 'tags': [category], 'score': 9.5,
                    'summary': excerpt, 'summary_type': '웹 검색 인용 문단 · 발행일 확인 필요',
                    'official': False, 'date_verified': False, 'research_citation': True,
                })
                if len(collected) >= maximum:
                    return collected
    return collected


def research_public_sources(articles: list, features: list, now: datetime,
                            focus_issues: list | None = None) -> tuple[list[dict], str]:
    phase = '집중 조사' if focus_issues else '광범위 조사'
    api_key = os.getenv('OPENAI_API_KEY', '').strip()
    if not api_key or os.getenv('MARKET_WEB_RESEARCH', '1').strip() == '0':
        return [], phase + ': API 연결 전 또는 웹 검색 비활성화'
    leads = choose_leads(articles)
    queries = query_plan(leads, features, focus_issues)
    context = {
        'date_kst': now.date().isoformat(), 'stage': phase,
        'independent_search_intents': queries,
        'focus_issues': (focus_issues or [])[:5],
        'candidate_events': [
            {'id': a.get('id'), 'title': a.get('title'), 'source': a.get('source'),
             'published': a.get('published'), 'url': a.get('url')}
            for a in leads[:18]
        ],
        'official_observations': [
            {'name': f.get('name'), 'period_end': f.get('period_end'), 'observed': f.get('observed')}
            for f in features[:4]
        ],
    }
    instruction = (
        '한국 금융시장 리서처다. 반드시 웹 검색으로 공개 근거를 조사한다. '
        '최근 30일의 중요한 한국·미국·글로벌 금융시장 사건부터 찾고, 원인을 확인할 과거 수치는 따로 조사한다. '
        '입력한 검색문은 각각 별개의 의도이며 하나의 복합 검색문으로 합치지 않는다. '
        '각 사건의 발표일, 시장 반응일, 지표 관측일, 비교기간을 구분한다. '
        'BOK·KRX·금융위·금감원·FRED·FRB·BLS·미 재무부 등 공식자료와 독립 취재를 우선한다. '
        '같은 보도자료의 재인용은 독립 근거로 세지 않는다. 확인한 수치의 통화·단위·기준일을 명시한다. '
        '검색 결과에 존재하지 않는 가격·발표·기사·확률을 만들지 않는다. '
        '기사 본문을 다 읽었다고 주장하지 말고, 확인한 근거 문단마다 실제 출처 URL을 인용한다. '
        '업계에서 쓰는 금융 전문용어는 정확히 사용한다. 번역투와 추상적 말, 취재 과정 설명을 피한다. '
    )
    if focus_issues:
        instruction += (
            '두 번째 조사다. 앞선 조사에서 나온 실제 시장 사건 각각의 원자료와 다른 설명을 검증한다. '
            '단순히 같은 기사를 다시 찾지 말고 통화정책·실물경제·가격·자금 수급 등 구분 가능한 추가 근거를 찾아라.'
        )
    else:
        instruction += (
            '첫 번째 조사다. 특정 지원 직무를 우대하지 말고 금리·물가·채권·주식·환율·유동성·규제를 넓게 살핀다. '
            '중요도는 실제 시장 변화의 크기·범위·기간으로 판단하며, 작은 주제의 편수를 채우지 않는다.'
        )
    request = {
        'model': os.getenv('OPENAI_RESEARCH_MODEL', os.getenv('OPENAI_MODEL', 'gpt-5-mini')),
        'tools': [{'type': 'web_search', 'search_context_size': 'high'}],
        'tool_choice': 'required', 'include': ['web_search_call.action.sources'],
        'input': [{'role': 'system', 'content': instruction},
                  {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}],
        'max_output_tokens': 8000, 'store': False,
    }
    try:
        response = requests.post(API_URL, json=request, headers={
            'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'
        }, timeout=(15, 240))
        response.raise_for_status()
        citations = cited_articles(response.json(), now)
        return citations, f'{phase}: 검색 의도 {len(queries)}개 · URL 인용 문단 {len(citations)}건'
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        return [], f'{phase}: {type(exc).__name__} · 로그에서 확인'
