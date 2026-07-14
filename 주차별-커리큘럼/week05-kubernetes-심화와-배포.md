# Week 5 — 쿠버네티스 심화와 배포

> 이번 주 한 줄: week04에서 하드코딩·불안정하게 배포했던 docpilot을, **설정 외부화 · 헬스체크 · 오토스케일링 · Ingress · 무중단 롤아웃/롤백** 을 갖춘 **운영형 배포**로 끌어올린다.
> docpilot 진화: **운영형 배포** — ConfigMap/Secret, probe, resources, HPA, Ingress, rollout을 붙인다.

> **이 주차는 [블록 1] 미니 과제 주차다.** week01~week05를 통해 만든 "설정이 외부화되고 무중단으로 배포되는 서비스"가 블록 1의 결승선이다. 과제 요구사항을 미리 읽고 실습하면서 증빙을 모으자.

```text
week03 Compose ─▶ week04 K8s 배포(하드코딩) ─▶ [week05] 운영형 배포(외부화·무중단) ─┃ 블록1 끝 ┃─▶ week06 LLM 챗
```

- 직전 주차: [week04 쿠버네티스 기초](./week04-kubernetes-기초.md) — 오늘은 그 클러스터·매니페스트를 그대로 이어 쓴다.
- 평가·미니 과제 기준: [평가와 몰입형 프로젝트](../03-평가와-몰입형-프로젝트.md).

---

## 학습 목표

- [ ] 설정을 코드/이미지에서 분리해야 하는 이유(12-Factor의 config)를 설명할 수 있다.
- [ ] ConfigMap(비밀 아님)과 Secret(민감정보)을 구분해 사용할 수 있다.
- [ ] liveness / readiness probe의 차이를 알고 `/health`에 연결할 수 있다.
- [ ] resources requests/limits를 설정하고, 그것이 HPA의 전제임을 안다.
- [ ] HPA로 CPU 부하에 따라 Pod가 자동으로 늘고 주는 것을 관찰할 수 있다.
- [ ] Ingress로 docpilot을 도메인으로 노출할 수 있다.
- [ ] `kubectl rollout`으로 무중단 롤아웃/롤백을 수행할 수 있다.
- [ ] GitHub Actions로 이미지를 빌드·푸시하는 워크플로우를 이해한다.

---

## 사전 준비

week04를 마친 상태에서 시작한다. 클러스터와 매니페스트가 살아있는지 확인한다.

```bash
kubectl config use-context kind-docpilot      # 컨텍스트 확인
kubectl get pods -l app=docpilot              # docpilot Pod 2개 Running
kubectl get pods -l app=docpilot-db           # DB Pod 1개 Running
```

**확인**: docpilot 2개 + DB 1개가 Running이면 그대로 진행. 클러스터를 지웠다면 week04의 1~8단계를 다시 실행해 복구한 뒤 오자.

> 만약 week04에서 `kind-cluster.yaml`의 포트 매핑(80/443)을 넣지 않고 클러스터를 만들었다면, Ingress 실습(4부)을 위해 클러스터를 다시 만들어야 한다. 포트 매핑은 **생성 시점에만** 지정 가능하기 때문이다. 이 경우 week04 1부를 다시 수행하고 이미지 재로드·매니페스트 재적용 후 오자.

---

## 개념 (요약)

### 1) 설정 외부화 (Config Externalization)

12-Factor App의 3번 원칙: **"설정은 환경에 저장하라(store config in the environment)."** 코드/이미지는 환경에 무관하게 동일해야 하고, 환경별로 달라지는 값(DB 주소, 로그레벨, 자격증명)은 **밖에서 주입**해야 한다. week04에서 우리는 이걸 어겼다(YAML에 `DATABASE_URL`, 비밀번호를 박아 넣음). 이번 주에 바로잡는다.

- **ConfigMap**: 비밀이 아닌 설정값(예: `APP_ENV`, `LOG_LEVEL`).
- **Secret**: 민감정보(예: DB 비밀번호, API 키). 값이 **base64 인코딩**되어 저장된다.

> ⚠️ Secret은 **암호화가 아니라 인코딩**이다. base64는 누구나 되돌릴 수 있다. 진짜 운영에서는 클러스터 저장소 암호화(EncryptionConfiguration), 또는 Sealed Secrets / External Secrets / 클라우드 KMS를 쓴다. 그리고 **`secret.yaml`은 git에 커밋하지 않는다**(`.gitignore`).

### 2) 헬스체크: probe

