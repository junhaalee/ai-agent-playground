FROM mwader/static-ffmpeg:latest AS ffmpeg

FROM n8nio/n8n:1.70.3
USER root

COPY --from=ffmpeg /ffmpeg /usr/bin/ffmpeg

RUN apk add --no-cache fontconfig font-noto-cjk       # ffmpeg 자막을 위한 한글 폰트 설치
RUN fc-cache -f                                       # 폰트 캐시 갱신
RUN mkdir -p /app/images /app/videos /app/scripts /app/workflow
RUN chown -R node:node /app

# 워크플로우 JSON 및 entrypoint 복사
COPY workflow/workflow.json /app/workflows/workflow.json
COPY script/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER node

ENTRYPOINT ["/app/entrypoint.sh"]
