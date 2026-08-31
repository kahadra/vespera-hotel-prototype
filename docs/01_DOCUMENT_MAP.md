# 제작 문서 및 설정집 지도

- 상태: ACTIVE
- 목적: 필요한 문서를 작성 시점과 책임에 따라 관리한다.

빈 문서를 미리 대량 생성하지 않는다. 해당 단계의 결정을 내려야 할 때 작성하고, 통과 조건을 만족한 뒤 다음 문서로 넘어간다.

## A. 항상 유지하는 기준 문서

| 문서 | 역할 | 현재 상태 |
|---|---|---|
| `README.md` | 프로젝트 진입점, 권위 순서, 바로 다음 작업 | 작성됨 |
| `docs/00_GAME_VISION.md` | 게임 정체성, 설계 기둥, 비목표 | 작성됨 |
| `docs/01_DOCUMENT_MAP.md` | 전체 문서 목록과 작성 순서 | 작성됨 |
| `docs/02_PRODUCTION_ROADMAP.md` | 완성까지의 단계, 산출물, 통과 조건 | 작성됨 |
| `docs/99_DECISION_LOG.md` | 확정 결정과 변경 이유 | 작성됨 |
| `PROTOTYPE_CONCEPTS.md` | 아이디어 탐색과 보류 후보 기록 | 보존 |
| `docs/10_IMPLEMENTATION_REPORT.md` | 세로 단면 구현 범위와 내부 검증 결과 | v2·캠페인·무한 영업 GREYBOX 검증됨 |
| `docs/11_ROOM_CONDITION_AND_STAYS.md` | 청결도·내구도·연박·정비의 시간축 퍼즐 | 방향 확정·다음 프로토타입 |
| `docs/12_SUBMISSION_PLAN.md` | 플레이 링크·3분 영상·썸네일·Codex 활용 설명·제출 게이트 | 제출 입력값 준비 완료 |
| `docs/13_CODEX_USAGE.md` | Codex 활용 네 문항 최종 원고·개발 이력 선택 문구·근거 | 제출 원고 완료 |
| `docs/29_DEVELOPMENT_CHRONICLE.md` | 사용자 입력부터 판단·변경·검증·커밋까지의 시간순 개발 과정 | ACTIVE · 작업/지시마다 누적 |
| `docs/30_DESKTOP_RUNTIME_SPIKE.md` | Electron 임시 셸, 세 모드 시작 허브, OS 사용자 파일 저장, 보안·패키징·출시 전 한계 | 기능 스파이크·모드 라우팅·회색 상자 파일 재개·격리 PASS · 네이티브 예외 사건 재개 · 출시 준비 전 |
| `artifacts/v2-core-playtest/REPORT.md` | v2 유효 배치 전수조사, 내부 만족도·후기·평판·평가 재검증 | 인과 모델 재감사 완료·난도 판단 대기 |

## B. 세로 단면 전에 필요한 설계 문서

| 순서 | 예정 문서 | 반드시 결정할 내용 | 생성 시점 |
|---:|---|---|---|
| 1 | `docs/03_VERTICAL_SLICE_SPEC.md` | 두 번의 영업, 시설 선택, 화면과 기능 범위 | 작성됨 |
| 2 | `docs/04_CORE_RULES_AND_SCORING.md` | 종족·등급 공통 조건, 개인 선호, 거리, 인접, 점수식, 수용·거절 | 작성·검산됨 |
| 3 | `docs/05_GUEST_DATA_SPEC.md` | 손님 데이터 필드, 종족·등급·개인 특성 합성 | 작성·검산됨 |
| 4 | `docs/06_FIRST_PUZZLES.md` | 최초 퍼즐 2개의 전체 데이터와 최고점 검산 | 작성·검산됨 |
| 5 | `docs/07_UI_FLOW_AND_WIREFRAMES.md` | 예약, 배치, 정산, 시설 선택, 결과 화면 | 작성됨 |
| 6 | `docs/08_TECHNICAL_DESIGN.md` | 엔진, 상태 모델, 규칙 평가기, 저장, RNG | 작성됨 |
| 7 | `docs/09_TEST_PLAN.md` | 핵심 가설, 플레이테스트 관찰표, 중단 조건 | 작성됨 |

## C. 코어 재미 검증 뒤 필요한 시스템 문서

