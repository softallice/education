# Week 4 — 쿠버네티스 기초

> 이번 주 한 줄: 지난주 Compose로 한 대에서 돌리던 docpilot을, 로컬 쿠버네티스(kind) 클러스터에 **Deployment + Service** 로 배포하고 스스로 살아나는 것을 눈으로 확인한다.
> docpilot 진화: **K8s 배포** — week02에서 만든 컨테이너 이미지를 클러스터에 올리고, 여러 개의 복제본(Pod)으로 띄운 뒤 Service로 노출한다.

이번 주는 [블록 1 · 클라우드 네이티브 기반]의 네 번째 주차다. 흐름은 이렇게 이어진다.

```text
week01 로컬 웹앱 ─▶ week02 컨테이너 이미지 ─▶ week03 Compose(web+DB) ─▶ [week04] K8s 배포 ─▶ week05 운영형 배포
```

- week02 참고: [week02 Docker 컨테이너 기초](./week02-docker-컨테이너-기초.md) — 오늘 클러스터에 올릴 이미지를 만든 주차.
- week03 참고: [week03 Docker Compose 멀티컨테이너](./week03-docker-compose-멀티컨테이너.md) — web+DB 구성을 K8s로 옮겨온다. 커리큘럼 전체 지도는 [README](./README.md).
- 도구·계정 준비는 [실습 환경과 기술 스택](../02-실습환경과-기술스택.md) 참조.

---

## 학습 목표

- [ ] 오케스트레이터가 왜 필요한지(스케줄링·자가치유·확장)를 한 문장으로 설명할 수 있다.
- [ ] Pod / ReplicaSet / Deployment / Service의 관계를 그림으로 그릴 수 있다.
- [ ] `kind`로 로컬 K8s 클러스터를 만들고 `kubectl`로 상태를 조회할 수 있다.
- [ ] 로컬에서 빌드한 docpilot 이미지를 `kind load docker-image`로 클러스터에 올릴 수 있다.
- [ ] Deployment + Service YAML을 작성·적용하고 `port-forward`로 접속을 확인할 수 있다.
- [ ] replica 수를 조정하고, Pod를 삭제한 뒤 자가치유되는 것을 관찰할 수 있다.

---

## 사전 준비

### 1) 지난주 산출물

week02~week03을 거치며 다음이 준비되어 있어야 한다.

- `docpilot/` 프로젝트 디렉터리 (FastAPI 앱 + `Dockerfile`)
- `GET /` → `{"message": "Hello, DocPilot"}` 와 `GET /health` → `{"status": "ok"}` 엔드포인트
- week03에서 추가한 `/documents`(업로드 메타데이터를 PostgreSQL에 저장), `db.py`, docker-compose 구성
- week02에서 만든 컨테이너 이미지 `docpilot:0.2.0` (week03에서 `/documents` 코드가 추가됨)

> 이번 주 실습은 **모든 명령을 `docpilot/` 프로젝트 루트에서** 실행한다고 가정한다.

### 2) 프로젝트 상태 복기 (이미지를 다시 빌드하기 위해)

클러스터에 올릴 이미지를 새로 빌드할 것이므로, 앱의 핵심 파일이 week03까지의 누적 상태인지 확인한다. 파일은 프로젝트 루트에 `main.py`, `db.py`, `requirements.txt`, `Dockerfile`로 있다. `/health`는 **DB에 의존하지 않고** 항상 `ok`를 돌려준다는 점이 중요하다(5주차 헬스체크의 토대가 된다).

```python
# main.py (week01~week03 누적 상태 요약 — 실제 완결본은 week03 문서 참조)
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from db import Document, SessionLocal, init_db   # week03에서 추가한 DB 모듈

app = FastAPI(title="docpilot", version="0.3.0")

@app.on_event("startup")
def on_startup() -> None:
    init_db()   # 테이블 생성. 시작 시 DB가 떠 있어야 하므로 K8s에서도 DB를 먼저 배포한다.

@app.get("/")
def root() -> dict:
    return {"message": "Hello, DocPilot"}

@app.get("/health")
def health() -> dict:
    # DB 연결 여부와 무관하게 프로세스가 살아있으면 ok
    return {"status": "ok"}

# /documents(업로드 메타 저장/조회) 라우터는 week03 그대로 둔다.
```