K8s는 세 가지 probe로 컨테이너 상태를 판단한다.

| probe | 질문 | 실패하면 | docpilot 설정 |
|---|---|---|---|
| **liveness** | "이 컨테이너 살아있나(교착 아닌가)?" | 컨테이너를 **재시작** | `GET /health` |
| **readiness** | "이제 트래픽 받아도 되나?" | Service 대상에서 **제외**(트래픽 차단) | `GET /health` |
| startup | "느린 초기화가 끝났나?" | (초기화 대기, 이번 주는 생략) | — |

> week04에서 새 Pod로 트래픽이 성급히 흘러 간헐 실패가 났던 문제는 **readiness probe**가 해결한다. 준비 안 된 Pod는 Service가 트래픽을 안 보낸다 → 무중단 롤아웃의 핵심.

### 3) resources requests / limits

- **requests**: 스케줄러가 "이 Pod에 최소 이만큼은 확보해줘"라고 보장하는 양. **HPA의 사용률 계산 기준**이 된다.
- **limits**: "이 이상은 못 쓴다"는 상한. CPU 초과는 throttling, 메모리 초과는 OOMKill.

> HPA가 "CPU 50% 사용" 같은 목표를 계산하려면 **requests가 반드시 설정**돼 있어야 한다. requests가 없으면 HPA는 사용률을 `<unknown>`으로 표시한다.

### 4) 오토스케일링 (HPA)

HorizontalPodAutoscaler는 지표(CPU 등)를 보고 Deployment의 `replicas`를 자동 조정한다. 지표 수집을 위해 **metrics-server**가 클러스터에 필요하다(kind엔 기본 미설치).

### 5) Ingress

Service(ClusterIP)는 클러스터 내부 전용이다. **Ingress**는 클러스터 바깥의 HTTP(도메인/경로)를 내부 Service로 라우팅하는 L7 진입점이다. Ingress 규칙을 실제로 처리하려면 **Ingress Controller**(여기선 ingress-nginx)가 있어야 한다.

### 6) 롤아웃 / 롤백

Deployment는 이미지·설정이 바뀌면 **RollingUpdate** 전략으로 Pod를 점진 교체한다. `maxUnavailable`/`maxSurge`로 교체 중 가용성을 통제하고, 문제가 생기면 **이전 리비전으로 롤백**한다.

### 7) CI/CD 개념

- **CI(지속적 통합)**: push할 때마다 자동으로 빌드·테스트·이미지 생성. (오늘 GitHub Actions로 맛본다)
- **CD(지속적 배포)**: 만들어진 이미지를 자동으로 클러스터에 반영. (개념만 소개; 실제 배포 연결은 kubeconfig 시크릿/GitOps 필요)

---

## 실습: 단계별 따라하기

**1부 설정 외부화 → 2부 probe·리소스 → 3부 HPA → 4부 Ingress → 5부 롤아웃/롤백 → 6부 CI/CD 맛보기** 로 진행한다. 모든 명령은 `docpilot/` 프로젝트 루트에서.

### 1부. ConfigMap / Secret으로 설정 외부화

#### 1단계. ConfigMap 작성

```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: docpilot-config
data:
  APP_ENV: "k8s-prod"
  LOG_LEVEL: "info"
```

#### 2단계. Secret 작성

`stringData`를 쓰면 평문으로 적어도 K8s가 저장 시 자동으로 base64 인코딩해 준다(직접 인코딩할 필요 없음).

```yaml
# k8s/secret.yaml  ← git에 커밋하지 말 것 (.gitignore에 추가)
apiVersion: v1
kind: Secret
metadata:
  name: docpilot-db-secret
type: Opaque
stringData:
  POSTGRES_USER: "docpilot"
  POSTGRES_PASSWORD: "docpilot"
  POSTGRES_DB: "docpilot"
  DATABASE_URL: "postgresql+psycopg://docpilot:docpilot@docpilot-db:5432/docpilot"
```

```bash
# secret.yaml이 실수로 커밋되지 않도록 무시 목록에 추가
echo "k8s/secret.yaml" >> .gitignore

kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
```

**확인**: Secret이 base64로 저장됐음을 직접 본다(암호화가 아님을 체감).

```bash
kubectl get configmap docpilot-config -o yaml     # data가 평문으로 보임
kubectl get secret docpilot-db-secret -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d; echo
# → docpilot  (base64는 누구나 복원 가능)
```

#### 3단계. Deployment를 외부화된 설정으로 리팩터링

