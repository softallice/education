# api/Dockerfile — docpilot FastAPI (교안 week02 컨테이너화 패턴)
FROM python:3.12-slim

# 파이썬 버퍼링 끄기 → 로그가 즉시 stdout 으로(12-Factor XI)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 의존성 레이어 캐시 최적화: requirements 먼저 복사
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스 복사
COPY app ./app

# 비루트 유저로 실행(보안)
RUN useradd -m appuser
USER appuser

EXPOSE 8000

# 0.0.0.0 바인딩: 컨테이너 밖에서 접속 가능하게
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
