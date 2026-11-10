import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build

class TestMarketBrief(unittest.TestCase):
    def test_macro_beats_clickbait(self):
        macro=build.classify('美 연준 금리인하 전망에 국채금리 하락','경기 전망',False)
        stock=build.classify('이 종목 주식 대박, 목표주가 상향','',False)
        self.assertTrue(macro[1]>stock[1])
        self.assertEqual(macro[0], '금리·통화정책')

    def test_no_unrelated_news(self):
        self.assertIsNone(build.classify('연예인 화보 공개','뮤직비디오 촬영',False)[0])

    def test_no_undated_news(self):
        item=build.feed_item({'title':'연준 금리인하 전망','link':'https://example.com/a','summary':'설명'},'test','news',build.NOW())
        self.assertIsNone(item)

    def test_dedup(self):
        a={'title':'연준 기준금리 인하 전망과 시장 반응','url':'https://example.com/one','score':14,'timestamp':10}
        b={'title':'연준 기준금리 인하 전망과 시장 반응!','url':'https://example.com/two','score':13,'timestamp':9}
        self.assertEqual(len(build.deduplicate([a,b])),1)

    def test_xss_safe(self):
        data=build.build_data(demo=True)
        data['articles'][0]['title']='<img src=x onerror=alert(1)>'
        build.publish(data)
        page=build.OUT.read_text(encoding='utf-8')
        self.assertNotIn('<img src=x onerror',page)
        self.assertIn('\\u003cimg',page)

    def test_rss_2_parse_and_date(self):
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
        <rss version='2.0'><channel><title>Sample</title><item>
        <title>Market update</title><link>https://example.com/123</link>
        <description><![CDATA[<p>Market detail in description</p>]]></description>
        <pubDate>Mon, 09 Nov 2026 05:00:00 +0000</pubDate>
        </item></channel></rss>"""
        items=build.parse_feed(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['link'], 'https://example.com/123')
        self.assertEqual(build.time_of(items[0]).hour, 14)

    def test_atom_feed_parse(self):
        xml=b"""<?xml version='1.0'?>
        <feed xmlns='http://www.w3.org/2005/Atom'><entry>
        <title>Test atom</title><link href='https://example.com/news' rel='alternate'/>
        <published>2026-11-09T02:30:00Z</published><summary>Detailed news</summary>
        </entry></feed>"""
        items=build.parse_feed(xml)
        self.assertEqual(items[0]['link'], 'https://example.com/news')
        self.assertEqual(build.time_of(items[0]).hour, 11)

    def test_extract_summary(self):
        text='연준은 기준금리를 동결했다. 해당 결정은 시장 예측과 일치했지만 향후 금리 경로에 관한 발언은 달라졌다. 이에 따라 채권시장에서는 향후 통화정책을 재평가하고 있다.'
        self.assertTrue(build.brief_from_text(text,'연준 기준금리 동결과 시장 반응'))

if __name__=='__main__':unittest.main()
