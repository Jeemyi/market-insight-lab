"""Broad-market issue discovery: score cross-source, cross-variable *questions*, not textbook conclusions.

Every surfaced question is marked as unverified until a sourced research report is produced.
The rules are intentionally broad: no topic earns extra points merely for ESG/regulation.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

# Groups describe market mechanisms; they are not recurring editorial quotas.
THEMES = (
    {
        "id": "markets", "name": "주식시장·수급", "weight": 2,
        "terms": ("코스피", "코스닥", "증시", "반도체", "S&P", "나스닥", "주가지수", "지수", "외국인", "기관", "시가총액", "쏠림", "순매도", "순매수", "주도주"),
        "bridges": ("금리", "환율", "실적", "수출", "외국인", "유동성", "ETF", "경기", "정책"),
        "question": "지수 변화를 기업이익·할인율·수급 중 무엇이 설명하는가? 상승·하락 종목의 폭도 같은 방향인가?",
        "check": "등락 종목 비율, 업종·상위종목의 지수 기여도, 외국인 업종별 순매매(같은 날짜)",
        "features": ("stocksvol", "equitycredit", "fxrisk"),
    },
    {
        "id": "rates", "name": "금리·채권·정책기대", "weight": 2,
        "terms": ("금리", "국채", "국고채", "채권", "연준", "FOMC", "한국은행", "금통위", "기준금리", "장기금리", "단기금리", "기간프리미엄", "재정적자", "발행물량"),
        "bridges": ("물가", "고용", "성장", "국채발행", "환율", "주식", "회사채", "경기", "재정"),
        "question": "단기 정책기대가 바뀐 것인가, 장기 성장·물가·국채수급의 재평가인가?",
        "check": "2년·10년 금리와 장단기 금리차, 물가·고용 발표, 국채 발행 및 기대금리",
        "features": ("curve", "equitycredit"),
    },
    {
        "id": "macro", "name": "실물경기·물가·기업이익", "weight": 2,
        "terms": ("물가", "인플레", "CPI", "PCE", "고용", "실업률", "GDP", "성장률", "PMI", "수출", "소비", "경기", "생산", "관세", "무역", "실적전망", "기업이익"),
        "bridges": ("금리", "증시", "환율", "채권", "투자", "기업", "외국인", "수급"),
        "question": "발표된 수치보다 시장의 예상이 얼마나 달랐으며, 성장 전망과 물가 전망 중 무엇을 더 바꿨는가?",
        "check": "실제치·시장 예상치·전월 수정치, 주식·채권·환율의 발표 전후 반응",
        "features": ("curve", "fxrisk", "equitycredit"),
    },
    {
        "id": "fx", "name": "환율·글로벌 자금 이동", "weight": 2,
        "terms": ("환율", "달러", "원화", "엔화", "외환", "DXY", "외국인", "자금유입", "자금유출", "외환보유", "환헤지", "경상수지", "환차"),
        "bridges": ("금리", "수출", "증시", "채권", "위험", "경기", "투자", "관세"),
        "question": "달러 전체의 움직임인가, 원화 고유의 위험인가? 주식·채권 수급과 같은 기간에 비교하면 무엇이 다른가?",
        "check": "달러지수와 아시아 통화, 외국인 주식·채권 순매매, 미·한 금리차",
        "features": ("fxrisk", "curve", "stocksvol"),
    },
    {
        "id": "credit", "name": "유동성·신용·금융안정", "weight": 2,
        "terms": ("신용", "회사채", "스프레드", "유동성", "PF", "부동산PF", "연체", "은행", "금융안정", "위험회피", "자금시장", "MMF", "RP", "CP", "부실", "차환"),
        "bridges": ("국채", "금리", "증시", "부동산", "규제", "담보", "자금", "은행"),
        "question": "위험이 특정 자산의 가격 조정에 머무는가, 신용과 자금조달 비용으로 전이되는가?",
        "check": "우량·비우량 회사채 스프레드, 단기자금 조달금리, 신규 발행·차환 여건",
        "features": ("equitycredit", "curve"),
    },
    {
        "id": "allocation", "name": "ETF·연금·자산배분 구조", "weight": 1,
        "terms": ("ETF", "퇴직연금", "국민연금", "패시브", "액티브", "자산배분", "펀드", "운용사", "수탁고", "리밸런싱", "자금유입", "자금유출", "연금개혁", "지수편입"),
        "bridges": ("주식", "채권", "유동성", "수급", "금리", "제도", "세제", "외국인", "환율"),
        "question": "투자자 자금이 어디로 이동했으며, 상품·지수·제도의 구조가 그 이동을 증폭하는가?",
        "check": "ETF 순유입·설정액과 실제 수익률, 기초지수 편입비중, 연금 자산배분·제도 변화",
        "features": ("stocksvol", "curve", "fxrisk"),
    },
    {
        "id": "policy", "name": "금융제도·시장구조 변화", "weight": 0,
        "terms": ("금융위", "금감원", "금융규제", "제도개편", "세제", "정책", "연금", "시장조성", "공매도", "자본시장법", "주주", "스튜어드십", "의결권", "상장제도", "밸류업"),
        "bridges": ("증시", "수급", "자금", "연금", "투자", "채권", "시장", "기업", "수익률", "비용"),
        "question": "제도 변화가 누구의 유인을 바꾸며, 그 결과 자금 흐름·상품·기업행동은 달라질 수 있는가?",
        "check": "원문 시행일·적용 대상, 실제 자금·거래·조직 변화, 제도 전후의 비교집단",
        "features": (),
    },
)


def publisher_of(source: str) -> str:
    """Treat different RSS channels from one company as one publisher."""
    return (source or '').split('·')[0].strip()


def hits(text: str, terms: tuple[str, ...]) -> set[str]:
    content = text.casefold()
    return {t for t in terms if t.casefold() in content}


def discover_issues(articles: list[dict], features: list[dict], now: datetime, limit: int = 5) -> list[dict]:
    """Select supported questions. Never say that correlated variables caused each other."""
    chosen = []
    for theme in THEMES:
        matched = []
        for article in articles:
            title = article.get('title', '')
            summary = article.get('summary', '')
            ht = hits(title, theme['terms'])
            hs = hits(summary, theme['terms'])
            strength = len(ht) * 3 + min(len(hs), 3) * .7
            if not ht or strength < 3:
                continue
            cross = hits(title + ' ' + summary, theme['bridges'])
            matched.append((strength + min(3, len(cross)) + min(1, article.get('score', 0)/20), article, cross))
        if len(matched) < 2:
            continue
        matched.sort(key=lambda pair: (pair[0], pair[1].get('timestamp', 0)), reverse=True)
        diversified = []
        for item in matched:
            if len(diversified) >= 7: break
            if sum(publisher_of(row[1].get('source')) == publisher_of(item[1].get('source')) for row in diversified) >= 2: continue
            diversified.append(item)
        publishers = {publisher_of(row[1].get('source')) for row in diversified}
        if len(publishers) < 2: continue
        selected_features = [f for f in features if f.get('id') in theme['features']]
        unique_links = sorted({x for row in diversified for x in row[2]})
        title_focus = sum(len(hits(row[1].get('title',''), theme['terms'])) for row in diversified)
        # Real-world salience: recency, independent coverage, breadth, and matching data.
        recent = sum(1 for _, a, _ in diversified if a.get('timestamp') and now.timestamp()-a['timestamp'] < 48*3600)
        score = (len(publishers) * 4.2 + min(len(diversified), 6) * 1.1
                 + min(len(unique_links), 5) * 1.7 + min(len(selected_features), 2) * 4
                 + min(recent, 4) * 1.8 + min(title_focus, 8) * .3 + theme['weight'])
        # A niche policy story without market/investor spillover should not dominate.
        if theme['id'] == 'policy' and not unique_links:
            score -= 7
        linked = [row[1] for row in diversified[:5]]
        chosen.append({
            'id': 'issue-' + theme['id'], 'theme': theme['name'], 'priority': round(score,1),
            'headline': theme['name'] + ': 서로 다른 뉴스의 설명은 어디에서 만나는가?',
            'question': theme['question'], 'check': theme['check'],
            'bridge_terms': unique_links[:6], 'article_ids': [a['id'] for a in linked],
            'feature_ids': [f['id'] for f in selected_features[:2]],
            'publisher_count': len({publisher_of(a['source']) for a in linked}),
            'article_count': len(linked), 'evidence_level': '연결 질문 · 원인 미확정',
        })
    chosen.sort(key=lambda c:(c['priority'],c['publisher_count'],c['article_count']), reverse=True)
    # Cap niche institutional themes; none gets a guaranteed slot.
    final=[]
    institutional=0
    for issue in chosen:
        if issue['id'] in ('issue-policy','issue-allocation'):
            if institutional >= 1: continue
            institutional += 1
        final.append(issue)
        if len(final) >= limit: break
    return final
