"""Numbers-first market cards backed by dated FRED series observations.

A card is published only after at least two live, time-aligned observations can
be checked. Differences are arithmetic, not causal attribution. FRED's CSV
Download URL is public but not a formally documented stable web API.
"""
from __future__ import annotations

import csv
import io
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any
import requests

SERIES = {
    'DGS2': ('미국 국채 2년물 금리', '%'),
    'DGS10': ('미국 국채 10년물 금리', '%'),
    'DEXKOUS': ('달러/원 (원/달러 환산율)', '원/달러'),
    'VIXCLS': ('VIX 변동성지수', 'pt'),
    'SP500': ('S&P 500 지수', 'pt'),
    'BAMLH0A0HYM2': ('미국 하이일드 회사채 스프레드', '%p'),
}
BASE = 'https://fred.stlouisfed.org/graph/fredgraph.csv'


def fetch_one(code: str, now: datetime):
    since = (now.date() - timedelta(days=85)).isoformat()
    try:
        response = requests.get(BASE, params={'id':code,'cosd':since}, timeout=12,
                headers={'User-Agent':'MarketInsightLab/2.0 (personal educational reading)'})
        response.raise_for_status()
        content = response.content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames or code not in reader.fieldnames:
            raise ValueError('Series not found in response')
        records={}
        for row in reader:
            dt=row.get('observation_date') or row.get('DATE')
            raw=(row.get(code) or '').strip()
            if not dt or raw in ('','.','NaN'): continue
            try:
                d=date.fromisoformat(dt)
                val=float(raw)
            except (ValueError, TypeError): continue
            if not math.isfinite(val) or d > now.date(): continue
            records[d] = val
        if not records: raise ValueError('No observations')
        return code, records, None
    except Exception as exc:
        return code, {}, f'{code}: {type(exc).__name__}'


def fetch_metrics(now: datetime):
    data, errors = {}, []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures=[executor.submit(fetch_one, code, now) for code in SERIES]
        for future in as_completed(futures):
            code, records, error=future.result()
            if records: data[code]=records
            if error: errors.append(error)
    return data, sorted(errors)


def pair_changes(raw: dict, code_a: str, code_b: str, asof: date, steps: int=5, max_age: int=9):
    """Same dates for both series; do not mix latest observations from unlike days."""
    if code_a not in raw or code_b not in raw: return None
    dates=sorted(d for d in (raw[code_a].keys() & raw[code_b].keys()) if d <= asof)
    if len(dates) < steps + 1: return None
    latest, past = dates[-1], dates[-(steps+1)]
    if (asof-latest).days > max_age: return None
    a0,a1=raw[code_a][past],raw[code_a][latest]
    b0,b1=raw[code_b][past],raw[code_b][latest]
    return {'past':past,'latest':latest,'a0':a0,'a1':a1,'b0':b0,'b1':b1,'observations':steps+1}


def pct(start: float, end: float):
    return (end/start-1)*100 if start else None


def signed(n: float, decimals: int=1):
    return f'{n:+,.{decimals}f}'


def related(articles: list, terms: list, limit:int=4):
    matched=[]
    for a in articles:
        title=a.get('title','').lower()
        summ=a.get('summary','').lower()
        strength=sum(3 if k in title else 0.5 if k in summ else 0 for k in terms)
        if strength >= 3:
            matched.append((strength, a))
    matched.sort(key=lambda pair:(pair[0],pair[1].get('timestamp',0)),reverse=True)
    chosen=[]
    publishers=set()
    for _, a in matched:
        if len(chosen)>=limit: break
        if a.get('source') in publishers and len(matched)>limit:
            continue
        chosen.append(a['id'])
        publishers.add(a.get('source'))
    return chosen