```dockerfile
# Dockerfile (week02 → week03 상태: db.py 추가 반영)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY db.py .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3) 도구 설치 확인

`kubectl`과 `kind`, 그리고 이미지 빌드를 위한 Docker가 필요하다.

```bash
# 각 도구가 설치되어 있는지 버전으로 확인
docker version --format '{{.Server.Version}}'   # Docker 데몬이 떠 있어야 함
kubectl version --client -o yaml | head -5      # 클라이언트 버전
kind version                                    # kind 버전
```

**확인**: 세 명령 모두 버전 문자열을 출력하면 통과. `command not found`가 나오면 설치가 필요하다.

```bash
# kind가 없다면 (Linux amd64 기준). macOS/Windows는 실습환경 문서 참조.
[ -x "$(command -v kind)" ] || {
  curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.23.0/kind-linux-amd64
  chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind
}

# kubectl이 없다면
[ -x "$(command -v kubectl)" ] || {
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  chmod +x kubectl && sudo mv kubectl /usr/local/bin/kubectl
}
```

**확인**: 다시 `kind version`, `kubectl version --client`가 정상 출력되면 준비 완료.

---

## 개념 (요약)

### 왜 오케스트레이터인가

Compose(week03)까지는 "한 대의 호스트에서 여러 컨테이너를 함께 띄우는" 수준이었다. 그런데 실제 서비스는 이런 요구가 생긴다.

- **스케줄링(scheduling)**: "이 컨테이너를 여유 있는 노드에 알아서 배치해줘."
- **자가치유(self-healing)**: "컨테이너가 죽으면 자동으로 다시 띄워줘. 항상 N개가 떠 있게 유지해줘."
- **확장(scaling)**: "트래픽이 늘면 복제본을 늘리고, 줄면 줄여줘."

쿠버네티스(K8s)는 이 세 가지를 **선언형(declarative)** 으로 처리한다. 우리는 "무엇을(desired state)" 만 YAML로 선언하고, K8s의 컨트롤러가 실제 상태(current state)를 그 선언에 계속 맞춘다(reconciliation loop). "이 명령을 실행해라(how)"가 아니라 "결과가 이래야 한다(what)"를 적는 것이 핵심 사고 전환이다.

### 핵심 오브젝트

| 오브젝트 | 한 줄 정의 | docpilot에서의 예 |
|---|---|---|
| **Pod** | 배포의 최소 단위. 1개 이상의 컨테이너를 묶은 것. IP를 하나 가진다. | uvicorn이 도는 docpilot 컨테이너 1개 = Pod 1개 |
| **ReplicaSet** | "동일한 Pod를 N개 유지"를 책임진다. 죽으면 다시 만든다. | docpilot Pod 2개 유지 |
| **Deployment** | ReplicaSet을 관리하며 **버전 롤아웃/롤백**을 담당. 우리가 직접 다루는 상위 오브젝트. | `docpilot` Deployment |
| **Service** | 여러 Pod 앞에 고정된 이름·IP를 제공하는 **내부 로드밸런서**. Pod가 죽고 살아나며 IP가 바뀌어도 접속 지점은 그대로. | `docpilot` Service (ClusterIP) |

관계를 그림으로:

```text
Deployment (버전·롤아웃 관리)
   └── ReplicaSet (개수 유지: replicas=2)
         ├── Pod (docpilot 컨테이너)  ← IP는 수시로 바뀔 수 있음
         └── Pod (docpilot 컨테이너)