week04의 `k8s/deployment.yaml`을 아래로 교체한다. 하드코딩 env가 `envFrom`(ConfigMap)과 `secretKeyRef`(Secret)로 바뀐 것이 핵심이다. probe·resources·롤아웃 전략도 함께 넣는다(2부에서 상세 설명).

```yaml
# k8s/deployment.yaml (week05 개정판)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docpilot
  labels:
    app: docpilot
spec:
  replicas: 2
  selector:
    matchLabels:
      app: docpilot
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1          # 교체 중 최대 1개 초과 생성
      maxUnavailable: 0    # 교체 중 사용 불가 Pod 0개 → 무중단
  template:
    metadata:
      labels:
        app: docpilot
    spec:
      containers:
        - name: docpilot
          image: docpilot:0.3.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: docpilot-config      # APP_ENV, LOG_LEVEL 주입
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: docpilot-db-secret # 민감정보는 Secret에서
                  key: DATABASE_URL
          resources:
            requests:
              cpu: "100m"                  # HPA 사용률 계산의 기준
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 3
            periodSeconds: 5
```

#### 4단계. PostgreSQL도 Secret에서 자격증명 주입

`k8s/postgres.yaml`의 `env` 블록을 하드코딩에서 Secret 참조로 바꾼다(컨테이너의 나머지는 week04와 동일).

```yaml
          env:
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: docpilot-db-secret
                  key: POSTGRES_USER
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: docpilot-db-secret
                  key: POSTGRES_PASSWORD
            - name: POSTGRES_DB
              valueFrom:
                secretKeyRef:
                  name: docpilot-db-secret
                  key: POSTGRES_DB
```

```bash
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/deployment.yaml
```

**확인**: 새 설정으로 Pod가 롤링 교체된다. 컨테이너 안의 환경변수가 실제로 주입됐는지 확인한다.

```bash
kubectl rollout status deployment/docpilot          # successfully rolled out
POD=$(kubectl get pod -l app=docpilot -o jsonpath='{.items[0].metadata.name}')
kubectl exec "$POD" -- printenv APP_ENV DATABASE_URL
# APP_ENV=k8s-prod
# DATABASE_URL=postgresql+psycopg://docpilot:docpilot@docpilot-db:5432/docpilot
```

**확인**: `APP_ENV`가 `k8s-prod`(ConfigMap 값), `DATABASE_URL`이 Secret 값으로 주입됐으면 설정 외부화 성공이다. 하드코딩을 지웠는데도 앱은 정상 동작한다.

```bash
kubectl port-forward service/docpilot 8080:80 >/dev/null 2>&1 &
sleep 2
curl -s http://localhost:8080/health      # {"status":"ok"}
kill %1
```

### 2부. 헬스체크와 리소스 (이미 적용됨) 확인·검증

probe와 resources는 3단계에서 이미 Deployment에 넣었다. 이제 그것이 작동하는지 검증한다.

#### 5단계. probe·resources가 붙었는지 확인

```bash
kubectl describe deployment docpilot | grep -A3 -E "Liveness|Readiness|Limits|Requests"
```

**확인**: `Liveness: http-get .../health`, `Readiness: http-get .../health`, `Requests`/`Limits` 값이 보이면 통과.

#### 6단계. readiness가 트래픽을 막는지 체감

week04의 간헐 실패가 사라졌는지 본다. 반복 요청 중 Pod를 지워도 이번엔 실패가 없어야 한다.

```bash
kubectl port-forward service/docpilot 8080:80 >/dev/null 2>&1 &
sleep 2
# 백그라운드로 초당 요청, 별도로 Pod 하나 삭제
( for i in $(seq 1 40); do curl -s -o /dev/null -w "%{http_code} " http://localhost:8080/health; sleep 0.25; done; echo ) &
POD=$(kubectl get pod -l app=docpilot -o jsonpath='{.items[0].metadata.name}')
kubectl delete pod "$POD"
wait
kill %1 2>/dev/null
```

**확인**: 출력이 대부분(이상적으론 전부) `200`. 새 Pod가 readiness 통과 전까지 Service 대상에서 빠지므로, 준비 안 된 Pod로 트래픽이 안 간다.

### 3부. 오토스케일링 (HPA)

#### 7단계. metrics-server 설치 (kind용 패치 포함)

```bash
# 지표 수집기 설치
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# kind 노드는 kubelet 인증서가 self-signed라 --kubelet-insecure-tls 가 필요하다
kubectl patch deployment metrics-server -n kube-system --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

kubectl rollout status deployment/metrics-server -n kube-system
```