| 순서 | 예정 문서 | 책임 |
|---:|---|---|
| 1 | `docs/20_PROGRESSION_AND_ECONOMY.md` | 5회 압축 쇼케이스, 등급 확률, 숨은 선호, 재방문, 시설·증축 (작성·구현됨) |
| 2 | `docs/21_HOTEL_BUILDING_SYSTEM.md` | 증축 규칙, 시설 범위, 철거·정지·매각 |
| 3 | `docs/22_HIDDEN_RULE_SYSTEM.md` | 소문, 시험 숙박, 반응, 후보 제거, 공정성 |
| 4 | `docs/23_GENERATION_AND_SOLVABILITY.md` | 예약 생성, 유효 부분집합 보장, 최고점 산출 |
| 5 | `docs/24_SAVE_AND_RUN_STRUCTURE.md` | 기능적 뼈대, 공용 프로필과 모드별 런 상태, 종료 판정·실행 기록·세이브 마이그레이션 (Electron 세 모드 허브·캠페인 재개/명시 중단·무한 영업 5-operation 파일 종단 검증) |
| 6 | `docs/25_SPECIES_AND_SYNERGY_SYSTEM.md` | 종족·계통·문화·신앙·직업 풀, 집단 인원·다종·지정 조합·시나리오 변화 시너지 (초안 작성됨) |
| 7 | `docs/26_CAMPAIGN_AND_MODE_STRUCTURE.md` | 가변 캠페인, 영업·사건 시간 단위, 관계·엔딩 분기, 무한 영업과 모드 상태 경계 (초안 · Electron 세 모드 진입과 GREYBOX 종단 검증) |
| 8 | `docs/27_OPERATIONS_HANDBOOK.md` | 공유 운영 수첩, 발견 단계, 종족·시설·아이템·시너지·손님 교차 기록 (초안 작성됨) |
| 9 | `docs/28_EXHIBITION_RELIC_SYSTEM.md` | 평판·관계별 전시품 후보군, 무작위 선택, 런 누적 패시브와 도감 (공용 3종 회색 상자 구현) |
| 10 | `docs/29_DEVELOPMENT_CHRONICLE.md` | 프로젝트 착수부터 현재까지의 요청·재설계·구현·검증 순서와 이후 상시 변경 기록 |

## D. 콘텐츠 설정집

코어가 검증되기 전에는 샘플만 만든다. 대량 설정집 작성은 시스템 변경 비용을 키우므로 보류한다.

| 예정 설정집 | 포함 내용 | 시작 조건 |
|---|---|---|
| `bibles/WORLD_BIBLE.md` | 호텔의 위치, 세계 규칙, 사회와 서비스 문화 | 핵심 루프 PASS |
| `bibles/SPECIES_BIBLE.md` | 종족·계통·문화·신앙·직업별 외형과 성향, 상극·연합 관계 | 손님 분류와 시너지 데이터 규격 고정 |
| `bibles/GUEST_RANK_BIBLE.md` | 일반·유명·귀빈·전설의 역할과 예법 | 등급 시스템 검증 |
| `bibles/FACILITY_BIBLE.md` | 시설 테마, 공개 효과, 숨은 효과, 종족 관계 | 건설 시스템 검증 |
| `bibles/CHAPTER_BIBLE.md` | 챕터별 새 사고 행동, 단체 예약, 보스 영업 | 진행 구조 검증 |
| `bibles/EVENT_BIBLE.md` | 경영 사건, 위험, 회복 선택지 | 기본 경제 안정화 |
| `bibles/TONE_AND_WRITING.md` | 명명 규칙, 유머 강도, 문장 길이, 금지 표현 | UI 문구 제작 전 |

## E. 제작 및 출시 문서

| 예정 문서 | 책임 | 시작 조건 |
|---|---|---|
| `production/CONTENT_PLAN.md` | 종족, 손님, 시설, 챕터 수량과 제작 일정 | 알파 범위 확정 |
| `production/ART_DIRECTION.md` | 색, 형태, 초상화, 객실, 아이콘 기준 | 회색 상자 PASS |
| `production/AUDIO_DIRECTION.md` | UI, 손님 반응, 영업 정산, 음악 기준 | 화면 흐름 고정 |
| `production/BALANCE_PLAN.md` | 점수, 경제, 등급 출현, 실패 회복 | 시스템 알파 |
| `production/LOCALIZATION.md` | 문자열 키, 레이아웃, 번역 범위 | 콘텐츠 구조 고정 |
| `production/ACCESSIBILITY.md` | 색약, 글자 크기, 키보드, 애니메이션 옵션 | UI 베타 전 |
| `production/QA_MATRIX.md` | 기능·데이터·시드·세이브·플랫폼 테스트 | 알파 전 |
| `production/RELEASE_CHECKLIST.md` | 빌드, 배포 페이지, 라이선스, 크레딧 | 출시 후보 전 |

## 문서 작성 원칙

- 한 결정은 하나의 권위 문서만 소유한다.
- 설정집의 수치는 시스템 문서가 아니라 데이터 표를 참조한다.
- 아이디어와 확정 규칙을 같은 문단에 섞지 않는다.
- `TBD`는 허용하지만 담당 단계와 결정 기한을 함께 적는다.
- 구현이 문서와 달라지면 구현을 정답으로 간주하지 않고 결정 로그에서 차이를 해결한다.
- 콘텐츠 개수는 코어 재미와 제작 속도가 확인된 후 확정한다.
- 사용자 설정·명령을 새로 받거나 하나의 작업을 완료하면 같은 세션에서 `docs/29_DEVELOPMENT_CHRONICLE.md`에 입력·해석·변경·검증·결과를 추가한다.
