# Week 12 — 통합 배포 & 몰입형 프로젝트 킥오프

> 이번 주 한 줄: 11주 동안 자란 docpilot **전체**(웹 + DB + 벡터DB + LLM + Agent)를 하나의 클러스터에 **통합 배포**하고, 4주 몰입형 프로젝트를 시작한다.
> docpilot 진화: 분산되어 있던 조각들을 **컨테이너 → Kubernetes**로 묶어 운영형으로 배포 + 관측성·키 관리 점검. (12주 강의의 **피날레**)

## 학습 목표

- [ ] docpilot 전체 스택을 하나의 이미지로 컨테이너화하고 K8s에 통합 배포할 수 있다.
- [ ] **Secret**으로 API 키를 안전하게 주입하고, ConfigMap으로 설정을 외부화할 수 있다(12요소 재점검).
- [ ] liveness/readiness **probe**와 리소스 requests/limits로 운영형 배포를 구성할 수 있다.
- [ ] 구조화 로그·기본 모니터링으로 **관측성**을 확보하고, 스모크 테스트로 배포를 검증할 수 있다.
- [ ] 비용·성능·보안 관점에서 배포를 점검할 수 있다.
- [ ] 4주 몰입형 프로젝트의 팀 편성·주제 선정·기획 방향을 잡을 수 있다.

## 사전 준비

- **지난주까지의 산출물**: week01~11의 docpilot 전체. 특히 week03(web+PostgreSQL compose), week04~05(K8s Deployment/Service/ConfigMap/Secret/probe/HPA/Ingress), week08(벡터DB), week11(`/report` Multi-Agent).
- **필요 도구**: Docker, `kind`(또는 minikube), `kubectl`. OpenAI API 키.

```bash
# 무엇을/왜: 도구 버전과 클러스터 준비 상태 확인
docker --version
kubectl version --client
kind --version
```

**확인**: 세 명령 모두 버전 문자열을 출력한다. 없으면 [실습 환경과 기술 스택](../02-실습환경과-기술스택.md)을 참조해 설치한다.

```bash
# 무엇을/왜: week04에서 만든 kind 클러스터가 있으면 재사용, 없으면 생성
kind get clusters | grep -q docpilot || kind create cluster --name docpilot
kubectl cluster-info --context kind-docpilot
```

**확인**: `Kubernetes control plane is running at https://...` 가 출력된다.

---

## 개념 (요약)

### 통합 배포란

지금까지는 기능을 하나씩(로컬 → 컨테이너 → K8s → AI → Agent) 붙여 왔다. 이번 주는 이 조각들을 **하나의 배포 단위로 묶어** 클러스터 위에서 함께 돌게 만든다. docpilot의 구성 요소는 이렇게 나뉜다.

```text
┌──────────────────────── Kubernetes (namespace: docpilot) ────────────────────────┐
│                                                                                    │
│   Ingress ──► Service(web) ──► Deployment(docpilot-web)  ◄── HPA (부하 따라 스케일)  │
│                                   │  probes / resources                            │
│                                   ├─► env(from ConfigMap: 설정)                     │
│                                   ├─► env(from Secret: OPENAI_API_KEY)             │
│                                   ├─► Service(postgres) ──► StatefulSet(PostgreSQL) │
│                                   └─► (벡터DB: pgvector 확장 또는 Chroma 사이드카)   │
│                                                                                    │
│   외부: OpenAI API (LLM 호출)                                                       │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 관측성(Observability)

배포는 끝이 아니라 시작이다. **로그·메트릭**이 없으면 장애를 못 본다. 이번 주는 (1) 앱이 **구조화(JSON) 로그**를 stdout에 찍고, (2) `kubectl logs`로 수집하며, (3) `/metrics`로 기본 지표를 노출하는 데까지 한다. 무거운 스택(Prometheus/Grafana) 전체 구성은 몰입형 프로젝트의 선택 과제로 남긴다.

### 12요소(12-Factor) 재점검

docpilot이 클라우드 네이티브 원칙을 지키는지 표로 되짚는다.

| 요소 | 원칙 | docpilot에서 |
|---|---|---|
| III. 설정(Config) | 설정을 환경변수로 | ConfigMap/Secret으로 주입 |
| IV. 백엔드 서비스 | DB를 attached resource로 | Postgres를 Service로 연결(URL만 교체) |
| VI. 프로세스 | 무상태 프로세스 | web 파드는 무상태, 상태는 DB/벡터DB에 |
| IX. 폐기성(Disposability) | 빠른 기동/graceful 종료 | probe + `SIGTERM` 처리 |
| XI. 로그 | 로그를 이벤트 스트림으로 | stdout JSON 로그 → `kubectl logs` |

### 비용·성능·보안

- **비용**: LLM 토큰이 가장 큰 변수. 모델을 `gpt-4o-mini`로 고정, 캐싱/상한(`MAX_TOOL_TURNS`)으로 제어. 무료 대안(HF Inference, 로컬 Ollama)도 언급.
- **성능**: resources requests/limits로 스케줄링 안정화, HPA로 부하 대응.
- **보안**: **API 키는 절대 이미지·코드·git에 넣지 않는다.** K8s Secret으로만 주입. 이미지에는 비밀이 없어야 한다.

---

## 실습: 단계별 따라하기

**1부** 컨테이너화(전체 스택), **2부** K8s 통합 배포(Secret/probe/resource/HPA/Ingress), **3부** 관측성 + 스모크 테스트 + 마무리.

---

## 1부 · 전체 스택 컨테이너화

### 1단계. 의존성·설정 정리 (12요소 III)

먼저 코드가 **모든 설정을 환경변수에서** 읽는지 확인한다. `app/config.py`(없으면 생성):

```python
"""docpilot 런타임 설정 — 전부 환경변수에서 읽는다(12-Factor III)."""
import os