**확인**: 잠시(30~60초) 뒤 지표가 나오면 성공.

```bash
kubectl top pods -l app=docpilot     # CPU/메모리 사용량이 숫자로 표시되어야 함
```

`error: Metrics API not available`이 나오면 아직 준비 중이니 조금 기다렸다 재시도한다.

#### 8단계. HPA 작성·적용

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: docpilot
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: docpilot
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 50   # 평균 CPU가 requests의 50% 넘으면 스케일 아웃
```

```bash
kubectl apply -f k8s/hpa.yaml
kubectl get hpa docpilot   # TARGETS가 cpu: x%/50% 형태여야 함 (<unknown>이면 metrics-server 대기 또는 requests 누락)
```

**확인**: `TARGETS`가 `<unknown>`이 아니라 `2%/50%` 같은 실제 값이면 정상.

#### 9단계. 부하를 걸어 스케일 아웃 관찰

```bash
# 감시 창 (별도 터미널)
kubectl get hpa,pods -l app=docpilot -w
```

다른 터미널에서 부하 생성 Pod를 띄운다.

```bash
kubectl run load-generator --image=busybox:1.36 --restart=Never -- \
  /bin/sh -c "while true; do wget -q -O- http://docpilot/health; done"
```

**확인**: 1~3분 안에 HPA의 `REPLICAS`가 2 → 3,4…로 증가하고 Pod가 늘어난다. 관찰 후 부하를 멈춘다.

```bash
kubectl delete pod load-generator
```

몇 분 뒤 부하가 사라지면 `minReplicas`(2)로 서서히 축소된다(scale-down은 안정화를 위해 기본 5분 지연).

### 4부. Ingress로 도메인 노출

#### 10단계. ingress-nginx 컨트롤러 설치 (kind provider)

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

# 컨트롤러가 준비될 때까지 대기
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

**확인**: `pod/ingress-nginx-controller-... condition met` 출력.

#### 11단계. Ingress 작성·적용

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: docpilot
spec:
  ingressClassName: nginx
  rules:
    - host: docpilot.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: docpilot
                port:
                  number: 80
```

```bash
kubectl apply -f k8s/ingress.yaml
kubectl get ingress docpilot   # HOSTS=docpilot.local, ADDRESS가 채워질 때까지 잠시 대기
```

#### 12단계. 도메인으로 접속

week04에서 kind 노드의 80 포트를 호스트 80으로 매핑해 뒀으므로, `docpilot.local`을 로컬로 가리키게만 하면 된다.

```bash
# hosts 파일에 도메인 등록 (한 번만)
echo "127.0.0.1 docpilot.local" | sudo tee -a /etc/hosts

curl -s http://docpilot.local/health   # {"status":"ok"}
curl -s http://docpilot.local/         # {"message":"Hello, DocPilot"}  (아직 0.3.0)
```

hosts 수정이 어려우면 Host 헤더로 대체할 수 있다.

```bash
curl -s -H "Host: docpilot.local" http://localhost/health
```

**확인**: 이제 **port-forward 없이** 도메인으로 docpilot에 접속된다. Ingress → Service → Pod 경로가 완성됐다.

### 5부. 무중단 롤아웃 / 롤백

#### 13단계. 새 버전 이미지 만들기

롤아웃을 눈으로 보려면 응답이 바뀌는 새 버전이 필요하다. `main.py`의 root 응답에 버전을 추가한다.

```python
# main.py — week03의 root()를 아래처럼 수정 (응답에 version 추가)
@app.get("/")
def root() -> dict:
    return {"message": "Hello, DocPilot", "version": "0.5.0"}
```

```bash
docker build -t docpilot:0.5.0 .                       # 새 태그로 빌드
kind load docker-image docpilot:0.5.0 --name docpilot  # 클러스터에 로드 (안 하면 ImagePullBackOff)
```

**확인**: `docker images docpilot`에 `0.3.0`, `0.5.0` 두 태그가 보인다.

#### 14단계. 롤아웃 수행

```bash
# 감시 창 (별도 터미널)
kubectl get pods -l app=docpilot -w
```

```bash
# 컨테이너 이미지를 0.5.0으로 교체 → RollingUpdate 시작
kubectl set image deployment/docpilot docpilot=docpilot:0.5.0
kubectl rollout status deployment/docpilot     # Waiting... → successfully rolled out
```

