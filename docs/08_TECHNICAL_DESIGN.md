# 프로토타입 기술 설계

- 상태: `v2 IMPLEMENTED · DESKTOP RELEASE DIRECTION CONFIRMED · SHELL TBD`
- 프로토타입 런타임: 의존성 없는 정적 HTML/CSS/JavaScript 앱
- 정식 배포 방향: 로컬 실행파일과 파일 저장을 사용하는 Windows 우선 데스크톱 게임, 이후 Steam 배포
- 현재 환경 확인: Python·.NET 사용 가능, Node.js/npm·Rust/Cargo·Godot 없음

## 2026-08-30 정식판 플랫폼 방향

심사용 웹 빌드의 동결 사유는 심사 종료와 함께 사라졌다. 정식 제품은 호스팅 주소를 주 실행 경로로 삼지 않고, 네트워크 연결 없이 로컬 자산을 읽는 데스크톱 실행파일을 기본 산출물로 삼는다. 저장도 브라우저 내부 `localStorage`가 아니라 운영체제의 앱 전용 폴더에 버전이 있는 파일로 보존하고, Steam 단계에서는 이 파일을 계정별 경로와 Steam Cloud에 연결한다. 별도의 자체 계정 서버는 기본 요구사항으로 두지 않는다.

이는 검증된 웹 코어를 폐기한다는 뜻이 아니다. 현재 `src`의 약 9천 줄 JavaScript, DOM/CSS UI와 Edge 회귀는 서버 계산에 의존하지 않으므로 데스크톱 셸에서도 대부분 재사용할 수 있다. 호스팅 웹은 빠른 내부 검증과 과거 쇼케이스 보존 역할로 낮추고, 정식 실행파일이 배포 권위가 된다.

### 구현 후보 — RECOMMENDED · NOT IMPLEMENTED

| 후보 | 현재 코드 재사용 | 저장·Steam 경계 | 비용과 판단 |
| --- | --- | --- | --- |
| Electron | HTML/CSS/ES Modules와 Chromium 회귀를 거의 그대로 사용 | preload에서 앱 데이터 파일과 네이티브 연동을 얇게 노출 가능 | 설치 용량·메모리는 크지만 현재 동기식 `Storage` 주입 계약과 가장 가까워 1차 스파이크 권장 |
| Tauri 2 | 프런트엔드 재사용 가능 | 앱 데이터 파일 API와 작은 설치본 제공 | Rust·MSVC와 비동기 브리지 도입이 필요하므로 크기 이점이 구현 복잡도보다 중요한지 스파이크에서 비교 |
| Godot/Unity 이식 | JSON 개념과 일부 순수 규칙만 직접 재사용 | 엔진별 저장·Steam 플러그인 사용 | DOM 렌더러·상태 연결·자동 회귀를 대폭 재작성하므로 실시간 공간 연출·대규모 애니메이션·콘솔 대응이 핵심 요구가 되기 전에는 보류 |

Electron/Tauri 중 어느 쪽이든 최종 게임은 로컬 실행파일이며, 인터넷 속도는 영업 처리 속도에 관여하지 않는다. 셸 선택은 엔진 이식 결정이 아니라 기존 웹 코어에 파일·창·Steam 기능을 제공하는 플랫폼 어댑터 결정이다.

### 데스크톱 저장 최소 계약

- 활성 런, 프로필 수첩, 실행 기록을 브라우저 캐시가 아닌 명시적 버전 파일로 분리한다.
- 저장은 임시 파일 기록과 원자적 교체, 직전 정상 백업을 사용해 중간 종료로 원본이 깨지지 않게 한다.
- Steam 미실행 또는 개발 실행은 로컬 기본 프로필을 사용한다. Steam 연동 뒤에는 Steam ID를 계정 경계로 사용하고 같은 PC의 다른 Steam 계정이 저장을 공유하지 않게 한다.
- Steam Cloud 1차 연결은 파일 경로만 동기화하는 Auto-Cloud를 우선 검토하고, 업적·오버레이·명시적 계정 정보가 필요할 때 Steamworks API 브리지를 추가한다.
- 기존 `localStorage` 데이터는 한 번만 파일 저장으로 가져오는 마이그레이션 대상으로 두며, 두 저장소를 동시에 권위로 사용하지 않는다.
- 출하 게이트는 완전 오프라인 기동, 종료 후 재실행 복구, 손상 파일 백업 복구, 계정 분리, Steam Cloud 충돌 처리와 기존 캠페인·무한 영업 회귀다.