Service (docpilot) ── 고정 이름/IP ──▶ label selector로 위 Pod들에 부하 분산
```

> **왜 Service가 필요한가?** Pod는 언제든 죽고 다시 생기며 그때마다 IP가 바뀐다. 그래서 Pod IP로 직접 접속하면 안 된다. Service는 `label selector`(예: `app: docpilot`)로 대상 Pod들을 묶어 **바뀌지 않는 접속 지점**을 제공한다.

### kubectl 개념

`kubectl`은 클러스터의 API 서버와 대화하는 CLI다. 대부분의 작업이 두 갈래다.

- **선언형(권장)**: `kubectl apply -f <file>.yaml` — 원하는 상태를 파일로 선언. 반복 실행해도 안전(idempotent).
- **명령형(디버깅용)**: `kubectl get / describe / logs / delete / scale ...` — 상태 조회·즉석 조작.

자주 쓰는 조회:

```bash
kubectl get pods           # Pod 목록과 상태
kubectl describe pod <name># 이벤트·원인까지 상세 조회 (트러블슈팅 1순위)
kubectl logs <pod>         # 컨테이너 로그
```

---

## 실습: 단계별 따라하기

4교시 흐름에 맞춰 **1부(클러스터 준비) → 2부(이미지 로드) → 3부(배포·노출) → 4부(확장·자가치유)** 로 진행한다.

### 1부. 로컬 K8s 클러스터 만들기

#### 1단계. 매니페스트 디렉터리와 클러스터 설정 파일 생성

프로젝트 루트에 K8s 매니페스트를 모아둘 `k8s/` 디렉터리를 만든다.

```bash
mkdir -p k8s
```

클러스터 설정 파일을 만든다. 지금은 노드 1개짜리 단순 클러스터지만, **5주차 Ingress 실습에 대비해** 호스트 80/443 포트를 노드로 매핑하고 `ingress-ready` 라벨을 붙여 둔다(이 포트 매핑은 클러스터 생성 시점에만 지정할 수 있어 미리 넣어 둔다).

```yaml
# k8s/kind-cluster.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: docpilot
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
```

#### 2단계. 클러스터 생성

```bash
# 설정 파일을 근거로 "docpilot"이라는 이름의 클러스터를 만든다
kind create cluster --config k8s/kind-cluster.yaml
```

**확인**: 마지막에 `Set kubectl context to "kind-docpilot"` 메시지가 보이면 성공. 아래로 재확인한다.

```bash
kubectl cluster-info --context kind-docpilot   # API 서버 주소 출력
kubectl get nodes                              # 노드가 Ready 상태여야 함
```

기대 출력(요약):

```text
NAME                     STATUS   ROLES           AGE   VERSION
docpilot-control-plane   Ready    control-plane   40s   v1.30.x
```

> Pod가 아직 하나도 없어도 정상이다. 시스템 컴포넌트는 `kubectl get pods -A`로 볼 수 있다.

### 2부. docpilot 이미지를 클러스터에 로드하기

#### 3단계. 이미지 빌드

kind 클러스터는 로컬 Docker 이미지 저장소와 **분리된 별도 환경**이다. 그래서 로컬에서 빌드한 이미지를 클러스터가 자동으로 볼 수 없다. 먼저 이미지를 빌드한다.

week02에서 이미지를 `docpilot:0.2.0`으로 만들었고, week03에서 `/documents`가 추가됐다. 현재 코드 상태(앱 `version="0.3.0"`)에 맞춰 새 태그로 빌드한다.

```bash
# week02 Dockerfile로 현재(week03 상태) docpilot 코드를 0.3.0 태그로 빌드
docker build -t docpilot:0.3.0 .
```

**확인**:

```bash
docker images docpilot   # docpilot  0.3.0  ...  방금 만든 이미지가 보여야 함
```

#### 4단계. `kind load`로 이미지 주입

```bash
# 로컬 이미지를 docpilot 클러스터 노드 안으로 복사한다
kind load docker-image docpilot:0.3.0 --name docpilot
```

**확인**: `Image: "docpilot:0.3.0" ... loaded` 메시지 출력. 노드 내부에서 직접 확인할 수도 있다.

```bash
docker exec -it docpilot-control-plane crictl images | grep docpilot
# docker.io/library/docpilot   0.3.0   ...   방금 로드한 이미지
```

> **핵심**: 이 단계를 빼먹으면 뒤에서 `ImagePullBackOff`가 난다. K8s가 레지스트리에서 `docpilot:0.3.0`을 받아오려다 실패하기 때문이다. 그래서 Deployment에 `imagePullPolicy: IfNotPresent`를 명시해 "로컬에 있으면 받아오지 마"라고 지시할 것이다.

### 3부. 배포하고 노출하기

#### 5단계. PostgreSQL 배포 (docpilot의 의존 DB)

week03의 web+DB 구조를 K8s에서도 유지한다. 실습용이므로 볼륨은 `emptyDir`(Pod가 사라지면 데이터도 사라짐)로 간단히 한다.

```yaml
# k8s/postgres.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docpilot-db
  labels:
    app: docpilot-db
