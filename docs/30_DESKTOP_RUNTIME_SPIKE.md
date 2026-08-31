# Electron 데스크톱 런타임 스파이크

- 상태: `FUNCTIONAL SPIKE PASS · NATIVE EXCEPTION INCIDENT REOPENED · NOT RELEASE READY`
- 기준일: 2026-08-31
- 목적: 검증된 웹 코어를 재작성하지 않고 Windows 로컬 실행파일, 오프라인 자산 기동과 운영체제 사용자 경로의 파일 저장을 증명한다.
- 권위 범위: 이 문서는 데스크톱 스파이크의 구조·검증·한계를 소유한다. 게임 규칙과 세이브 의미는 `08_TECHNICAL_DESIGN.md`, `24_SAVE_AND_RUN_STRUCTURE.md`를 따른다.

## 1. 결론

Electron 44.0.0을 현재 개발 셸로 채택한다. 개발 실행과 수동 조립한 win32-x64 폴더 패키지가 모두 `vespera://app/`의 로컬 자산만으로 기동했고, 기존 웹 코어는 같은 저장 키와 상태 전환을 유지한 채 파일 저장 어댑터를 사용했다. 쿼리 없는 Electron 시작 주소는 캠페인·무한 영업·초청 영업을 고르는 모드 허브로 진입하며, 쿼리 없는 브라우저 주소는 기존 `SHOWCASE` 시작 계약을 유지한다. Electron 렌더러에서는 파일이 저장 권위이고 브라우저 개발·과거 쇼케이스에서는 `localStorage` 대체 경로를 계속 사용한다.

이 결과는 임시 플랫폼 어댑터의 기능 계약을 증명한 스파이크다. 이후 모드 허브 본창이 보이는 상태에서 `electron.exe`의 `0x80000003` 네이티브 예외 창이 다시 관측됐으므로 제품 실행 안정성 사건은 닫히지 않았다. 설치 프로그램, 서명, Steam 계정·Cloud, 정식 캠페인 파일 기반 완주와 출시 QA가 끝난 제품 빌드도 아니다. 설치 크기가 핵심 제약으로 확정될 때만 Tauri 2 비교를 다시 연다.

## 2. 런타임 경계

```text
기존 HTML/CSS/ES Modules 게임 코어
  → sandboxed renderer
  → preload의 제한된 동기식 Storage 호환 API
  → main process의 FileStorageService
  → OS별 Electron userData/save-data/v1/profiles/local
```

- `desktop/main.cjs`는 표준 파일 URL 대신 권한 있는 사용자 정의 `vespera://app/` 프로토콜을 등록한다.
- 프로토콜은 `index.html`, `styles.css`, 허용된 `src/`, `data/` 런타임 자산만 읽고 `package.json`, `desktop/`, 상위 경로 접근을 거부한다.
- preload는 `platform`, 저장 준비 상태·오류, `getItem`·`setItem`·`removeItem`, 제한된 진단만 노출한다. Node와 임의 IPC·파일 경로는 렌더러에 노출하지 않는다.
- Electron 창은 `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, `webSecurity: true`를 사용한다. 새 창과 외부 내비게이션, 권한 요청과 사전 권한 확인도 기본 거부한다.
- `index.html`의 CSP는 기본 자산을 자체 프로토콜로 제한한다. 스파이크를 통과시키기 위해 `--no-sandbox` 같은 보안 완화는 사용하지 않았다.
- 모드 허브는 `CAMPAIGN`, `ENDLESS`, `SHOWCASE`의 별도 체크포인트 상태만 요약하며 손상 JSON이나 다른 모드의 저장을 재개 가능으로 표시하지 않는다. 선택 시 `mode`만 지정하고 이전 `seed`는 제거한다.
- 허브는 CDP Tab→Space 신뢰 입력으로 모드를 선택할 수 있다. 테스트 전용 시작 인자로 실제 외곽 창을 960×600으로 만들었을 때 콘텐츠 영역은 944×561이었고 카드·주요 행동이 잘리거나 overflow가 생기지 않았다. 1280×720·960×600 콘텐츠 viewport 에뮬레이션은 보조 증거로 분리했다.

## 3. 파일 저장 계약

기본 로컬 프로필의 저장 루트는 다음과 같다.

```text
app.getPath("userData")/
└─ save-data/v1/profiles/local/
   ├─ profile.v1.json
   ├─ run-records.v1.json
   ├─ active-run.v1.legacy.json
   ├─ active-run.v2.<mode>.json
   ├─ *.bak
   └─ corrupt/
