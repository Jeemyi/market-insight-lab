"""Versioned, source-linked archive of published MARKET deep reports.

Daily Actions deployments do not commit their generated site back to GitHub.
The workflow restores/saves site/history.json via Actions cache; local runs
also reuse an existing history or the most recent site/data.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MAX_ITEMS = 240


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def _key(row):
    return hashlib.sha1((str(row.get('created_at',''))+'|'+str(row.get('report',{}).get('headline',''))).encode()).hexdigest()[:20]


def _snapshot(data: dict) -> list[dict]:
    if data.get('demo'):
        return []
    articles={a.get('id'):a for a in data.get('articles',[])}
    features={f.get('id'):f for f in data.get('features',[])}
    policies={p.get('id'):p for p in data.get('policy_sources',[])}
    rows=[]
    for report in data.get('deep_reports',[]):
        if not report.get('headline') or not report.get('facts'):
            continue
        row={
            'created_at':data.get('generated_at',''),
            'report':report,
            'articles':[articles[x] for x in report.get('article_ids',[]) if x in articles],
            'features':[features[x] for x in report.get('feature_ids',[]) if x in features],
            'policies':[policies[x] for x in report.get('policy_ids',[]) if x in policies],
        }
        row['archive_id']=_key(row)
        rows.append(row)
    return rows


def merge_archive(data: dict, folder: Path) -> list[dict]:
    if data.get('demo'):
        return []
    recent=_read(folder/'history.json')
    previous=_read(folder/'data.json')
    history = recent.get('reports',[]) if isinstance(recent,dict) else []
    if isinstance(previous,dict) and not previous.get('demo'):
        history += previous.get('archive_reports',[])
        if not previous.get('archive_reports'):
            history += _snapshot(previous)
    entries=_snapshot(data)+history
    dedup={}
    for row in entries:
        if not isinstance(row,dict) or not isinstance(row.get('report'),dict):
            continue
        if not row.get('archive_id'):
            row=dict(row,archive_id=_key(row))
        dedup.setdefault(row['archive_id'],row)
    return sorted(dedup.values(),key=lambda r:r.get('created_at',''),reverse=True)[:MAX_ITEMS]


def write_archive(entries: list[dict], folder: Path):
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'history.json').write_text(json.dumps({'reports':entries},ensure_ascii=False,indent=2),encoding='utf-8')