class Settings:
    openai_api_key: str = os.environ["OPENAI_API_KEY"]          # 필수: 없으면 기동 실패
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql://docpilot:docpilot@postgres:5432/docpilot"
    )
    model: str = os.environ.get("DOCPILOT_MODEL", "gpt-4o-mini")
    log_level: str = os.environ.get("LOG_LEVEL", "INFO")


settings = Settings()
```

> 핵심: `os.environ["OPENAI_API_KEY"]`는 키가 없으면 **기동 시점에 즉시 실패**한다(fail-fast). 비밀을 코드에 하드코딩하지 않는다.

**확인**: `python -c "from app.config import settings; print(settings.model)"` 실행 시(키가 있으면) `gpt-4o-mini`가 출력된다.

### 2단계. requirements 고정

`requirements.txt`가 11주까지의 의존성을 모두 담는지 확인한다.

```text
fastapi
uvicorn[standard]
openai
langgraph
psycopg[binary]
pgvector
python-multipart
```

```bash
# 무엇을/왜: 로컬에서 의존성이 실제로 설치·임포트되는지 검증
pip install -r requirements.txt
python -c "import fastapi, openai, langgraph, psycopg; print('deps OK')"
```

**확인**: `deps OK` 가 출력된다.

### 3단계. 프로덕션용 Dockerfile

week02의 Dockerfile을 통합 배포용으로 다듬는다. 멀티스테이지 없이도 되지만, **비루트 실행 + 헬스체크**를 넣는다.

`Dockerfile`:

```dockerfile
FROM python:3.12-slim

# 무엇을/왜: 파이썬 버퍼링 끄기 → 로그가 즉시 stdout으로 흐름(12-Factor XI)
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

# graceful shutdown: uvicorn이 SIGTERM에 정상 종료(12-Factor IX)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

빌드하고 kind 클러스터로 로드한다:

```bash
# 무엇을/왜: 통합 이미지 빌드
docker build -t docpilot:1.0 .

# 무엇을/왜: 로컬 이미지를 kind 노드로 로드(레지스트리 없이 배포 가능)
kind load docker-image docpilot:1.0 --name docpilot
```

**확인**: `docker images | grep docpilot` 에 `docpilot 1.0` 이 보이고, `kind load` 가 에러 없이 끝난다.

---

## 2부 · Kubernetes 통합 배포

모든 매니페스트를 `k8s/` 디렉터리에 모은다.

```bash
mkdir -p k8s
```

### 4단계. Namespace + ConfigMap

`k8s/00-namespace.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: docpilot
```

`k8s/01-config.yaml` (비밀이 아닌 설정만):

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: docpilot-config
  namespace: docpilot
data:
  DOCPILOT_MODEL: "gpt-4o-mini"
  LOG_LEVEL: "INFO"
  DATABASE_URL: "postgresql://docpilot:docpilot@postgres:5432/docpilot"
```

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-config.yaml
```

**확인**: `kubectl get configmap -n docpilot` 에 `docpilot-config` 가 보인다.