```

`profiles/local`은 운영체제 사용자별 `userData`에 속하는 단일 로컬 네임스페이스다. 현재 검증은 서로 다른 합성 `userData` 루트가 저장을 공유하지 않는다는 뜻이며, Steam ID 귀속이나 실제 복수 Windows 계정 인증을 완료했다는 뜻은 아니다.

각 파일은 다음 보호 계약을 사용한다.

- 파일 스키마 버전, 원래 저장 키, revision, 저장 시각, JSON payload와 SHA-256 checksum을 가진 envelope
- 키 허용 목록, 모드 ID, JSON 형식, 파일당 8 MiB와 전체 24 MiB 상한 검증
- 임시 파일 기록·파일 동기화 뒤 원자 교체와 직전 정상 revision의 `.bak` 보존
- 손상 primary 격리와 이전 정상 backup 복구, primary가 사라지고 동적 모드 backup만 남은 경우의 부트스트랩 복구
- 삭제 tombstone으로 오래된 backup이 제거한 런을 되살리지 못하게 방지
- 종료 기록은 저장 뒤 같은 원문이 다시 읽히는지 확인한 다음에만 활성 런을 제거
- 실행 기록 쓰기가 예외를 내거나 조용히 무시되면 종료를 확정하지 않고 정확한 활성 체크포인트를 남겨 재개 가능
- 캠페인·무한 영업·초청 영업의 primary와 backup은 함께 존재할 수 있으며, 앱 재시작 뒤 선택한 모드가 자기 단계·시드·영업일을 정확히 재개
- 한 모드 종결 시 그 모드에만 tombstone을 쓰고 다른 모드의 primary·backup 원문 바이트를 변경하지 않는 삭제 경계

checksum은 우발적 손상을 탐지하기 위한 장치이며 변조·치트를 막는 암호학적 인증 수단이 아니다. 손상 격리 파일 보존 상한, 디스크 가득 참·읽기 전용·전원 차단 단계별 주입과 사용자용 복구 안내도 출시 전 과제로 남는다.

## 4. 패키징 경계

- `package.json`은 Electron `44.0.0`을 정확히 고정한다.
- `desktop/package.cjs`는 Electron 런타임과 필요한 게임 자산만 `out/Vespera Hotel-win32-x64/`로 복사하고 실행파일을 `VesperaHotel.exe`로 이름 붙이는 얇은 스파이크 패키저다.
- 초기 검토한 Electron Forge는 종속성 감사에서 높은 위험의 취약 종속성을 포함해 제거했다. 현재 lockfile의 설치 종속성 감사 결과는 0건이었다.
- `out/`, `node_modules/`, 도구용 `.tmp/`는 Git에서 제외한다. 기존 공개 웹 빌드와 ZIP은 수정하지 않는다.
- 현재 manifest의 SHA-256은 실행파일 한 개만 확인한다. JS·데이터·preload·저장 코드 전체를 포괄하는 출시 무결성 영수증은 아니다.

따라서 현재 폴더 패키지는 로컬 스파이크 산출물이다. installer/uninstaller, ASAR·fuse·integrity 강화, 아이콘·버전 메타데이터, 코드 서명·SmartScreen, 라이선스 고지와 재현 가능한 빌드가 추가되기 전에는 배포 후보로 승격하지 않는다.

## 5. 재현 명령

Node.js/npm을 사용할 수 있는 개발 환경에서는 다음 순서로 재현한다.

```powershell
npm ci
npm run test:desktop:unit
npm run desktop:package
npm run test:desktop:dev
npm run test:desktop:packaged
```

이번 스파이크는 시스템 Node.js를 설치하지 않고 Git에서 제외한 공식 Node 24.20.0 휴대용 런타임으로 수행했다. 결과가 안정적이므로 이후 정식 빌드 환경을 고정할 때만 시스템 또는 CI 도구 설치를 결정한다.

## 6. 2026-08-30 검증 결과

| 검증 | 결과 | 증명 범위 |
| --- | --- | --- |
| 파일 저장 단위 계약 | `9/9 PASS` | 분리·재실행, 손상/backup 복구, backup 단독 부트스트랩, checksum, tombstone, 키·용량, 사용자 루트 분리, 지연 진단 |
| 모드 허브 단위 계약 | `10/10 PASS` | 모드 ID, 기존 `readActiveRunSave` 권위와 원시 후보 분리, 유효·손상·불일치 체크포인트, 쇼케이스 v1 보조 조회, 저장소 예외, 모드·허브 URL |
| Electron 개발 실행 | `PASS` | 쿼리 없는 허브, 실제 외곽 창 960×600·콘텐츠 944×561, Tab→Space, 오프라인 허브·SHOWCASE 데이터, 보안 표면, 세 모드 파일 공존·재시작 재개, 종결 삭제 격리 |
| 폴더 패키지 실행 | `PASS` | 위 계약을 이름 변경한 실제 `VesperaHotel.exe`에서 재검증 |
| 동기식 파일 변경 지연 | 개발 p95 `14.264 ms`, 최종 패키지 p95 `11.206 ms` | 첫 프로필의 허브·세 모드 저장 공존 과정에서 측정한 운영체제 사용자 드라이브 17회 FileStorage mutation 표본; 종단 격리는 별도 회귀이며 장기 성능 판정 아님 |
| 기존 브라우저 회귀 | `PASS` | 최종 변경 뒤 queryless 1280×720 SHOWCASE 5영업, 기존 시간제 영업, 캠페인·무한 영업 뼈대와 브라우저 fallback 보존 |
| 종료 기록 내구 회귀 | `PASS` | 정상 STORY 체크포인트에서 기록 저장 실패 시 원문 보존·미확정·동일 단계/시드 재개 |
| 모드 종결·격리 회귀 | `PASS` | 캠페인 `completeRun()`의 `CAMPAIGN_INTERRUPTED` 종결과 무한 영업 5-operation 감사 실패 종결에서 대상 tombstone, 비대상 primary·backup 바이트 불변, 재시작 후 비대상 정확 재개 |

오프라인 검증은 CDP 네트워크 에뮬레이션과 로드 자원 검사를 함께 사용했다. 게임 자산이 HTTP에 의존하지 않는다는 증거이며, 기본 제품 실행의 모든 패킷을 캡처했거나 클린 PC 설치를 통과했다는 뜻은 아니다. 두 저장 루트 분리도 OS 범위를 모사한 계약 시험이지 실제 Steam 두 계정 시험이 아니다.

첫 자동 실행은 제한된 Codex 관리 프로세스 환경에서 Chromium Mojo IPC 생성이 Windows 오류 `0x5`로 차단되어 렌더러 진입 전 `electron.exe`의 `0x80000003` 예외 창을 냈다. 소유한 프로세스 트리를 정리하도록 하네스를 보강하고, 상속된 `ELECTRON_RUN_AS_NODE`·Crashpad 환경을 제거한 뒤 일반 사용자 권한에서 다시 실행했을 때 개발·패키지 기능 회귀는 Electron 보안 sandbox를 유지한 채 PASS했다.

그러나 2026-08-31 사용자의 예시 플레이 중 모드 허브 본창과 함께 같은 코드의 네이티브 예외 창이 다시 보였다. 언제 발생했는지, main·renderer·GPU·utility 중 어느 프로세스가 예외를 냈는지, 해당 프로세스가 자동 복구됐는지는 아직 증거가 없다. 따라서 최초 오류를 관리 환경 한정 사건으로 닫았던 판단은 철회한다. 기능 회귀 PASS는 유지하되 실행 안정성은 `OPEN INCIDENT`이며, crash dump·프로세스 역할·stderr와 정확한 재현 순서를 확보하기 전에는 게임 JavaScript 결함이나 Chromium 자식 프로세스 결함으로 단정하지 않는다. 별도 시스템 설치나 `--no-sandbox` 우회도 진단 근거 없이 적용하지 않는다.

작업 드라이브에서 한 차례 관측된 약 4.9초 p95는 동시에 높은 디스크 큐와 다른 개발 프로세스 쓰기가 있었던 환경 결합값이다. 실제 기본 `userData`가 위치하는 운영체제 사용자 드라이브에서 최종 허브 통합본의 첫 프로필을 다시 검증해 개발 14.264ms를 측정했고, 외부 F: 디스크 포화를 피해 동일 최종 패키지를 운영체제 임시 폴더에서 다시 실행한 회귀는 11.206ms였다. 이 값도 허브·세 모드 저장 공존 과정의 17회 FileStorage mutation이라는 작은 기능 회귀 표본이므로, 큰 56/70일 세이브·저사양 저장장치·백신 검사 환경을 별도로 확인하기 전에는 hitch-free 성능을 선언하지 않는다.

## 7. 출시 전 남은 게이트

1. 설치·제거, 제품 메타데이터·아이콘, 코드 서명, SmartScreen과 클린 Windows VM 검증
2. Electron 보안 패치 정책, 라이선스 고지, 전체 산출물 무결성·재현 가능한 빌드
3. Steamworks, Steam ID별 프로필, Steam Cloud, 충돌 정책·복구 UI와 실제 두 계정 시험
4. 기존 웹 `localStorage`의 명시적 export/import 또는 일회성 이전 도구
5. 캠페인 슬롯 수와 실행 기록·운영 수첩까지 지우는 완전 초기화 범위 확정
6. 플레이어에게 보이는 저장 실패·backup 복구·손상 격리 안내
7. 현재 5영업 회색 상자를 넘어 Electron 파일 저장으로 정식 캠페인 56/70일, 무한 영업 장기 런과 큰 저장을 종단 검증
8. 디스크 가득 참·읽기 전용·강제 종료·백신 경합과 장기 동기식 쓰기 성능 시험
9. 활성 런 삭제 중 backup tombstone과 primary tombstone 사이의 강제 실패, 첫 쓰기 실패를 주입하고 삭제 실패 전파·재개 정책을 확정
10. `0x80000003` 재발 시점의 정확한 프로세스 역할·PID·stderr·Crashpad dump를 수집하고, main 창 생존·자식 프로세스 자동 재생성·GPU 가속의 영향을 분리 재현

플랫폼 기능 스파이크 PASS는 네이티브 실행 안정성 PASS가 아니며, 게임 자체의 정식 콘텐츠, 생성기, 경제 밸런스, 아트·오디오와 출시 QA 완료도 의미하지 않는다. 다음 기능적 뼈대 작업은 기존 로드맵 순서를 계속 따르되 Electron 예외 진단을 별도 P0로 유지한다.
