# 프로젝트 컨텍스트

- 한국어로 답변
- 이 프로젝트는 뉴스 기사로 YouTube Shorts 영상을 자동 생성/업로드하는 파이프라인

## 구조

- `junhaalee/` — 메인 프로젝트 디렉토리
  - `n8n/` — n8n 워크플로우 (영상 생성)
  - `python/` — YouTube 업로드 (watchdog)

## 서비스

| 서비스 | 역할 |
|--------|------|
| n8n (v1.70.3) | Input JSON → 이미지 다운로드 → OpenAI 자막 생성 → ffmpeg 영상 생성 |
| python (3.12-slim) | /app/videos/ 감시 → YouTube 자동 업로드 |

## 파이프라인

```
[Input JSON] → [n8n Workflow] → [ffmpeg 영상] → [Python Watchdog] → [YouTube 업로드]
```

## n8n 워크플로우 (3개 병렬 분기)

```
Read File ─┬─ Code (이미지 다운로드)  → Write File → Execute Command (ffmpeg)
           ├─ Code1 (텍스트 파싱)    → OpenAI → Code2 (SRT) → Write File ─┘
           └─ Execute Command1 (mkdir -p)
```

## 주요 기술 사항

- n8n 1.70.3 사용 (Execute Command 노드 필요. 2.6.4에는 없음)
- n8n Code 노드에서 `child_process`, `fs` 사용 불가 (sandbox)
- Binary 데이터: `this.helpers.getBinaryDataBuffer(0, 'data')` 사용
- 한글 자막: `font-noto-cjk` + `fc-cache` 필요
- 파일 경로: `/app/{images|scripts|videos}/{yyyyMMdd-HH}/` (KST 기준)
- KST 처리: shell에서 `TZ=Asia/Seoul date`, JS에서 `+9*60*60*1000`
- OpenAI 노드는 커스텀 필드(dirName)를 전달하지 않음 → 각 Code 노드에서 독립 계산
- Docker named volumes: videos (n8n↔python 공유), images, scripts, n8n_data

## 실행

```bash
cd junhaalee
docker compose up -d --build
```

## 파일 참고

- `docker-compose.yml` — 서비스 오케스트레이션
- `n8n/Dockerfile` — ffmpeg + 한글폰트 포함 커스텀 이미지
- `n8n/script/entrypoint.sh` — 워크플로우 자동 import + n8n 실행
- `n8n/workflow/workflow.json` — n8n 워크플로우 정의
- `python/main.py` — YouTube 업로드 + watchdog
- `python/util/WatchdogUtil.py` — 파일 감시 유틸

## 주의사항

- `client_secret.json`, `token.json`, `api-key.txt`는 gitignore 대상
- OpenAI credential은 n8n 웹에서 수동 등록 필요
- workflow.json을 웹에서 수정했으면 파일 최신화 필요
