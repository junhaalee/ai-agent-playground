#!/bin/sh

# 워크플로우 JSON 파일이 있으면 자동 import
if [ -f /app/workflows/workflow.json ]; then
  n8n import:workflow --separate --input=/app/workflows
  echo "Workflow imported successfully"
fi

# n8n 실행
exec n8n start