def feature(fid,name,title,excerpt,obs,interpretation,alternative,verify,facts,terms,series,articles,start,end,weight):
    aids=related(articles,terms)
    return {
        'id':fid, 'name':name,'title':title,'subtitle':excerpt,
        'observed':obs,'interpretation':interpretation,'alternative':alternative,
        'verify':verify, 'facts':facts, 'article_ids':aids,'article_count':len(aids),
        'source_count':len(set(a.get('source') for a in articles if a.get('id') in aids)),
        'data_links':[{'label':SERIES[s][0], 'url':f'https://fred.stlouisfed.org/series/{s}'} for s in series],
        'period_start':start.isoformat(), 'period_end':end.isoformat(),
        'mode':'실제 수치 기반 · 인과 미검증', 'score':weight+min(len(aids),3)*2,
    }


def make_features(raw:dict, articles:list, now:datetime, limit:int=4):
    today=now.date()
    features=[]
    # Different bonds' yields as of the SAME observation date, in percentage points.
    p=pair_changes(raw,'DGS10','DGS2',today)
    if p:
        long_change=(p['a1']-p['a0'])*100
        short_change=(p['b1']-p['b0'])*100
        old_spread=(p['a0']-p['b0'])*100
        spread=(p['a1']-p['b1'])*100
        shift=spread-old_spread
        direction='확대' if shift>0.05 else '축소' if shift < -0.05 else '거의 변화 없음'
        driver=('장기금리가 더 크게 상승' if long_change>short_change and long_change>0 else
                '단기금리가 더 크게 하락' if short_change<long_change and short_change<0 else
                '장기·단기 금리의 상대 변화')
        features.append(feature('curve','금리차·경기 기대',f'미 국채 10년−2년 금리차 {signed(old_spread,0)}bp → {signed(spread,0)}bp',
           f'같은 관측일 5개 구간 동안 스프레드 {signed(shift,0)}bp · {direction}',
           f'{p["past"]} 대비 {p["latest"]}: 10년물 {p["a1"]:.2f}% ({signed(long_change,0)}bp), 2년물 {p["b1"]:.2f}% ({signed(short_change,0)}bp).',
           f'금리차 {direction}는 {driver}한 결과다. 이것만으로 경기 회복·침체나 향후 금리 결정을 단정할 수는 없다.',
           '기간프리미엄·국채 발행량 변화로 장기금리만 움직였을 수도 있다. 정책금리 기대 변화와 별도로 구분한다.',
           '동일 기간 미국 물가·고용 발표와 선물시장의 정책금리 기대, 장단기 금리의 개별 방향을 대조',
           [{'label':'10년물', 'value':f'{p["a1"]:.2f}%', 'detail':f'{signed(long_change,0)}bp / 5개 공통 관측구간'},
            {'label':'2년물','value':f'{p["b1"]:.2f}%','detail':f'{signed(short_change,0)}bp'},
            {'label':'10년−2년','value':f'{spread:.0f}bp','detail':f'{signed(shift,0)}bp'}],
           ['국채','금리','연준','금통위','인하','채권','fomc','채권시장'], ['DGS10','DGS2'], articles,p['past'],p['latest'],12+min(abs(shift)/3,8)))
    # USD/KRW and volatility on a common date.
    p=pair_changes(raw,'DEXKOUS','VIXCLS',today)
    if p:
        fxchg=pct(p['a0'],p['a1'])
        vixchg=p['b1']-p['b0']
        same=(fxchg>0 and vixchg>0) or (fxchg<0 and vixchg<0)
        relation='같은 방향' if same else '반대 방향'
        fxdir='원화 약세' if fxchg>0 else '원화 강세' if fxchg<0 else '원화 보합'
        features.append(feature('fxrisk','환율·위험선호',f'달러/원 {signed(fxchg,2)}% · VIX {signed(vixchg,1)}pt',
           f'두 지표가 {relation}으로 움직였다 — 글로벌 위험선호와 원화 고유 변수를 분리해서 볼 필요',
           f'{p["past"]}→{p["latest"]} (공통 관측일): 달러/원 {p["a0"]:,.1f}→{p["a1"]:,.1f}원, VIX {p["b0"]:.1f}→{p["b1"]:.1f}pt.',
           f'이 구간은 {fxdir}와 변동성지수의 {"상승" if vixchg>0 else "하락" if vixchg<0 else "보합"}이 관찰됐다. 같이 움직였다는 사실만으로 외국인 자금 유출이 환율 변화를 일으켰다고 볼 수는 없다.',
           '달러 자체의 강세·무역수지·한국 통화정책 등 다른 요인이 환율을 움직였을 수 있다.',
           '같은 기간 달러지수(DXY), 원화 이외 아시아 통화, 외국인 코스피 순매매, 한국은행·미국 금리차 확인',
           [{'label':'달러/원', 'value':f'{p["a1"]:,.1f}원','detail':f'{signed(fxchg,2)}% / 5개 공통 관측구간'},
            {'label':'VIX', 'value':f'{p["b1"]:.1f}pt','detail':f'{signed(vixchg,1)}pt'}],
           ['환율','원달러','원/달러','달러','외국인','원화','수급','위험회피','변동성'], ['DEXKOUS','VIXCLS'], articles,p['past'],p['latest'],10+min(abs(fxchg)*4+abs(vixchg)/2,9)))
    # Stocks down while credit risk rises? Separate price index and credit spread.
    p=pair_changes(raw,'SP500','BAMLH0A0HYM2',today)
    if p:
        stockchg=pct(p['a0'],p['a1'])
        credit=(p['b1']-p['b0'])*100
        divergence='주가 하락과 신용스프레드 확대가 동시에 관찰' if stockchg<0 and credit>0 else '주가 상승과 신용스프레드 축소가 동시에 관찰' if stockchg>0 and credit<0 else '주가와 회사채 위험프리미엄이 다른 신호를 보임'
        features.append(feature('equitycredit','주가·신용위험',f'S&P 500 {signed(stockchg,2)}% · 하이일드 스프레드 {signed(credit,0)}bp',
            divergence,
            f'{p["past"]}→{p["latest"]} (공통 관측일): S&P 500 {p["a0"]:,.1f}→{p["a1"]:,.1f}, 하이일드 스프레드 {p["b0"]:.2f}→{p["b1"]:.2f}%p.',
            f'{divergence}. 주식과 채권 모두가 위험 신호를 주는지 보면 가격 하락이 단순 조정인지 신용위험까지 번지는지 구별하는 데 도움이 된다.',
            '스프레드 변동은 발행회사 구성·유동성·국채 금리 등에도 영향을 받는다. 움직임만으로 위기 징후라고 단정하면 안 된다.',
            '투기등급 회사채 발행시장, 금융여건지수, 주가 업종별 수익률과 국채금리 비교',
            [{'label':'S&P 500','value':f'{signed(stockchg,2)}%','detail':'5개 공통 관측구간'},
             {'label':'하이일드','value':f'{p["b1"]:.2f}%p','detail':f'{signed(credit,0)}bp'}],
            ['신용','회사채','스프레드','유동성','증시','위험','채권','미국 증시'], ['SP500','BAMLH0A0HYM2'], articles,p['past'],p['latest'],9+min(abs(stockchg)+abs(credit)/4,10)))
    # Exposure of stocks to changing volatility (two independently sampled values).
    p=pair_changes(raw,'SP500','VIXCLS',today)
    if p:
        stockchg=pct(p['a0'],p['a1'])
        vixchg=p['b1']-p['b0']
        if abs(stockchg) >= 1.0 or abs(vixchg) >= 2.0:
            features.append(feature('stocksvol','증시·변동성',f'美 증시 {signed(stockchg,2)}% 움직이는 동안 VIX {signed(vixchg,1)}pt',
               '주가 등락과 옵션시장의 예상 변동성은 같은 지표가 아니다',
               f'{p["past"]}→{p["latest"]} (공통 관측일): S&P 500 {p["a0"]:,.1f}→{p["a1"]:,.1f}pt, VIX {p["b0"]:.1f}→{p["b1"]:.1f}pt.',
               f'주가지수 변화율은 {signed(stockchg,2)}%, 같은 구간 VIX 변화는 {signed(vixchg,1)}포인트였다. 변동성 상승이 동반되었는지 보면 시장의 불확실성 가격을 별도 관찰할 수 있다.',
               'VIX는 향후 변동성의 옵션 가격 기반 지표이지 확정된 실제 변동성이 아니다. 주가와 항상 반대로 움직이지 않는다.',
               '변동성 기간구조, 업종별 하락 종목 수, 국채 금리와 하이일드 신용스프레드 확인',
               [{'label':'S&P 500','value':f'{signed(stockchg,2)}%','detail':'5개 공통 관측구간'},
                {'label':'VIX','value':f'{p["b1"]:.1f}pt','detail':f'{signed(vixchg,1)}pt'}],
               ['미국 증시','나스닥','코스피','급락','급등','변동성','위험회피','반도체','증시'], ['SP500','VIXCLS'], articles,p['past'],p['latest'],7+min(abs(stockchg)+abs(vixchg)/2,9)))
    # No macro textbook-only cards: all require observed pairs.
    features.sort(key=lambda f:(f['score'],f['article_count']), reverse=True)
    return features[:limit]