### 5단계. Secret으로 API 키 주입 (보안 핵심)

**키를 YAML 파일에 적어 git에 커밋하지 않는다.** `kubectl create secret` 명령으로 직접 만든다.

```bash
# 무엇을/왜: OPENAI_API_KEY를 K8s Secret으로 생성(파일·git에 남기지 않음)
kubectl create secret generic docpilot-secrets \
  --namespace docpilot \
  --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}"
```

**확인**:

```bash
kubectl get secret docpilot-secrets -n docpilot -o jsonpath='{.data.OPENAI_API_KEY}' | base64 -d | head -c 7; echo "..."
```

`sk-...` 처럼 키 앞부분이 복원되면 정상. (Secret은 base64 인코딩일 뿐 암호화가 아니다 — 운영에선 Sealed Secrets/외부 KMS를 쓴다는 점을 언급하고 넘어간다.)

### 6단계. PostgreSQL (pgvector 포함)

벡터DB를 pgvector로 통합한다(Chroma를 별도 파드로 띄우는 대안은 트러블슈팅 참고). `k8s/02-postgres.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: docpilot
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: docpilot
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: pgvector/pgvector:pg16     # pgvector 확장이 포함된 공식 이미지
          env:
            - name: POSTGRES_USER
              value: docpilot
            - name: POSTGRES_PASSWORD
              value: docpilot
            - name: POSTGRES_DB
              value: docpilot
          ports:
            - containerPort: 5432
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "docpilot"]
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - name: pgdata
              mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
    - metadata:
        name: pgdata
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 1Gi
```

```bash
kubectl apply -f k8s/02-postgres.yaml
kubectl rollout status statefulset/postgres -n docpilot --timeout=120s
```

**확인**: `kubectl get pods -n docpilot` 에서 `postgres-0` 이 `Running` + `READY 1/1` 이 된다.

### 7단계. web Deployment (probe + resources + env 주입)

docpilot 웹/에이전트 파드. **ConfigMap→일반 설정, Secret→키**를 env로 주입하고, probe·resources를 건다. `k8s/03-web.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docpilot-web
  namespace: docpilot
  labels:
    app: docpilot-web
spec:
  replicas: 2
  selector:
    matchLabels:
      app: docpilot-web
  template:
    metadata:
      labels:
        app: docpilot-web
    spec:
      containers:
        - name: web
          image: docpilot:1.0
          imagePullPolicy: IfNotPresent      # kind에 로드한 로컬 이미지 사용
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: docpilot-config          # DOCPILOT_MODEL, LOG_LEVEL, DATABASE_URL
          env:
            - name: OPENAI_API_KEY             # 비밀은 Secret에서만
              valueFrom:
                secretKeyRef:
                  name: docpilot-secrets
                  key: OPENAI_API_KEY
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          readinessProbe:                       # 트래픽 받을 준비됐는지
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:                        # 죽었으면 재시작
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 20
---
apiVersion: v1
kind: Service
metadata:
  name: docpilot-web
  namespace: docpilot
spec:
  selector:
    app: docpilot-web
  ports:
    - port: 80
      targetPort: 8000
```

```bash
kubectl apply -f k8s/03-web.yaml
kubectl rollout status deployment/docpilot-web -n docpilot --timeout=120s
```

**확인**: `kubectl get pods -n docpilot -l app=docpilot-web` 에서 파드 2개가 `Running` + `READY 1/1`. readiness가 `/health`를 통과하지 못하면 `READY 0/1`에 머무니, 그 경우 8단계 로그로 원인을 본다.

### 8단계. HPA + Ingress (운영형)

부하 기반 오토스케일과 외부 노출. `k8s/04-hpa.yaml`:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: docpilot-web
  namespace: docpilot
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: docpilot-web
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

`k8s/05-ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: docpilot
  namespace: docpilot
spec:
  rules:
    - host: docpilot.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: docpilot-web
                port:
                  number: 80
```

```bash
kubectl apply -f k8s/04-hpa.yaml
# Ingress는 컨트롤러가 있을 때만 동작(없으면 9단계 port-forward로 테스트)
kubectl apply -f k8s/05-ingress.yaml
```

**확인**: `kubectl get hpa -n docpilot` 에 `docpilot-web` 이 보인다(`TARGETS`가 `<unknown>`이면 metrics-server 미설치 — 트러블슈팅 참고).

---

## 3부 · 관측성 + 스모크 테스트 + 마무리