데스크톱 셸을 붙이기 전에도 규칙·캠페인 뼈대는 현재 브라우저 회귀로 계속 완성한다. 셸 스파이크는 게임 코어를 재작성하지 않고 동일 데이터·동일 시드·동일 저장 의미를 보존해야 한다.

## v2 현재 구조

### v2 프로토타입 런타임과 배포

- HTML5, CSS, 브라우저 표준 JavaScript ES Modules, JSON만으로 실행한다.
- 보존 중인 v2 공개 쇼케이스는 GitHub Pages 같은 정적 호스팅에서 실행하며 플레이어에게 Python이나 빌드 도구를 요구하지 않는다. 이는 정식 제품의 배포 권위가 아니다.
- 로컬 정적 서버와 Python 도구는 개발 검증 전용이다.
- `data/prototype_v1.json` 파일명은 배포 경로 호환성을 위해 유지하지만 현재 내용은 v2 5영업 스키마다.

### v2 모듈 책임

| 모듈 | 책임 |
|---|---|
| `data.js` | JSON 로딩, 인덱스, 시설이 병합된 개선 객체, 교차참조·확률·단계·숨은 선호 검증 |
| `random.js` | JSON으로 직렬화 가능한 순수 시드 난수 상태와 가중 선택 |
| `progression.js` | 단계·평판 잠금을 적용한 등급 확률, 손님 신청 생성, 보장·특별 초대 |
| `upgrades.js` | 공사 제안 생성, 선행조건·비용 검사, 구매 결과 |
| `rules.js` | 객실·관계·필수 조건·공개/숨은 선호·재방문·시너지·상극 평가 |
| `scoring.js` | 수입, 평판, 현재 만족도와 결과 설명 |
| `emergency.js` | 시간 만료 시 연박 고정을 지키는 비최적 긴급 배정·강제 취소 |
| `run.js` | 공통 런 지표 요약, 데이터 기반 종료 판정, 버전이 있는 로컬 실행 기록 |
| `save.js` | 데이터·모드 버전을 검증하는 활성 런과 직전 영업 시작 체크포인트 생성·복구·삭제 |
| `state.js` | 5영업 상태, 시드, 수용, 동적 응대·물리 객실 한도, 연박, 객실 상태, 발견, 예지 재시도, 누적 개선, 계약 한도 |
| `render.js` | 초대장, 수첩, 예약 한도·기존 객실도, 객실 배정, 결산, 영업 준비·공사 계약, 종합 결과 |
| `input.js` | 손님 클릭 정보 열람, 드래그 전용 배정·교환·해제, 수용·거절, 정비·계약, 수첩과 주요 전환 |

### v2 상태 전환

```text
TITLE → TUTORIAL ─┐
  └─ saved run → RESUME ─┤
  └──── skip ─────┴→ NIGHT_1_PLACEMENT → RESULT
SHOWCASE: RESULT → PREPARATION_CONTRACT → RESERVATION → PLACEMENT → RESULT
                                      ↑ 2~5회차 반복 ↓
RESULT(5회차) → RUN_COMPLETION → FINAL → RUN_RECORD

CAMPAIGN: DAY_OPENING → RESERVATION / PLACEMENT → RESULT → RESULT_REVIEW
              ↑                                      ├─ 마감 서명 → 다음 진행
              └────── 아침 장부 재열람 ─────────────┘
```

`PREPARATION_CONTRACT`는 플레이어에게 `영업 준비 / 공사 계약`으로 표시한다. 같은 화면에서 빈 객실을 정비하고 `동관 증축`과 `시설·인테리어`를 분리해 제안한다. 각 분류는 영업 사이 최대 1건 계약하며, 계약 여부와 관계없이 명시적인 `다음 영업` 행동으로 진행한다.

### v2 핵심 상태

```js
{
  phase,
  currentNightIndex,
  gold,
  hotelReputation,
  runSeed,
  rngState,
  currentRankOdds,
  currentGuestOfferIds,
  specialInviteGuestIds,
  reservationBoardOpen,
  applicantDecisions,
  acceptedGuestIds,
  rejectedGuestIds,
  placements,
  stayovers,
  lockedGuestIds,
  roomConditions,
  ownedUpgradeIds,
  currentUpgradeOfferIds,
  preparationContracts,
  guestHistory,
  seenSpeciesIds,
  seenRankIds,
  discoveredHiddenPreferenceIds,
  secretaryPresentationId,
  foresightRetryCount,
  foresightDiscoveryIds,
  nightResults,
  runRecord,
  recordArchiveCount
}
```

