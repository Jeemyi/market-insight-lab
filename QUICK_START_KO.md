# MARKET INSIGHT LAB v5 — 기존 GitHub 사이트 업데이트 (윈도우)

**현재 사용 중인 사이트:** `https://jeemyi.github.io/market-insight-lab/`  
**저장소:** `https://github.com/Jeemyi/market-insight-lab`

## 무엇이 바뀌었나

v4는 스튜어드십 관련 공식자료가 화면에 고정되고, 좁은 제도·운용지원 키워드가 높은 가중치를 받았습니다. v5에서는 그런 고정 카드를 메인 화면에서 제거했습니다.

- ① **중요한 시장 변화 우선:** 거시·금리·주식시장 구조·글로벌 자금·환율·신용위험·자산배분의 중요 현상을 우선 선별합니다.
- ② **관련 기사 묶기:** 당일 기사 주제와 연결할 만한 시장 변수·숫자·다른 분야를 탐색합니다. 서로 다른 RSS 카테고리에서 나온 같은 언론사 기사는 독립 출처로 세지 않습니다.
- ③ **논리적인 구조적 분석:** AI API를 연결했다면 여러 보도·관측 시계열을 조합해 논리 사슬·대안 가설·검증 조건·2차 파급효과를 작성합니다. 기사 내용을 단순 재요약하거나 억지로 운용지원 업무에 연결하지 않도록 지침을 바꿨습니다.
- ④ **불확실한 것은 유보:** 지수 기여도나 외국인 수급 등 실제 계산하지 않은 숫자는 만들어내지 않습니다. 출처가 부족하면 리포트 0건도 정상입니다.
- ⑤ **주제 편향 제거:** 특정 ESG·의결권·제도 이야기를 매일 자동으로 띄우지 않습니다. 관련 공식문서는 그날의 뉴스가 실제로 해당 내용을 다룰 때만 참고용으로 제공합니다.

## 네 GitHub 저장소에 적용하기

1. `market-insight-lab-v5-update-only.zip` 압축을 풀어 주세요.
2. 브라우저에서 `https://github.com/Jeemyi/market-insight-lab/upload/main`을 엽니다.
3. ZIP 내부의 **아래 여덟 개 파일**을 저장소 최상위에 업로드합니다.
   - `build.py`
   - `editorial.py` (**새 파일**)
   - `deep_analysis.py`
   - `metrics.py`
   - `policy_sources.py`
   - `template.html`
   - `requirements.txt`
   - `QUICK_START_KO.md`
4. **Commit changes**를 누릅니다. 파일이 이미 있어 웹 업로드가 막히면 저장소의 기존 파일을 클릭 → 연필(Edit) → 새 파일 내용으로 교체 → Commit하면 됩니다. **ZIP 자체를 저장소에 올리는 게 아닙니다.**
5. GitHub `Actions` → `Daily MARKET INSIGHT LAB`에서 새 실행의 `build`, `deploy`가 모두 초록색인지 확인합니다.
6. 브라우저에서 `https://jeemyi.github.io/market-insight-lab/`을 새로고침합니다. 캐시 때문에 이전 화면이면 `Ctrl+F5`를 눌러 주세요.

> `.github/workflows/daily.yml` 파일은 기존에 설정했다면 기본 기사 수집·사이트 배포를 계속 담당합니다. ZIP의 웹 업로드 과정에서 숨김 폴더가 누락될 수 있으니 기존 워크플로를 삭제하지 마세요.

## AI 심층 분석에 대한 가장 중요한 구분

| 기능 | OpenAI API 없이 | 별도 API 키를 GitHub에 설정하면 |
|---|---|---|
| RSS 최신 기사 | 자동 갱신 | 자동 갱신 |
| FRED 수치 비교 | 자동 갱신 | 자동 갱신 |
| 서로 다른 기사 묶음·검증 질문 | 자동 생성 (결론 아님) | 자동 생성 |
| 실제 기사를 종합한 **새로운 구조적 결론** | **생성하지 않음** | 근거가 충분할 때만 생성 |

**ChatGPT 구독 결제와 OpenAI API 요금은 별도입니다.** AI 기능을 원하면 API 비용·한도를 먼저 확인하세요. 키를 채팅이나 코드에 붙여 넣지 마세요.

API를 연결할 경우:

1. `https://github.com/Jeemyi/market-insight-lab/settings/secrets/actions`에서 `OPENAI_API_KEY`라는 이름으로 발급받은 API 키를 **Repository secret**에 저장합니다.
2. `https://github.com/Jeemyi/market-insight-lab/edit/main/.github/workflows/daily.yml`에서 `python build.py`를 실행하는 단계를 아래와 같이 설정해야 합니다 (이미 `env`가 있다면 수정 불필요):

```yaml
      - name: Collect RSS and build connected market insights
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          OPENAI_MODEL: gpt-5-mini
        run: python build.py
```

3. 변경을 Commit하고 Actions → Run workflow로 실행합니다. API 호출 오류나 근거 부족으로 분석 카드가 비어 있을 수 있습니다. GitHub Actions 로그에 `AI 분석 실패` 또는 `0건` 등의 사유가 표시됩니다.

### 왜 기사가 나와도 분석 보고서가 0개일 수 있나요?

입수 가능한 데이터가 RSS 제목·발췌와 FRED 일부 지표에 한정되어 있습니다. 상세 기업이익 추정, 한국 상장사별 지수 기여도, 정확한 외국인 업종별 자금 흐름, 실제 제도 적용 사례는 별도 검증이 필요합니다. 자료 부족 시에는 억지로 결론을 만들지 않습니다.

### 업데이트 예약 시간

기존 워크플로 설정을 그대로 쓰면 KST 07:17 / 12:17 / 18:17에 실행을 시도합니다. 지연·실패가 있을 수 있으며 무료 공개 저장소에서 장기간 활동이 없으면 예약이 비활성화될 수 있습니다. 일반적인 정적 사이트에는 추가 서버가 필요 없습니다.

## 윈도우 컴퓨터에서 확인

`build.py`가 보이는 폴더의 주소창에 `cmd` 입력 → 아래를 순서대로 실행합니다.

```bat
python -m pip install -r requirements.txt
python build.py
```

그 뒤 `site/index.html` 더블클릭. 이 컴퓨터에서 직접 실행하는 방식은 실행 시점에만 업데이트되고, GitHub 자동 실행과는 별개입니다.
