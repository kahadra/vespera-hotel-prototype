# 세로 단면 기술 설계

- 상태: READY FOR IMPLEMENTATION
- 대상: 의존성 없는 정적 웹 앱
- 현재 환경 확인: Python 사용 가능, Node.js/npm 없음

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

### 정식 버전 기술 게이트

코어 플레이테스트 PASS 뒤 다음 중 하나를 다시 결정한다.

- 현재 웹 구조를 TypeScript 기반으로 정식화
- Godot 등 게임 엔진으로 이식
- 정적 웹 구조를 유지하며 모듈과 테스트만 강화

세로 단면 전에 정식 버전 엔진을 확정하지 않는다.

## 2. 예정 파일 구조

```text
F:\Game\
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

- 클릭 배치
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

## 12. 배포

1. Python 서버에서 전체 흐름 테스트
2. 상대 경로 확인
3. `index.html`, `styles.css`, `src`, `data`를 ZIP 루트에 포함
4. ZIP 루트에 `index.html`이 있는지 확인
5. 웹 호스팅 업로드
6. 배포 URL에서 새 세션 전체 진행

## 13. 구현 금지

- 규칙을 UI 이벤트 안에 직접 작성
- 손님별 조건을 JavaScript에 하드코딩
- Python과 JavaScript가 다른 점수 공식을 사용
- 검산되지 않은 새 손님이나 시설 추가
- 숨은 성향 시스템 선행 구현
- 외부 UI 프레임워크 설치