- `rngState`는 매 선택 뒤 새 값으로 교체하므로 저장·재현 가능하다.
- 연박은 `{ guestId: { roomId, remainingNights } }`로 첫 객실을 고정한다.
- 객실 상태는 `{ roomId: { cleanliness, durability } }`로 영업 사이 유지한다.
- 공개 종족·등급은 첫 신청에서 `seen*Ids`에 기록하고, 종족×등급 숨은 선호는 결산에서만 `discoveredHiddenPreferenceIds`에 기록한다.
- 숨은 선호는 별도 배열로 평가해 공개 `soft` 목록에 중복 합산하지 않는다.
- 마지막 결산은 `completeRun()`을 통해서만 종료하며, 종료 조건·표시 문구는 `run_completion` 데이터에서 판정한다.
- 실행 기록 스키마 6은 전체 상태를 복제하지 않고 모드·시드·엔딩 ID·계층, 종족·관계 인물 선택, 종족 엔딩에서 열린 지배인의 이후 선택지, 인과적으로 연결된 후일담과 핵심 지표만 최근 20개 보존한다. 형식 캠페인은 실제 완료 스테이지·진행 권위·활성 상한·트루 확장 여부·마지막 영업 ID와 수입·유지비·재가동·정비·상환·잔여 부채, day 56 부채 해결 및 운영자금 부족 증거도 기록한다. 같은 기록 ID의 중복 저장은 기존 항목을 대체한다.
- 캠페인의 세이브·체크포인트·프로필 분리는 `24_SAVE_AND_RUN_STRUCTURE.md`의 계약을 따른다.
- 현재 v2는 조작 뒤와 페이지 이탈 시 활성 런을 저장한다. 다시 열면 타이틀의 `지난 영업 이어하기`로 복구하며, 새 런 시작·엔딩·재시작은 활성 세이브를 제거한다.
- 활성 런 세이브 스키마 6은 모드별 키로 현재 상태와 `stage_checkpoint`를 보존한다. `SHOWCASE`는 예약·배치 시작 상태를, 시나리오 캠페인은 신청 생성 전 `DAY_OPENING` 상태를 캡처한다. 형식 캠페인은 결과 배열·실제 진행 기록·재정 원장·선택 상환을 일대일 교차검증하고, 현재·체크포인트의 접두부와 영업 ID 또는 현금·지출·부채 권위가 어긋난 저장을 거부한다. 별도 프로필 스키마 1은 모드가 공유하는 수첩 지식과 전시품 도감용 ID 집합만 저장한다.
- `DAY_OPENING`과 `RESULT_REVIEW`는 시나리오 모드에서만 진입한다. `ENDLESS`는 결과 화면의 `이번 영업 다시`가 `retryCurrentStage()`를 직접 호출하고, `SHOWCASE`는 재검토 행동을 만들지 않는다.
- `restartDayThroughSecretary()`는 마감 대화에서만 동작하며 골드·평판·난수·객실·연박·사건 상태를 아침 체크포인트로 되돌린다. 해당 경로에서 새로 확인한 숨은 선호 ID와 내부 재검토 횟수만 합쳐서 유지한다.
- `secretaryPresentationId`는 `MALE` 또는 `FEMALE`만 허용하며 캠페인 상태 전환과 규칙 계산에는 사용하지 않는다.
- 캠페인은 `NEW_GAME`과 `STORY` 상태를 추가한다. 플레이어·비서·관계 인물 표현 설정은 런에 고정하고, 마녀 관계 역할은 항상 `FEMALE`로 정규화한다.
- 기존 비형식 스키마 3·4·5 및 과거 단일 키 `SHOWCASE` 저장은 읽을 때 스키마 6의 모드별 저장으로 정규화한다. 형식 캠페인은 스키마 6만 허용하고 이전 저장에서 진행·재정 권위를 추론하지 않는다. 손상 데이터나 프로필 ID가 다른 런은 재개하지 않는다.

### 시드 제안과 공정성

- `rankOddsFor(data, stage, reputation)`는 평판 구간을 고른 뒤 아직 열리지 않은 등급 확률을 하위 등급으로 이동한다.
- 각 확률 행은 N/R/SR/SSR 합계 100을 유지한다.
- 2회차 R, 3회차 SR 보장은 쇼케이스 진행을 위한 명시적 예외다.
- 5회차 SSR 특별 초대는 일반 확률이나 영구 해금 상태를 변경하지 않는다.
- `generateGuestOffer`와 공사 제안 생성은 동일 입력·동일 시드에서 동일 결과를 반환한다.
- 동관 증축은 `F1-D → F2-D → F3-D` 선행조건을 검증한다. 시설·인테리어는 함께 보유할 수 있다.
- 공사가 직접 건드리는 객실 집합과 현재 연박 객실이 겹치면 해당 시설·인테리어 계약을 거부한다.
- `roomCapacitySummary()`는 완공 객실 수, 기본 5명+증축 객실 수의 `serviceLimit`, 구조·상태 차단을 제외한 `physicalPlacementLimit`, 연박 점유와 남은 빈 객실을 한 번에 계산한다.
- `reservationSummary()`는 연박·사전 확정·신청 수용 명단을 중복 없이 합치고 응대 한도와 물리 객실 한도를 각각 검사한다. 필수 숙박 조건의 조합 가능성은 예약 단계에서 선판정하지 않는다.
- 예약 객실도는 배치 화면을 재사용하지 않고 board state와 `stayovers`만 읽는 전용 읽기 뷰다. 미증축·사용 불가·연박 고정·빈 객실 상태를 객실당 하나만 표시한다.