**확인**: 감시 창에서 새 Pod가 하나 뜨고(readiness 통과 후) 옛 Pod가 하나 지워지는 식으로 **점진 교체**된다(maxUnavailable:0 덕에 항상 최소 2개 준비 상태 유지). 새 버전 응답을 확인한다.

```bash
curl -s http://docpilot.local/     # {"...","version":"0.5.0"}
```

리비전 히스토리도 본다.

```bash
kubectl rollout history deployment/docpilot   # REVISION 1, 2 ...
```

#### 15단계. 롤백

문제가 생겼다고 가정하고 이전 버전으로 되돌린다.

```bash
kubectl rollout undo deployment/docpilot       # 직전 리비전(0.3.0)으로 롤백
kubectl rollout status deployment/docpilot
curl -s http://docpilot.local/                 # version 필드가 사라짐 (0.3.0 응답)
```

**확인**: 응답이 0.3.0으로 돌아왔다. 특정 리비전으로 되돌리려면 `kubectl rollout undo deployment/docpilot --to-revision=<N>`.

> 참고: 코드 변경 없이 Pod만 새로 굴리고 싶을 땐(예: Secret 갱신 반영) `kubectl rollout restart deployment/docpilot`.

### 6부. CI/CD 맛보기 (GitHub Actions)

#### 16단계. 이미지 빌드·푸시 워크플로우 작성

push할 때마다 이미지를 빌드해 GitHub Container Registry(GHCR)에 푸시하는 워크플로우다. 별도 시크릿 설정 없이 `GITHUB_TOKEN`으로 GHCR에 푸시할 수 있다.

```yaml
# .github/workflows/docker-build.yml
name: docpilot-image

on:
  push:
    branches: ["main"]
    paths:
      - "app/**"
      - "Dockerfile"
      - "requirements.txt"
      - ".github/workflows/docker-build.yml"

permissions:
  contents: read
  packages: write        # GHCR에 푸시하려면 필요

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata (tags)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}/docpilot
          tags: |
            type=sha            # 커밋 SHA 태그
            type=raw,value=latest

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

```bash
git add .github/workflows/docker-build.yml
git commit -m "ci: build and push docpilot image to GHCR"
git push origin main
```

**확인**: GitHub 저장소의 **Actions** 탭에서 워크플로우가 초록불로 끝나고, **Packages**에 `docpilot` 이미지가 생기면 성공. (푸시된 이미지를 kind에서 쓰려면 GHCR 패키지를 public으로 바꾸거나 imagePullSecret이 필요하다.)

> **CD는 여기서 개념만.** 실제로 이 이미지를 클러스터에 자동 반영하려면 (a) 러너가 클러스터 kubeconfig를 시크릿으로 갖고 `kubectl set image`를 실행하거나, (b) Argo CD/Flux 같은 GitOps 도구가 매니페스트 변경을 감지해 배포한다. 이는 12주차 통합 배포에서 다시 다룬다.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| HPA `TARGETS`가 `<unknown>` | metrics-server 미준비, 또는 Deployment에 `resources.requests` 없음 | metrics-server 설치·`--kubelet-insecure-tls` 패치 확인, `kubectl top pods` 동작 확인, requests 존재 확인 |
| `kubectl top` 이 `Metrics API not available` | metrics-server가 아직 기동 중이거나 TLS 패치 누락 | 30~60초 대기 후 재시도, 7단계 patch 재적용, `kubectl -n kube-system logs deploy/metrics-server` |
| Ingress 접속 시 `404` | host 불일치, Ingress 규칙/서비스명 오타 | `curl -H "Host: docpilot.local"`로 host 명시, `kubectl get ingress`·`describe ingress`로 backend 확인 |
| Ingress 접속 시 `503` | 백엔드 Pod가 readiness 미통과(엔드포인트 없음) | `kubectl get endpoints docpilot`에 Pod IP가 있는지, Pod가 Ready인지 확인 |
| Ingress `ADDRESS`가 안 채워짐 / 연결 거부 | ingress-nginx 컨트롤러 미준비, 또는 80 포트 매핑 없이 만든 클러스터 | 컨트롤러 `kubectl wait`, week04 `kind-cluster.yaml`의 extraPortMappings 확인(없으면 클러스터 재생성) |
| 롤아웃이 `ImagePullBackOff` | 새 태그 이미지를 `kind load` 안 함 | `kind load docker-image docpilot:0.5.0 --name docpilot` |
| Secret 바꿔도 앱에 반영 안 됨 | env로 주입된 Secret은 Pod 재생성 시에만 반영 | `kubectl rollout restart deployment/docpilot` |
| Pod가 probe 때문에 계속 재시작 | `/health` 경로/포트 오타, initialDelay 너무 짧음 | probe의 path=`/health`, port=8000 확인, `initialDelaySeconds` 늘리기, `kubectl describe pod`의 Events 확인 |
| 롤아웃이 멈춤(progress deadline) | 새 Pod가 readiness 통과 실패 | `kubectl describe pod`·`kubectl logs`로 원인 확인 후 `kubectl rollout undo` |

---

## 이번 주 과제 — 블록 1 미니 과제

**주제: "설정 외부화 + 무중단 배포" 를 갖춘 운영형 docpilot.** week01~week05의 결승선이다.

**제출물** (`week05/` 폴더, 스크린샷·로그·YAML 포함):

1. **설정 외부화 증빙**
   - `k8s/configmap.yaml`, `k8s/secret.yaml`(값은 더미로 마스킹), 리팩터링된 `k8s/deployment.yaml`.
   - `kubectl exec <pod> -- printenv APP_ENV DATABASE_URL` 출력 — 값이 ConfigMap/Secret에서 왔음을 확인.
   - Deployment YAML에 하드코딩 자격증명이 **없음**을 보인다.
2. **헬스체크·리소스**
   - `kubectl describe deployment docpilot`에서 liveness/readiness/requests/limits가 보이는 부분.
3. **오토스케일링**
   - 부하를 걸었을 때 `kubectl get hpa,pods -w` 화면(REPLICAS 증가 순간)과, 부하 제거 후 축소.
4. **Ingress**
   - `curl http://docpilot.local/health` 결과와 `kubectl get ingress` 출력.