spec:
  replicas: 1
  selector:
    matchLabels:
      app: docpilot-db
  template:
    metadata:
      labels:
        app: docpilot-db
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          ports:
            - containerPort: 5432
          env:
            # week05에서 이 하드코딩 값들을 Secret으로 뽑아낼 것이다
            - name: POSTGRES_USER
              value: "docpilot"
            - name: POSTGRES_PASSWORD
              value: "docpilot"
            - name: POSTGRES_DB
              value: "docpilot"
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: data
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: docpilot-db
spec:
  selector:
    app: docpilot-db
  ports:
    - port: 5432
      targetPort: 5432
  type: ClusterIP
```

```bash
kubectl apply -f k8s/postgres.yaml
```

**확인**: Service 이름 `docpilot-db`가 곧 docpilot의 접속 호스트명이 된다(클러스터 내부 DNS).

```bash
kubectl get pods -l app=docpilot-db    # 1/1 Running 이 될 때까지 잠시 대기
```

> `postgres:16-alpine`는 공개 이미지라 클러스터가 인터넷에서 자동으로 받아온다. **로컬 빌드 이미지(docpilot)만** `kind load`가 필요하다는 차이를 기억하자.

#### 6단계. docpilot Deployment 작성

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docpilot
  labels:
    app: docpilot
spec:
  replicas: 2                 # Pod 2개를 항상 유지
  selector:
    matchLabels:
      app: docpilot
  template:                   # 이 틀로 Pod를 찍어낸다
    metadata:
      labels:
        app: docpilot         # Service가 이 라벨로 Pod를 찾는다
    spec:
      containers:
        - name: docpilot
          image: docpilot:0.3.0
          imagePullPolicy: IfNotPresent   # 로컬에 로드한 이미지를 쓰라는 지시 (ImagePullBackOff 예방)
          ports:
            - containerPort: 8000
          env:
            # 아직은 설정을 하드코딩한다. week05에서 ConfigMap/Secret으로 외부화한다.
            - name: APP_ENV
              value: "k8s-dev"
            - name: DATABASE_URL
              # week03과 동일한 psycopg 스킴. 호스트는 Compose의 db 대신 K8s Service명 docpilot-db
              value: "postgresql+psycopg://docpilot:docpilot@docpilot-db:5432/docpilot"
```

#### 7단계. docpilot Service 작성

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: docpilot
spec:
  selector:
    app: docpilot            # 이 라벨을 가진 Pod들로 트래픽을 분산
  ports:
    - port: 80               # Service가 노출하는 포트
      targetPort: 8000       # 컨테이너(uvicorn)의 포트
  type: ClusterIP            # 클러스터 내부에서만 접근 가능한 기본 타입
```

#### 8단계. 적용하고 상태 확인

```bash
# Deployment와 Service를 한 번에 적용
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

**확인 1 — Pod가 뜨는지**:

```bash
kubectl get pods -l app=docpilot -w   # Ctrl+C로 종료. 2개가 Running / 1/1 이 되어야 함
```

기대 출력(요약):

```text
NAME                        READY   STATUS    RESTARTS   AGE
docpilot-6c9f...-abcde      1/1     Running   0          15s
docpilot-6c9f...-fghij      1/1     Running   0          15s
```

**확인 2 — 리소스 전체 조망**:

```bash
kubectl get deploy,rs,pods,svc -l app=docpilot
```

Deployment `READY 2/2`, ReplicaSet `DESIRED 2 / CURRENT 2`, Pod 2개 Running, Service `docpilot`가 보이면 배포 성공이다.

#### 9단계. describe와 logs로 들여다보기

```bash
# Pod 이름 하나를 변수에 담는다
POD=$(kubectl get pod -l app=docpilot -o jsonpath='{.items[0].metadata.name}')

kubectl describe pod "$POD"   # 하단 Events에서 Scheduled → Pulled → Created → Started 흐름 확인
kubectl logs "$POD"           # uvicorn 시작 로그 확인
```

**확인**: `describe`의 Events에 오류가 없고, `logs`에 `Uvicorn running on http://0.0.0.0:8000` 류의 메시지가 보이면 정상.

#### 10단계. port-forward로 접속 확인

