# MARKET INSIGHT LAB v6.9

매일 금융시장 주요 이슈를 찾아 공개 뉴스와 공식 지표를 바탕으로 분석하는 개인용 정적 사이트입니다.

- **01 주요 시장 심층 분석:** 중요한 사건을 폭넓게 탐색한 뒤 원자료를 추가 조사해 최대 3편의 독립된 완성형 기사를 작성합니다. 충분한 근거가 없으면 발행하지 않습니다.
- **02 공식 데이터 리서치:** FRED 관측일을 맞춰 수치 비교, AI 분석 또는 명확히 구분한 자동 해설을 제공합니다.
- **03 참고 기사:** 기사 목록·원문 링크·읽음/저장을 제공합니다. 기사 요약과 검증 전 쟁점은 완성된 분석으로 세지 않습니다.
- **04 지난 심층 분석:** 이전에 발행한 글을 보고서 날짜와 함께 보관합니다. 별도 `site/history.json`을 생성하며 Actions 캐시로 다음 실행에 복원합니다.
- **문체:** 전문용어는 유지하면서 자연스럽고 구체적인 금융 기사 문체를 사용합니다.
- **읽기 화면:** 본문 폭·크기와 제목 간격을 다듬었으며, 모바일에서는 추가 관점 필터를 접어서 본문을 앞에 배치합니다.

## 설치와 실행

[QUICK_START_KO.md](QUICK_START_KO.md)를 따르세요. 기존 저장소의 `site/data.json`과 `site/index.html`을 보존하도록 **배포 ZIP에는 site 폴더를 넣지 않습니다.**

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python build.py
```

`python build.py --demo`는 화면과 데이터 구조 확인용 **시연 데이터**를 만들며 실시간 AI 분석이 아닙니다. GitHub Actions는 한국시간 07:17 하루 한 번 예약되어 있습니다.

필요한 GitHub Secrets: `OPENAI_API_KEY`, `FRED_API_KEY`. ChatGPT 구독과 OpenAI API 사용료는 별개입니다.

선택 환경변수: `MARKET_WEB_RESEARCH`(`1` 기본, `0` 비활성화), `MARKET_RESEARCH_ROUNDS`(`2` 기본, `1` 절약), `OPENAI_RESEARCH_MODEL`(선택). 검색·기사·데이터 원고에 각각 API 호출이 발생할 수 있습니다.

이 사이트는 공개자료를 근거로 작성한 AI 분석으로, 실제 투자 권유 또는 모든 출처의 완전 자동 사실확인 서비스가 아닙니다.
