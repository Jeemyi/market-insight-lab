import sys
import unittest
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metrics import pair_changes, make_features, demo_feature, pct

class TestQuantifiedStories(unittest.TestCase):
    def test_same_day_pair_not_synthetic(self):
        raw={'DGS10':{date(2026,11,i):4.0+i/100 for i in range(1,8)},
             'DGS2':{date(2026,11,i):3.0+i/100 for i in range(2,9)}}
        p=pair_changes(raw,'DGS10','DGS2',date(2026,11,9),steps=4)
        self.assertEqual(p['latest'],date(2026,11,7))
        self.assertEqual(p['past'],date(2026,11,3))
    def test_not_stale(self):
        x={date(2026,9,i):float(i) for i in range(1,10)}
        self.assertIsNone(pair_changes({'DGS10':x,'DGS2':x},'DGS10','DGS2',date(2026,11,9)))
    def test_no_fabricated_cards(self):
        self.assertEqual(make_features({}, [], datetime(2026,11,9,tzinfo=timezone.utc)),[])
    def test_spread_and_5_common_obs(self):
        ds=[date(2026,11,i) for i in range(1,8)]
        raw={'DGS10':{d:4.00+i*.02 for i,d in enumerate(ds)},
             'DGS2':{d:3.50+i*.005 for i,d in enumerate(ds)}}
        cards=make_features(raw, [],datetime(2026,11,9,tzinfo=timezone.utc))
        first=next(c for c in cards if c['id']=='curve')
        self.assertEqual(first['period_start'],'2026-11-02')
        self.assertEqual(first['period_end'],'2026-11-07')
        self.assertEqual(first['facts'][2]['value'],'59bp')
    def test_historical_is_labeled(self):
        card=demo_feature()
        self.assertIn('과거',card['mode'])
        self.assertEqual(card['period_end'],'2026-11-06')
if __name__=='__main__': unittest.main()