### 9단계. 구조화 로그 + `/metrics` (관측성)

앱이 요청을 **JSON 한 줄**로 stdout에 찍게 미들웨어를 추가하고, 간단한 카운터를 `/metrics`로 노출한다. `app/main.py`에 추가:

```python
# app/main.py 에 추가 — 관측성(로그 + 메트릭)
import json
import logging
import sys
import time

from fastapi import Request
from fastapi.responses import PlainTextResponse

logging.basicConfig(stream=sys.stdout, level="INFO", format="%(message)s")
logger = logging.getLogger("docpilot")

_metrics = {"requests_total": 0, "errors_total": 0}


@app.middleware("http")
async def access_log(request: Request, call_next):
    """모든 요청을 JSON 한 줄 로그로 남기고 카운터를 증가시킨다."""
    start = time.time()
    _metrics["requests_total"] += 1
    try:
        response = await call_next(request)
    except Exception:
        _metrics["errors_total"] += 1
        raise
    dur_ms = round((time.time() - start) * 1000, 1)
    logger.info(json.dumps({
        "path": request.url.path,
        "method": request.method,
        "status": response.status_code,
        "duration_ms": dur_ms,
    }))
    return response


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    """Prometheus 텍스트 포맷으로 기본 지표를 노출한다."""
    return (
        f"docpilot_requests_total {_metrics['requests_total']}\n"
        f"docpilot_errors_total {_metrics['errors_total']}\n"
    )
```

이미지를 다시 빌드·로드하고 롤아웃한다:

```bash
# 무엇을/왜: 관측성 코드 반영 → 재빌드 → kind 로드 → 무중단 롤아웃(week05 복습)
docker build -t docpilot:1.1 .
kind load docker-image docpilot:1.1 --name docpilot
kubectl set image deployment/docpilot-web web=docpilot:1.1 -n docpilot
kubectl rollout status deployment/docpilot-web -n docpilot --timeout=120s
```

**확인**: `kubectl rollout status` 가 `successfully rolled out` 을 출력한다. 롤아웃이 실패하면 `kubectl rollout undo deployment/docpilot-web -n docpilot` 로 이전 버전(1.0)으로 되돌린다(롤백 복습).

### 10단계. 최종 스모크 테스트

`port-forward`로 Service를 로컬에 붙여 핵심 엔드포인트를 순서대로 두드린다.

```bash
# 무엇을/왜: 클러스터 내부 Service를 로컬 8080으로 포워딩(백그라운드)
kubectl port-forward -n docpilot service/docpilot-web 8080:80 &
sleep 3
```

`smoke.sh`(레포에 저장해 반복 사용):

```bash
#!/usr/bin/env bash
# 무엇을/왜: docpilot 통합 배포 스모크 테스트 — 헬스→RAG→Multi-Agent 순
set -euo pipefail
BASE="http://localhost:8080"

echo "[1/4] /health"
curl -fs "$BASE/health" && echo

echo "[2/4] /metrics"
curl -fs "$BASE/metrics" && echo

echo "[3/4] /ask (week08 RAG)"
curl -fs -X POST "$BASE/ask" -H "Content-Type: application/json" \
  -d '{"question": "docpilot이 무엇인가?"}' | python -m json.tool

echo "[4/4] /report (week11 Multi-Agent)"
curl -fs -X POST "$BASE/report" -H "Content-Type: application/json" \
  -d '{"topic": "docpilot의 전체 아키텍처 요약"}' | python -m json.tool

echo "SMOKE TEST PASSED"
```

```bash
chmod +x smoke.sh
./smoke.sh
```

**확인**: 4단계 모두 200 응답이 나오고 마지막에 `SMOKE TEST PASSED` 가 찍힌다. `/report` 응답의 `log`에 week11의 에이전트 협업 로그가 포함된다.

로그·메트릭도 실제로 관찰한다:

```bash
# 무엇을/왜: 방금 요청들이 JSON 로그로 수집됐는지 확인
kubectl logs -n docpilot -l app=docpilot-web --tail=20
```

**확인**: `{"path": "/report", "method": "POST", "status": 200, "duration_ms": ...}` 형태의 JSON 로그가 보인다.

### 11단계. 배포 점검 (비용·성능·보안 체크)

```bash
# 무엇을/왜: 리소스·파드·오토스케일 상태를 한 번에 점검
kubectl get all -n docpilot
kubectl top pods -n docpilot          # metrics-server 있으면 CPU/메모리 실사용
```