5. **무중단 배포 증빙** (핵심)
   - 0.3.0 → 0.5.0 롤아웃 중 `/health`를 반복 호출한 로그에서 **다운타임(비200 응답)이 없음**을 보인다. 예:
     ```bash
     ( while true; do curl -s -o /dev/null -w "%{http_code}\n" http://docpilot.local/health; sleep 0.2; done ) &
     kubectl set image deployment/docpilot docpilot=docpilot:0.5.0
     kubectl rollout status deployment/docpilot
     # 위 반복 로그가 전부 200 이면 무중단 달성
     ```
   - `kubectl rollout history`와 `kubectl rollout undo`로 롤백까지 수행한 로그.
6. **CI/CD 맛보기**
   - `.github/workflows/docker-build.yml`과 Actions 실행 성공 스크린샷.
7. 회고(5줄 내외): "무중단 배포를 가능하게 한 요소(readiness probe, maxUnavailable:0)는 각각 무슨 역할을 했나?"

---

## 체크리스트

- [ ] ConfigMap/Secret으로 설정과 DB 자격증명을 외부화하고, Deployment에서 하드코딩을 제거했다.
- [ ] `secret.yaml`을 `.gitignore`에 넣었다.
- [ ] liveness/readiness probe를 `/health`에 연결했다.
- [ ] resources requests/limits를 설정했다.
- [ ] metrics-server를 설치하고 `kubectl top pods`가 동작한다.
- [ ] HPA가 부하에 따라 Pod를 늘리고 줄이는 것을 관찰했다.
- [ ] ingress-nginx를 설치하고 `docpilot.local` 도메인으로 접속했다.
- [ ] `kubectl set image`로 롤아웃, `kubectl rollout undo`로 롤백을 수행했다.
- [ ] 롤아웃 중 무중단(전부 200)을 확인했다.
- [ ] GitHub Actions로 이미지 빌드·푸시 워크플로우를 만들고 실행에 성공했다.

---

## 다음 주 예고

블록 1(클라우드 네이티브 기반)이 끝났다. 지금까지 docpilot은 **잘 배포·운영되지만 아직 "말"은 못 한다.** 블록 2에서 이 서비스에 **AI 두뇌**를 붙인다.

[week06 — LLM API 연동](./week06-llm-api-연동.md)에서는:

- OpenAI / Google Gemini API 인증과 요청/응답, 토큰·비용 개념
- 프롬프트 엔지니어링 기초(system/user/assistant 롤, temperature 등)
- docpilot에 `/chat` 엔드포인트 추가 + **스트리밍** 응답
- 컨테이너화된 LLM 챗 서비스

이번 주에 만든 K8s 배포 위에, 다음 주부터는 기능이 얹힌다. API 키는 오늘 배운 **Secret**으로 주입할 것이다 — 설정 외부화 습관이 그대로 이어진다.
