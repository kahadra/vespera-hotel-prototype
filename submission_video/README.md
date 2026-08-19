# 제출용 플레이 영상

## 바로 제출할 파일

- `output/vespera-hotel-play-demo.webm`
- 1280×720, VP8 WebM, 무음, 150.228초
- 34,141,307 bytes
- SHA-256: `C44FDFECE15C45046DC9088516BD6F68ECB10374C108DD761546492FFECA2B22`
- 실제 플레이 화면은 장면 안에서 고정되며 커서, 클릭 파동, 강조선과 장면 전환만 움직인다.
- `box_audit/`에는 강조 박스가 있는 12개 장면의 중간 프레임이 있다.

## 자동 재생 프레젠테이션

프로젝트 서버를 실행한 뒤 `http://127.0.0.1:8765/submission_video/`를 연다.

```powershell
python -m http.server 8765
```

- `Space`: 재생/정지
- `←`, `→`: 5초 이동
- `R`: 처음부터
- `F`: 전체 화면
- `2분 30초 영상 저장`: 브라우저에서 WebM 다시 생성

## 재생성 및 검증

Edge를 원격 디버깅 포트 9223으로 실행한 상태에서 다음 명령을 사용한다.

```powershell
python .\tools\export_submission_video.py --record
```

도구는 150초 타임라인, 1280×720 해상도, 최종 WebM 재생 시간을 검증한다. `STORYBOARD.md`에 구간별 전달 내용을 기록했다.