def demo_feature():
    """A dated historical example, never displayed as live news or live metrics."""
    return {
      'id':'historic-2026-11-06', 'name':'시장 폭·외국인 수급',
      'title':'코스피 -6.02%: 대형주 집중 하락인가, 광범위한 위험회피인가?',
      'subtitle':'11월 6일 확인된 시장 폭과 수급으로 두 설명을 구별해 보는 실제 사례',
      'observed':'2026-11-06 코스피 5,059.69(-6.02%). 삼성전자 -6.35%, SK하이닉스 -10.44%. 코스피 하락 종목 760개, 외국인 순매도 약 2.77조 원.',
      'interpretation':'반도체 대형주 약세만으로 지수 하락 전체를 설명하는 것은 불충분하다. 하락 종목이 시장 전반에 넓게 퍼졌다는 점은 위험회피가 확산됐을 가능성을 시사한다. 다만 두 대형주의 지수 하락 기여도는 별도 산출 전까지 알 수 없다.',
      'alternative':'미국 AI 투자 관련 우려와 국내 증시의 업종 편중이 동시에 작용했을 수 있다. 당일 주가만으로 어느 요인의 인과적 영향이 큰지 확정할 수 없다.',
      'verify':'코스피 전체 상장 종목 중 등락 종목 비율, 두 대형주의 가중 지수 기여도, 업종별 하락 폭, 외국인 업종별 순매매를 같은 기준일로 대조',
      'facts':[{'label':'코스피', 'value':'-6.02%', 'detail':'2026-11-06 종가'},
               {'label':'하락 종목','value':'760개','detail':'장 마감 집계'},
               {'label':'외국인 순매도','value':'약 2.77조원','detail':'코스피 장 마감'}],
      'article_ids':[], 'article_count':0, 'source_count':3,
      'data_links':[{'label':'Aju Press · 11/6 보도','url':'https://www.ajupress.com/view/20261106164850202'},
                    {'label':'The Korea Times · 11/6 보도','url':'https://www.koreatimes.co.kr/economy/20261106/ai-investment-fears-spark-panic-selling-in-samsung-sk-hynix'},
                    {'label':'당일 등락 종목 집계','url':'https://todaystk.kr/market/2026-11-06'}],
      'period_start':'2026-11-06', 'period_end':'2026-11-06',
      'mode':'과거 사례 · 2026.11.06 (실시간 아님)','score':99,
    }
