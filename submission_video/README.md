# 제출용 플레이 영상

> 정식 게임의 장기 성장 구조를 다섯 번의 `개장 전 초청 영업`에 담은 2분 30초 제출 영상이다.

영상은 튜토리얼과 5회의 실제 영업 화면을 사용한다. N·R·SR·SSR 등장 확률, 무작위 손님·공사 제안, 수용·거절, 객실 수 기반 응대 한도와 별도 사용 가능 객실 수, 연박 객실도, `동관 증축`과 `시설·인테리어` 계약, 종족 시너지·상극, 객실 상태, 정산 뒤 열람되는 숨은 선호, 5번째 영업의 SSR 특별 초청을 보여준다. 영업 준비에서는 두 공사 구획에서 각각 최대 1건을 계약할 수 있다.

## 제출 파일 상태

- 제출 경로: `output/vespera-hotel-play-demo.webm`
- 상태: `개장 전 초청 영업` 용어를 반영한 최종 재캡처·재인코딩·독립 재생 검증 완료
- 실제 규격: 1280×720, VP8 WebM, 무음, 150.018초, 34,084,026바이트
- SHA-256: `60C473B2A025BFB57A45AC660FFD8ADA45D03C62D782E04D904A7799EFBFB634`
- 실제 플레이 화면은 장면 안에서 고정되며 커서, 클릭 파동, 강조선과 장면 전환만 움직인다.
- SSR의 시연 범위 안내는 00:06~00:15 진행 속도 안내에서 한 번만 표시한다. 왕실 손님 카드·장면 자막·최종 결과·엔드 카드에서는 반복하지 않는다.
- 인코딩 뒤 00:10, 01:16, 01:47, 01:56, 02:26을 연속 재생해 진행 안내·예약 응대 한도·왕실 손님·마지막 배치·엔드 카드를 확인한다.
- 다섯 검증 프레임의 SHA-256이 모두 다르고 화면 내용도 서로 달라, 정지 화면이 아닌 실제 장면 전환임을 확인했다.

이전 2회 영업 영상이나 짧은 녹화 시험본의 해시와 용량은 최종 제출본의 근거로 사용하지 않는다.

## 화면 에셋

`assets/`에는 다음 1280×720 PNG가 모두 있어야 한다.

`title`, `tutorial`, `handbook-ranks`, `night1`, `result1`, `upgrade-r`, `reservation2`, `result3-discovery`, `upgrade-expansion`, `night4-synergy`, `reservation5-ssr`, `night5`, `final`

- `미열람 규칙`: 아직 만나지 않은 종족 또는 등급의 공개 규정 전체. 필수 숙박 조건과 공통 선호를 함께 포함한다.
- `숨은 선호`: 해당 종족×등급 손님의 첫 숙박 정산 뒤 열람되는 추가 점수 조건
- `SSR 특별 초청`: 다섯 번째 영업에서 최종 등급의 위험과 보상을 보여주는 왕실 손님 제안

## 강조 좌표

- `box_audit/targets.json`에 실제 1280×720 에셋을 기준으로 한 장면별 좌표를 기록한다.
- 좌표가 없는 장면에는 강조선과 가상 커서를 그리지 않는다.
- 내보내기 도구가 `box_audit/scene-*.png`를 다시 만들면 모든 박스가 실제 UI 요소와 일치하는지 확인한다.

## 자동 재생 프레젠테이션

프로젝트 서버를 실행한 뒤 `http://127.0.0.1:8765/submission_video/`를 연다.

```powershell
python -m http.server 8765
```

- `Space`: 재생/정지
- `←`, `→`: 5초 이동
- `R`: 처음부터
- `F`: 전체 화면
- `개장 전 초청 영업 영상 저장`: 브라우저에서 2분 30초 WebM 생성

## 재생성 및 검증

Edge를 원격 디버깅 포트 9223으로 실행한 상태에서 먼저 미리보기와 강조 좌표를 확인한다.

```powershell
python .\tools\export_submission_video.py
```

`output/preview-*.png`와 `box_audit/scene-*.png`를 검토한 뒤 최종 WebM을 만든다.

```powershell
python .\tools\export_submission_video.py --record
python .\tools\export_submission_video.py --validate-existing
Get-FileHash .\submission_video\output\vespera-hotel-play-demo.webm -Algorithm SHA256
```

도구는 150초 타임라인, 1280×720 해상도, WebM 재생 시간과 인코딩된 다섯 시점의 장면을 검증한다. 최종 제출 전에는 영상과 공개 플레이 링크가 같은 빌드인지 다시 확인한다.