### 데이터 불변 조건

- 등급은 정확히 N/R/SR/SSR, 시나리오는 정확히 5개다.
- 종족은 4개, 손님은 12명 이상, 공사 항목은 8개 이상이다.
- 종족×등급 숨은 선호는 지원되는 soft 규칙, 고유 ID, 양수 점수만 허용한다.
- 손님 객체의 개인 `hidden_*` 필드와 모든 숨은 hard/감점 형식을 거부한다.
- 연박 객실 고정, 마모 기준, 공사 교차참조와 순환 선행조건을 검증한다.
- 완공된 증축 객실 한 실이 예약 응대 한도를 정확히 1명 높이고, 연박 손님이 응대 인원과 물리 점유에 각각 한 번만 포함되는지 검증한다.

## v1 보존 기록 — 2영업 기술 설계

아래 구조와 고정 최고점은 최초 2영업 빌드의 구현 계획·검증 기록이다. 현재 상태 머신, 무작위성, 콘텐츠 상한으로 사용하지 않는다.

## 1. 기술 선택

### 프로토타입

- HTML5
- CSS Grid/Flexbox
- 브라우저 표준 JavaScript ES Modules
- JSON 데이터
- Python 정적 서버와 검산기

### 선택 이유

- 설치와 빌드 단계 없이 즉시 구현 가능
- UI와 데이터 중심 게임에 충분함
- 정적 파일만으로 웹 배포 가능
- `prototype_v1.json`을 검산기와 게임이 함께 사용 가능
- 현재 로컬 환경에 추가 도구 설치가 필요 없음

### 정식 버전 플랫폼 게이트

- 게임 코어는 현재 HTML/CSS/JavaScript 구조와 회귀를 유지하고, Windows 실행파일을 만드는 데스크톱 셸을 부착한다.
- 첫 구현 직전 Electron과 Tauri 2 중 셸을 확정한다. 현재 권장안은 동기식 저장 주입과 Chromium 회귀를 가장 적게 바꾸는 Electron이다.
- Godot 등으로의 전면 이식은 실시간 공간 연출·대규모 애니메이션·콘솔 대응이 실제 필수 요구가 될 때 별도 재검토한다.
- 셸 선택 뒤에는 파일 저장 어댑터, 오프라인 기동, 빌드 재실행 복구를 먼저 증명하고 Steam 계정·Cloud 연동을 붙인다.

## 2. 예정 파일 구조

```text
vespera-hotel-prototype/
├─ index.html
├─ styles.css
├─ data/
│  └─ prototype_v1.json
├─ src/
│  ├─ main.js
│  ├─ state.js
│  ├─ data.js
│  ├─ rules.js
│  ├─ scoring.js
│  ├─ render.js
│  └─ input.js
└─ tools/
   └─ validate_prototype_puzzles.py
```

## 3. 모듈 책임

### `main.js`

- 초기 데이터 로딩
- 게임 상태 생성
- 화면 전환 연결
- 렌더와 입력 초기화

### `state.js`

- 현재 단계
- 골드와 평판
- 시설
- 수용·거절 목록
- 손님 배치
- 영업 결과
- 재시작과 두 번째 영업 재도전

### `data.js`

- JSON 로딩
- ID 인덱스 생성
- 데이터 누락 검사
- 종족과 개인 조건 합성

### `rules.js`

- 객실 속성
- 기본 및 시설 이웃 관계
- 필수 조건 평가
- 위반 원인 구조 생성

### `scoring.js`

- 손님별 선호 사항 점수
- 시설 객실 보너스
- 수입
- 평판
- 영업 평가

### `render.js`

- 현재 상태를 DOM으로 표현
- 화면별 템플릿
- 점수와 충돌 원인 표시
- 시설 미리보기

### `input.js`

