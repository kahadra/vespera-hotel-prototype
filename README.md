# 베스페라 호텔

## 현재 상태

- 단계: 5시간 세로 단면 구현 및 자동 검증 완료, 외부 플레이테스트 대기
- 확정 장르: 숨은 규칙 학습 + 조건 최적화 배치 퍼즐 + 로그라이크 호텔 경영
- 첫 제작 목표: 두 번의 영업과 한 번의 경영 선택을 포함한 5시간 세로 단면 프로토타입
- 작업 제목 및 호텔명: 베스페라 호텔 / HOTEL VESPERA

## 문서 권위 순서

결정이 충돌할 경우 아래 순서로 따른다.

1. `docs/00_GAME_VISION.md` — 게임의 정체성과 고정된 설계 원칙
2. `docs/03_VERTICAL_SLICE_SPEC.md` — 최초 프로토타입의 정확한 범위
3. `docs/02_PRODUCTION_ROADMAP.md` — 제작 순서와 단계별 통과 조건
4. `docs/01_DOCUMENT_MAP.md` — 필요한 문서와 작성 시점
5. `docs/99_DECISION_LOG.md` — 결정의 이유와 변경 이력
6. `PROTOTYPE_CONCEPTS.md` — 아이디어 탐색 기록과 보류 후보

`PROTOTYPE_CONCEPTS.md`의 다른 후보는 폐기하지 않지만 현재 제작 범위에는 포함하지 않는다.

## 실행

별도 설치 없이 Python 정적 서버로 실행한다.

```powershell
python -m http.server 8765
```

브라우저에서 `http://127.0.0.1:8765`를 연다. `index.html`을 직접 열면 브라우저의 모듈 보안 정책 때문에 데이터 로딩이 차단될 수 있다.

## 배포본

- 파일: `build/vespera-hotel-prototype.zip`
- 형식: ZIP 루트에 `index.html`이 있는 정적 웹 빌드
- SHA-256: `CFAF6AB5B00A60099AEDD2C2EB6F8ED31E2841FAF95F970BE4E3606C03F301C3`
- 검증: ZIP을 새 임시 폴더에 풀어 Edge에서 처음부터 최종 결과까지 자동 플레이 PASS

## 검증

```powershell
python .\tools\validate_prototype_puzzles.py
python .\tools\smoke_browser.py --facility SECRET_PASSAGE
```

브라우저 자동 검증을 새 환경에서 실행할 때만 `pip install -r requirements-dev.txt`가 필요하다. 게임 실행 자체에는 외부 패키지가 필요 없다.

- Python 전수 검산: 첫 영업 35, 방음 객실 60, 라운지 63, 비밀 통로 62
- Edge 자동 플레이: 세 시설 경로 모두 최종 화면까지 통과
- 기준 화면: 1280×720

## 바로 다음 작업

1. 신규 플레이어 3명에게 설명 없이 세션을 맡긴다.
2. `docs/09_TEST_PLAN.md`의 PASS·REVISE·STOP 기준으로 코어 재미를 판정한다.
3. PASS일 때만 숨은 성향, 종족 평판, 증축 시스템을 정식 설계한다.