**확인**: web 파드 2개 + postgres 1개가 Running. 아래 셀프 체크를 통과하는지 본다.

- [ ] **보안**: 이미지·git에 API 키가 없다(`grep -r "sk-" app/ || echo clean`). 키는 Secret에만.
- [ ] **성능**: 모든 컨테이너에 resources requests/limits가 있다.
- [ ] **비용**: 모델이 `gpt-4o-mini`로 고정, tool 루프 상한(week11) 유지.
- [ ] **폐기성**: 파드를 지워도(`kubectl delete pod <name> -n docpilot`) 자동 복구되고 서비스가 안 끊긴다.

정리(선택):

```bash
# 무엇을/왜: 실습 후 클러스터 전체 삭제(비용/자원 회수)
kill %1 2>/dev/null || true          # port-forward 종료
# kind delete cluster --name docpilot   # 완전 삭제하려면 주석 해제
```

---

## 몰입형 프로젝트 킥오프 (4주)

12주 강의는 여기서 끝난다. 이제부터 **P-학기제의 4주 몰입 구간**이다. 팀 단위로 **Agentic AI 서비스를 클라우드 네이티브 방식으로 구축·배포·발표**한다. 상세 규정·루브릭은 [평가와 몰입형 프로젝트](../03-평가와-몰입형-프로젝트.md)를 따른다.

### 1. 팀 편성

- 팀 규모는 수강 인원에 맞춰 조정(권장 2~4명).
- 역할을 미리 나눈다: **백엔드/배포**(K8s·CI), **AI/Agent**(LLM·RAG·Multi-Agent), **프론트/문서·발표**. week11 Multi-Agent처럼 사람도 역할 분담이 협업의 핵심이다.

### 2. 주제 선정

docpilot이 이미 "AI API + RAG + Agent + K8s 배포"의 뼈대이므로, **docpilot을 발판(seed)** 삼아 확장하는 것이 가장 빠르다. 예시(자세한 목록은 03 문서):

- 문서 QA Agent — 사내 위키/매뉴얼 질의응답 (docpilot의 `/ask` 확장)
- 멀티 에이전트 리서치 어시스턴트 — 검색·요약·보고서 협업 (docpilot의 `/report` 확장)
- 코드/데이터 분석 Agent — 파일 업로드 → 분석 → 시각화
- 멀티모달 상담 봇 — 이미지·음성 입력 처리 후 응답 (week07 재사용)

**필수 요소**(03 문서 발췌): AI API 연계 1개 이상 · Agent 요소(도구 연동 또는 Multi-Agent) 1개 이상 · 컨테이너화 + K8s(또는 클라우드) 배포 · README + 데모.

### 3. docpilot → 프로젝트 발전 경로

| 지금 있는 것(docpilot) | 프로젝트에서 발전 방향 |
|---|---|
| `/ask` RAG (week08) | 도메인 문서로 교체, 하이브리드 검색·재랭킹 추가 |
| `/agent` 도구·MCP (week09-10) | 실제 업무 도구(캘린더/이슈트래커/파일) 연동 |
| `/report` Multi-Agent (week11) | reviewer/planner 등 역할 확장, HITL 승인 흐름 |
| K8s 통합 배포 (week12) | 클라우드(EKS/GKE) 또는 CI/CD 파이프라인, 관측성 강화 |

### 4. 기획 발표 안내

킥오프 세션에서 팀별로 **5분 기획 발표**를 준비한다. 발표에 담을 것:

1. 문제 정의 & 타깃 사용자
2. 핵심 기능(필수 요소 매핑 표)
3. 아키텍처 스케치(어떤 AI/Agent + 어떻게 배포)
4. 4주 일정 & 역할 분담

### 5. 4주 일정 (권장, 03 문서 기준)