- v1 당시 클릭 배치
- 드래그 앤 드롭
- 수용·거절 전환
- 주요 버튼 이벤트

## 4. 게임 단계 상태 머신

```text
TITLE
→ NIGHT1_INTRO
→ NIGHT1_PLACEMENT
→ NIGHT1_RESULT
→ FACILITY_SHOP
→ NIGHT2_RESERVATION
→ NIGHT2_PLACEMENT
→ FINAL_RESULT
```

허용된 전환만 함수로 제공한다. 화면 코드가 단계 값을 임의로 변경하지 않는다.

## 5. 게임 상태

```js
{
  phase,
  gold,
  hotelReputation,
  selectedFacilityId,
  acceptedGuestIds,
  rejectedGuestIds,
  placements,
  night1Result,
  night2Result,
  runSeed
}
```

- `placements`: `{ guestId: roomId }`
- 화면 전환 시 필요한 값만 유지
- 재시작은 초기 상태 객체를 새로 생성
- 두 번째 영업 재도전은 첫 결과와 시설을 유지하고 두 번째 예약 이후 상태만 초기화

## 6. 평가 결과 구조

```js
{
  valid,
  violations: [
    { guestId, ruleType, relatedIds, message }
  ],
  guestScores: {
    guestId: {
      total,
      items: [{ label, points, source }]
    }
  },
  placementScore,
  income,
  reputationDelta,
  evaluationScore
}
```

렌더링 코드가 규칙을 다시 계산하지 않는다. 모든 숫자와 메시지는 평가 결과를 사용한다.

## 7. Python 검산기와 브라우저 평가기의 관계

- JSON 데이터는 동일 파일을 사용한다.
- JavaScript 규칙 결과는 Python 검산기의 최고점과 일치해야 한다.
- 첫 영업 최고 평가: 35
- 방음 객실 두 번째 영업 최고 평가: 60
- 라운지 두 번째 영업 최고 평가: 63
- 비밀 통로 두 번째 영업 최고 평가: 62

구현 완료 전 대표 최고점 배치를 브라우저에 입력해 네 값을 모두 비교한다.

## 8. 데이터 로딩

브라우저 보안 정책을 피하기 위해 `file://`로 직접 열지 않고 정적 서버를 사용한다.

```powershell
python -m http.server 8000
```

브라우저에서 `http://localhost:8000`을 연다.

모든 파일 경로는 상대 경로를 사용한다.

## 9. 무작위성

세로 단면의 퍼즐, 손님, 시설 제안은 고정한다.

- 팁은 만족 점수와 동일한 고정값
- 시설 순서 고정 가능
- `runSeed`는 이후 무작위성 추가를 위한 자리만 유지
- 같은 선택과 배치는 항상 같은 결과

## 10. 오류 처리

- JSON 로딩 실패: 시작 화면 대신 오류와 파일명 표시
- 알 수 없는 규칙 ID: 해당 영업 진행 차단, 개발 오류 표시
- 존재하지 않는 손님/객실 참조: 데이터 검증 실패
- 수용 한도 초과: 명단 확정 비활성화
- 유효 배치가 없는 고정 데이터: Python 검산 단계에서 빌드 전 차단

## 11. 성능 상한

- 런타임에서 전수 열거하지 않는다.
- 현재 배치 한 번만 평가한다.
- 한 번의 배치 변경에서 손님 6명 이하 전체 재평가 허용
- DOM 요소를 무제한 누적하지 않음
- 애니메이션은 CSS transition 수준으로 제한

## 12. 검증과 배포

### 보존 프로토타입

1. Python 서버에서 전체 흐름 테스트
2. 상대 경로와 브라우저 회귀 확인
3. 기존 정적 ZIP과 공개 URL은 과거 쇼케이스 증빙으로 보존

### 정식 제품

1. 선택한 데스크톱 셸에서 동일 시드·동일 규칙 결과 회귀
2. 앱 전용 폴더의 원자적 파일 저장·백업·마이그레이션 검증
3. 네트워크를 끊은 클린 Windows 환경에서 설치·기동·한 런 완료
4. 재실행 복구, 손상 파일 복구와 같은 PC의 계정별 저장 분리 검증
5. Steam Auto-Cloud와 충돌 처리 검증 뒤 Windows 실행파일을 배포 권위로 지정

## 13. 구현 금지

- 규칙을 UI 이벤트 안에 직접 작성
- 손님별 조건을 JavaScript에 하드코딩
- Python과 JavaScript가 다른 점수 공식을 사용
- 검산되지 않은 새 손님이나 시설 추가
- 숨은 선호 시스템 선행 구현
- 외부 UI 프레임워크 설치