`ClusterIP` Service는 클러스터 내부 전용이라 밖에서 바로 못 붙는다. 개발 중 빠른 확인엔 `port-forward`를 쓴다.

```bash
# 로컬 8080 → Service의 80 으로 터널을 뚫는다 (이 터미널은 켜 둔 채로)
kubectl port-forward service/docpilot 8080:80
```

다른 터미널에서:

```bash
curl -s http://localhost:8080/health   # {"status":"ok"}
curl -s http://localhost:8080/         # {"message":"Hello, DocPilot"}
```

**확인**: `/health`가 `{"status":"ok"}`, `/`가 `{"message":"Hello, DocPilot"}`를 반환하면, 이미지→클러스터→Deployment→Service→접속의 전 과정이 성공한 것이다. 주입한 설정이 컨테이너에 들어갔는지도 확인해 본다(이 값은 week05에서 ConfigMap으로 외부화한다).

```bash
POD=$(kubectl get pod -l app=docpilot -o jsonpath='{.items[0].metadata.name}')
kubectl exec "$POD" -- printenv APP_ENV   # k8s-dev
```

확인 후 port-forward 터미널은 Ctrl+C로 닫는다.

### 4부. 확장과 자가치유 관찰

#### 11단계. replica 수 조정 (스케일)

```bash
# 복제본을 2 → 4로 늘린다
kubectl scale deployment/docpilot --replicas=4
kubectl get pods -l app=docpilot   # Pod가 4개로 늘어남
```

**확인**: 잠시 뒤 Pod가 4개 모두 `Running`. 반대로 줄여도 본다.

```bash
kubectl scale deployment/docpilot --replicas=2
kubectl get pods -l app=docpilot   # 2개로 줄어듦 (초과분이 Terminating)
```

> 방금은 명령형으로 조정했다. 선언형으로 하려면 `deployment.yaml`의 `replicas` 값을 고치고 다시 `kubectl apply` 하면 된다. 실무에선 파일이 진실의 원천(source of truth)이어야 하므로 **파일을 고쳐 apply** 하는 습관을 들이자.

#### 12단계. Pod 삭제 → 자가치유 관찰

자가치유의 핵심 체험이다. Pod 하나를 강제로 지우고, ReplicaSet이 즉시 새 Pod를 만드는지 본다.

```bash
# 감시 창을 하나 켜 둔다 (별도 터미널)
kubectl get pods -l app=docpilot -w
```

다른 터미널에서 Pod 하나를 삭제한다.

```bash
POD=$(kubectl get pod -l app=docpilot -o jsonpath='{.items[0].metadata.name}')
kubectl delete pod "$POD"
```

**확인**: 감시 창에서 지운 Pod가 `Terminating` 되는 동시에 **새 Pod가 곧바로 `ContainerCreating` → `Running`** 으로 생성된다. 잠시 뒤에도 항상 2개가 유지된다. 이것이 "desired state = 2개"를 K8s가 지켜주는 자가치유다.

#### 13단계. (선택) 무중단 여부 감 잡기

port-forward를 다시 켜고, 반복 요청 중에 Pod를 하나 지워도 응답이 끊기는지 확인해 본다.

```bash
kubectl port-forward service/docpilot 8080:80 &   # 백그라운드로
for i in $(seq 1 30); do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/health; sleep 0.3; done
```