| 주 | 활동 |
|---|---|
| 1주차 | 기획 확정·아키텍처 설계·역할 분담 (오늘 킥오프 연계) |
| 2주차 | 핵심 기능 구현 (AI/Agent 파이프라인) |
| 3주차 | 통합·컨테이너화·클라우드 배포·테스트 |
| 4주차 | 마감·발표 준비·최종 데모 |

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| web 파드 `CrashLoopBackOff` | `OPENAI_API_KEY` 미주입 → `config.py`가 기동 실패 | `kubectl get secret -n docpilot` 확인 후 5단계 Secret 재생성 |
| 파드 `READY 0/1` 지속 | readiness `/health` 실패 | `kubectl logs`/`kubectl describe pod`로 원인, `/health` 라우트 존재 확인 |
| `ImagePullBackOff` | kind에 이미지 미로드 or `imagePullPolicy` | `kind load docker-image docpilot:1.1 --name docpilot`, `imagePullPolicy: IfNotPresent` |
| DB 연결 실패 | Postgres 미기동 or `DATABASE_URL` 불일치 | `postgres-0` Running 확인, ConfigMap의 URL과 Service명 일치 확인 |
| `pgvector` 확장 없음 | 일반 postgres 이미지 사용 | 이미지를 `pgvector/pgvector:pg16`으로, 최초 `CREATE EXTENSION vector;` 실행 |
| Chroma를 쓰고 싶다 | pgvector 대신 별도 벡터DB | `chromadb/chroma` 이미지를 별도 Deployment+Service로 띄우고 앱 설정만 교체 |
| HPA `TARGETS <unknown>` | metrics-server 미설치 | `kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml` (kind는 `--kubelet-insecure-tls` 패치 필요) |
| Ingress 접속 불가 | Ingress 컨트롤러 없음 | 학습용은 `kubectl port-forward`로 대체(10단계) |
| `kubectl top` 에러 | metrics-server 없음 | 위 HPA 항목과 동일하게 설치 |

---

## 이번 주 과제

**몰입형 프로젝트 기획서 제출 (팀 단위).**

`기획서.md`에 아래를 담는다:

1. 팀명·구성원·역할 분담
2. 문제 정의 & 타깃 사용자
3. 핵심 기능 목록 + **필수 요소 매핑 표**(AI API / Agent 요소 / 배포 / 문서·데모가 각각 어디서 충족되는지)
4. 아키텍처 스케치(다이어그램 또는 텍스트)
5. 4주 일정 & 마일스톤
6. docpilot에서 무엇을 재사용하고 무엇을 새로 만들지

**추가 개인 제출물**: 이번 주 통합 배포 결과 증빙 — `kubectl get all -n docpilot` 출력 + `./smoke.sh`의 `SMOKE TEST PASSED` 로그를 담은 `week12-배포증빙.md`.

> 평가 기준·루브릭은 [평가와 몰입형 프로젝트](../03-평가와-몰입형-프로젝트.md)를 반드시 확인한다.

---

## 체크리스트

- [ ] docpilot 전체를 단일 이미지로 컨테이너화하고 kind에 로드했다.
- [ ] Namespace/ConfigMap/Secret으로 설정·비밀을 외부화했다(12요소 III).
- [ ] Postgres(pgvector) + web Deployment가 클러스터에서 함께 Running이다.
- [ ] probe·resources·HPA·Ingress로 운영형 배포를 구성했다.
- [ ] 구조화 로그 + `/metrics`로 관측성을 확보하고 `kubectl logs`로 확인했다.
- [ ] `./smoke.sh`가 `/health`→`/ask`→`/report`를 통과했다.
- [ ] 비용·성능·보안 셀프 체크(11단계)를 통과했다.
- [ ] (팀) 몰입형 프로젝트 기획서를 작성했다.

---

## 12주 강의 마무리 & 몰입 4주 안내

수고했다. 1주차의 `Hello, DocPilot` 로컬 웹앱이, 12주차에는 **K8s에 통합 배포된 Multi-Agent Agentic AI 서비스**로 자랐다. 버린 코드 없이 매주 같은 프로젝트를 키워 온 결과다.

- **블록 1(1–5주)**: 로컬 웹앱 → 컨테이너 → Compose+DB → K8s → 운영형 배포
- **블록 2(6–8주)**: LLM 챗 → 멀티모달/HF → RAG
- **블록 3(9–11주)**: 단일 Agent → 도구·MCP → Multi-Agent
- **통합(12주)**: 전체 K8s 통합 배포 + 관측성 + 프로젝트 킥오프

이제 이 역량을 **4주 몰입형 프로젝트**에서 팀 단위로 증명한다. docpilot을 발판 삼아, 여러분의 문제를 푸는 Agentic AI 서비스를 만들고 배포하고 발표하자. 세부 운영·평가는 [평가와 몰입형 프로젝트](../03-평가와-몰입형-프로젝트.md)에서 이어진다. 전체 강의 맥락은 [강의 개요](../00-강의개요.md)와 [주차별 커리큘럼 README](./README.md)를 참조한다.
