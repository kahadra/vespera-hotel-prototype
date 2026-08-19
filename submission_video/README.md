# 제출용 플레이 영상

## 바로 제출할 파일

- `output/vespera-hotel-play-demo.webm`
- 1280×720, VP8 WebM, 무음, 150.209초
- 34,860,334 bytes
- SHA-256: `B0C3AFEBC2D9538EEEAA2F8D396461A132F8E077E3170FB95AC79B6F822F1E84`

## 보관용 고화질 파일

- `output/vespera-hotel-play-demo-hq.webm`
- 1280×720, VP8 WebM, 무음, 150.209초
- 80,517,587 bytes
- SHA-256: `7CBC12F8A09E90352A669622ED6657A20689C211372C1C71B33F59A83028908F`

제출 플랫폼의 업로드 한도가 넉넉하더라도 기본 제출본을 우선 사용한다. UI 글자가 충분히 선명하고 업로드와 재생이 더 빠르다.

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