**확인**: 대부분 `200`이 찍힌다(간헐적 실패가 보일 수 있는데, 이는 아직 **readiness probe가 없어서** Service가 준비 안 된 새 Pod로도 트래픽을 보내기 때문이다). 이 문제를 **week05에서 probe로** 해결한다. 확인 후 `kill %1`로 port-forward를 종료한다.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| Pod가 `ImagePullBackOff` / `ErrImagePull` | 이미지를 `kind load` 안 했거나, 이름/태그 오타, 또는 `:latest` 태그라 K8s가 레지스트리에서 받으려 함 | `kind load docker-image docpilot:0.3.0 --name docpilot` 재실행. Deployment의 `image` 이름·태그 확인. `imagePullPolicy: IfNotPresent` 명시 |
| Pod가 `CrashLoopBackOff` | 컨테이너가 시작 직후 죽음(코드 오류, 잘못된 CMD, import 실패 등) | `kubectl logs <pod>` 와 `kubectl logs <pod> --previous`로 죽기 직전 로그 확인 후 코드/Dockerfile 수정→재빌드→재로드 |
| Pod가 계속 `Pending` | 스케줄 불가(리소스 부족 등) 또는 이미지 대기 | `kubectl describe pod <pod>`의 Events 확인. kind 노드가 Ready인지 `kubectl get nodes` |
| `kubectl` 이 `connection refused` | 컨텍스트가 클러스터를 안 가리킴 | `kubectl config use-context kind-docpilot` |
| `curl localhost:8080` 이 응답 없음 | port-forward가 죽었거나 대상 Pod 미준비 | port-forward 터미널이 살아있는지, `kubectl get pods`가 Running인지 확인 |
| `kind create cluster` 가 80 포트 에러 | 호스트 80/443을 다른 프로세스가 점유 | 점유 프로세스 종료, 또는 `kind-cluster.yaml`의 `hostPort`를 8080/8443으로 변경 |
| docpilot는 뜨는데 `/documents`가 500 | DB Pod 미준비 또는 DATABASE_URL 오타 | `kubectl get pods -l app=docpilot-db`가 Running인지, DATABASE_URL의 호스트가 Service명 `docpilot-db`와 일치하는지 확인 |

디버깅 3종 세트를 기억하자: **`kubectl get`(무엇이 있나) → `kubectl describe`(왜 이 상태인가, Events 확인) → `kubectl logs`(앱이 뭐라 하나)**.

---

## 이번 주 과제

`docpilot`을 로컬 kind 클러스터에 배포한 결과를 제출한다.

**제출물** (`week04/` 폴더에 모아 스크린샷 또는 텍스트 로그로):

1. `kubectl get deploy,rs,pods,svc -l app=docpilot` 출력 — Deployment 2/2, Pod 2개 Running이 보일 것.
2. `kubectl describe pod <docpilot-pod>` 의 Events 섹션 — 정상 스케줄/기동 흐름.
3. `curl http://localhost:8080/health` 와 `curl http://localhost:8080/` 결과.
4. **자가치유 증빙**: Pod 하나를 삭제한 직후 `kubectl get pods -w` 화면(삭제된 Pod와 새로 생성되는 Pod가 함께 보이는 순간).
5. `k8s/deployment.yaml`, `k8s/service.yaml`, `k8s/postgres.yaml`, `k8s/kind-cluster.yaml` 파일.
6. 짧은 회고(3~5줄): "Compose와 비교해 K8s에서 새로 얻은 것은 무엇인가?"

---

## 체크리스트

- [ ] `kind`로 `docpilot` 클러스터를 만들고 `kubectl get nodes`가 Ready를 보였다.
- [ ] `docker build`로 `docpilot:0.3.0`을 만들고 `kind load`로 클러스터에 주입했다.
- [ ] Deployment + Service YAML을 작성해 `kubectl apply` 했다.
- [ ] `get / describe / logs`로 상태를 조회할 수 있다.
- [ ] `port-forward`로 `/health`, `/` 접속을 확인했다.
- [ ] `replicas`를 늘리고 줄여 보았다.
- [ ] Pod를 삭제하고 자가치유(새 Pod 자동 생성)를 관찰했다.
- [ ] `imagePullPolicy: IfNotPresent`가 왜 필요한지 설명할 수 있다.

---

## 다음 주 예고

이번 주 배포는 **설정이 YAML에 하드코딩**되어 있고, 새 Pod로 트래픽이 성급히 흘러 간헐적 실패가 났다. [week05 — 쿠버네티스 심화와 배포](./week05-kubernetes-심화와-배포.md)에서는 이것을 **운영형 배포**로 끌어올린다.

- ConfigMap/Secret으로 **설정과 DB 자격증명 외부화**
- liveness/readiness **probe**로 죽은 Pod 재시작·준비 안 된 Pod 트래픽 차단(무중단의 열쇠)
- resources requests/limits와 **HPA(오토스케일링)**
- **Ingress**로 도메인 노출, `kubectl rollout`으로 **롤아웃/롤백**
- GitHub Actions로 **이미지 빌드·푸시(CI/CD 맛보기)**

week05는 **블록 1 미니 과제**가 걸린 주차다. 이번 주 산출물(클러스터·매니페스트)을 그대로 이어서 쓴다.
