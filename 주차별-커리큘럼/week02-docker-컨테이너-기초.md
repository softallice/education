# Week 2 — Docker 컨테이너 기초

> 이번 주 한 줄: "내 컴퓨터에선 되는데"를 끝낸다. `docpilot`을 컨테이너 이미지로 만들어 어디서든 똑같이 실행한다.
> docpilot 진화: **로컬 웹앱 → 컨테이너 이미지** (Dockerfile 작성 → 빌드 → 실행 → 레지스트리 푸시)

이 문서는 [주차별 커리큘럼 목차](./README.md)의 2주차다. [Week 1](./week01-오리엔테이션과-클라우드네이티브개론.md)에서 만든 `docpilot`을 그대로 이어서 쓴다.

---

## 학습 목표

- [ ] 컨테이너와 VM의 차이를 아키텍처 수준에서 설명할 수 있다.
- [ ] 이미지·레이어·레지스트리의 관계를 그림/표로 구분해 설명할 수 있다.
- [ ] `docpilot`용 Dockerfile을 작성하고 이미지를 빌드한다.
- [ ] `docker run -p`로 컨테이너를 실행하고 포트를 매핑한다.
- [ ] `docker logs` / `docker exec`로 컨테이너 내부를 관찰한다.
- [ ] 이미지를 태깅해 Docker Hub 또는 GHCR에 푸시한다.

## 사전 준비

- 지난주 산출물: `docpilot` 로컬 앱 (`main.py`, `requirements.txt`, `.gitignore`) + GitHub 저장소
- 필요한 도구·계정
  - Docker Engine 또는 Docker Desktop (`docker --version`)
  - Docker Hub 계정 **또는** GitHub 계정(GHCR 사용 시)
- 확인 명령:

```bash
docker --version           # Docker version 27.x 등
docker run hello-world     # "Hello from Docker!" 메시지가 나오면 정상
cd ~/projects/docpilot     # 지난주 프로젝트로 이동
ls                         # main.py, requirements.txt 가 보여야 함
```

> `docker run hello-world`가 권한 오류(`permission denied`)를 내면 트러블슈팅 표를 참고한다.

---

## 개념 (요약)

### 1. 컨테이너 vs VM

| 구분 | 가상 머신(VM) | 컨테이너 |
|---|---|---|
| 격리 단위 | 하드웨어를 가상화, **게스트 OS 통째로** | OS 커널 공유, **프로세스 수준 격리** |
| 부팅 | 수십 초~분 | 수백 ms~수 초 |
| 크기 | GB 단위 | MB 단위 |
| 오버헤드 | 하이퍼바이저 + 게스트 OS | 거의 없음 |
| 무엇을 담나 | OS + 앱 | 앱 + 실행에 필요한 것만 |

핵심 그림:

```text
[ VM ]                         [ Container ]
App A   App B                  App A   App B
Guest OS  Guest OS             (커널 공유, OS 없음)
------ Hypervisor ------       ------ Docker Engine ------
--------- Host OS ---------    --------- Host OS ---------
--------- Hardware --------    --------- Hardware --------
```

컨테이너는 게스트 OS가 없으니 가볍고 빠르다. **"동일한 실행 환경을 통째로 패키징"** 한다는 게 핵심 — 이게 12-Factor의 "Dev/prod parity"를 실현한다.

### 2. 이미지 · 레이어 · 레지스트리

- **이미지(Image)**: 실행에 필요한 파일시스템 스냅샷 + 메타데이터. "컨테이너를 찍어내는 틀".
- **컨테이너(Container)**: 이미지를 실행한 **인스턴스**. 하나의 이미지로 여러 컨테이너를 띄울 수 있다.
- **레이어(Layer)**: 이미지는 Dockerfile 명령마다 쌓이는 **읽기 전용 레이어의 스택**이다. 레이어는 캐시되고 이미지 간 공유된다 → 빌드가 빠르고 저장이 효율적이다.
- **레지스트리(Registry)**: 이미지를 저장·배포하는 원격 저장소. Docker Hub(공개 기본), GHCR(GitHub Container Registry), ECR/GCR 등.

레이어 캐시 규칙(중요): Dockerfile은 **자주 안 바뀌는 것 → 자주 바뀌는 것** 순으로 써야 캐시가 잘 먹는다. 그래서 의존성 설치(`requirements.txt`)를 소스 복사보다 **먼저** 한다.

---

## 실습: 단계별 따라하기

### 1부. Dockerfile 작성과 빌드

#### 1단계. .dockerignore 작성

빌드 컨텍스트에서 불필요/민감 파일을 제외한다(이미지 크기·보안·빌드 속도에 직결).

프로젝트 루트에 `.dockerignore` 생성:

```text
.venv/
__pycache__/
*.pyc
.pytest_cache/
.git/
.gitignore
.env
.env.*
Dockerfile
.dockerignore
README.md
```

**확인**: `.venv`, `.git`이 목록에 있다. 이게 없으면 무거운 가상환경이 통째로 이미지에 들어간다.

#### 2단계. Dockerfile 작성 (완결된 코드)

프로젝트 루트에 `Dockerfile`을 만든다. 아래는 복붙해서 바로 빌드되는 완결본이다.

```dockerfile
# Dockerfile — docpilot week02
# 슬림 베이스 이미지: 데비안 slim + Python 3.12 (풀 이미지보다 수백 MB 작다)
FROM python:3.12-slim

# 1) 파이썬 런타임 권장 환경변수
#    - PYTHONDONTWRITEBYTECODE: .pyc 안 만듦 (이미지 깔끔)
#    - PYTHONUNBUFFERED: 로그를 버퍼링 없이 즉시 출력 (docker logs로 바로 보임)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 2) 작업 디렉터리
WORKDIR /app

# 3) 의존성 먼저 복사·설치 (레이어 캐시 최적화 핵심)
#    requirements.txt가 안 바뀌면 이 레이어는 캐시돼서 재설치 안 함
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) 앱 소스 복사 (자주 바뀌는 것은 뒤로)
COPY main.py .

# 5) 문서화용 포트 노출 선언 (실제 매핑은 docker run -p에서)
EXPOSE 8000

# 6) 컨테이너 시작 명령
#    컨테이너 밖에서 접속하려면 반드시 host=0.0.0.0 (127.0.0.1이면 컨테이너 내부만)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

> **왜 `0.0.0.0`인가?** 1주차 로컬 실행에선 `127.0.0.1`을 썼다. 하지만 컨테이너 안에서 `127.0.0.1`에 바인딩하면 컨테이너 **내부에서만** 접근 가능하다. 컨테이너 밖(호스트)에서 접속하려면 모든 인터페이스(`0.0.0.0`)에 바인딩해야 한다.

#### 3단계. 이미지 빌드

```bash
docker build -t docpilot:0.2.0 .
```

- `-t docpilot:0.2.0` = 이미지 이름:태그
- `.` = 빌드 컨텍스트(현재 디렉터리)

**확인**: 마지막에 아래 비슷한 출력이 나온다.

```text
 => naming to docker.io/library/docpilot:0.2.0
```

이미지 목록으로도 확인:

```bash
docker images | grep docpilot
# docpilot   0.2.0   <id>   ...   ~150MB 근처
```

### 2부. 컨테이너 실행과 관찰

#### 4단계. docker run -p로 실행

```bash
docker run --name docpilot-dev -p 8000:8000 docpilot:0.2.0
```

- `--name docpilot-dev` = 컨테이너 이름 지정
- `-p 8000:8000` = 호스트 8000 → 컨테이너 8000 매핑 (`호스트:컨테이너`)

**확인**: 터미널에 `Uvicorn running on http://0.0.0.0:8000` 로그가 뜨고 대기한다. **새 터미널**에서:

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/health
```

```json
{"message":"Hello, DocPilot"}
{"status":"ok"}
```

> 1주차와 결과가 똑같다. 다른 점은 이제 **컨테이너 안에서** 돌고 있다는 것. 이게 "한 번 빌드, 어디서든 실행"이다.

#### 5단계. 백그라운드 실행 + 로그 확인

포그라운드 컨테이너를 `Ctrl+C`로 멈추고, 이번엔 백그라운드(`-d`)로 띄운다.

```bash
docker rm -f docpilot-dev                              # 기존 컨테이너 제거
docker run -d --name docpilot-dev -p 8000:8000 docpilot:0.2.0
docker ps                                              # 실행 중 컨테이너 확인
docker logs docpilot-dev                               # 컨테이너 로그 출력
docker logs -f docpilot-dev                            # 실시간 로그 (Ctrl+C로 빠져나옴)
```

**확인**: `docker ps`의 STATUS가 `Up ...`, PORTS가 `0.0.0.0:8000->8000/tcp`. `docker logs`에 startup 로그가 보인다.

#### 6단계. docker exec로 컨테이너 내부 들어가기

돌고 있는 컨테이너 안에서 셸을 연다.

```bash
docker exec -it docpilot-dev /bin/bash
```

컨테이너 내부 프롬프트에서:

```bash
ls -la                     # /app 안에 main.py, requirements.txt 확인
python --version           # Python 3.12.x
curl http://localhost:8000/health   # 컨테이너 내부에서 헬스 확인 (curl 없으면 아래 참고)
exit                       # 컨테이너에서 빠져나오기
```

> slim 이미지엔 `curl`이 없을 수 있다. 그럴 땐 `python -c "import urllib.request as u; print(u.urlopen('http://localhost:8000/health').read())"`로 확인한다.

**확인**: 내부 `/app`에 우리 파일들이 있고, 헬스 체크가 응답한다.

### 3부. 태깅과 레지스트리 푸시

레지스트리는 둘 중 **하나**만 골라 따라 하면 된다.

#### 7단계-A. Docker Hub에 푸시

```bash
docker login                                           # Docker Hub 사용자/비번(또는 토큰)
docker tag docpilot:0.2.0 <dockerhub-username>/docpilot:0.2.0
docker push <dockerhub-username>/docpilot:0.2.0
```

**확인**: `docker push` 출력 마지막에 `0.2.0: digest: sha256:... size: ...`. Docker Hub 웹의 본인 저장소에 이미지가 보인다.

#### 7단계-B. GHCR(GitHub Container Registry)에 푸시

GHCR은 `write:packages` 권한이 있는 Personal Access Token(classic)이 필요하다.

```bash
echo $GHCR_TOKEN | docker login ghcr.io -u <github-username> --password-stdin
docker tag docpilot:0.2.0 ghcr.io/<github-username>/docpilot:0.2.0
docker push ghcr.io/<github-username>/docpilot:0.2.0
```

**확인**: GitHub 프로필 → Packages 탭에 `docpilot` 패키지가 생긴다. (기본은 private이며, 원하면 public으로 전환)

#### 8단계. 푸시 검증 (다른 곳에서 pull 되는지)

로컬 이미지를 지우고 레지스트리에서 다시 받아 본다. 진짜 "어디서든 실행"이 됐는지 검증하는 단계다.

```bash
docker rm -f docpilot-dev
docker rmi <레지스트리경로>/docpilot:0.2.0             # 로컬 캐시 제거
docker run -d --name docpilot-verify -p 8000:8000 <레지스트리경로>/docpilot:0.2.0
curl http://127.0.0.1:8000/                            # 레지스트리에서 받은 이미지가 응답
```

**확인**: pull 후 실행한 컨테이너가 `{"message":"Hello, DocPilot"}`를 반환한다.

정리:

```bash
docker rm -f docpilot-verify
```

Dockerfile과 `.dockerignore`도 잊지 말고 커밋한다.

```bash
git add Dockerfile .dockerignore
git commit -m "feat: docpilot week02 컨테이너화 (Dockerfile, .dockerignore)"
git push
```

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `permission denied ... docker.sock` | 사용자가 docker 그룹에 없음 | `sudo usermod -aG docker $USER` 후 재로그인, 또는 `sudo docker ...` |
| 컨테이너는 뜨는데 `curl` 접속 안 됨 | `CMD`에서 host가 `127.0.0.1` | Dockerfile CMD를 `--host 0.0.0.0`으로 (본 문서대로) |
| `port is already allocated` | 8000 포트 다른 컨테이너가 점유 | `docker ps`로 찾아 `docker rm -f`, 또는 `-p 8001:8000` |
| 이미지가 너무 큼(수백 MB+) | `.venv`/`.git`이 이미지에 포함 | `.dockerignore` 확인, slim 베이스 사용 |
| 코드 고쳤는데 반영 안 됨 | 이미지 재빌드 안 함 | 컨테이너는 **빌드 시점** 스냅샷. `docker build` 다시 실행 |
| `pip install` 매번 오래 걸림 | 레이어 캐시 안 먹음 | `COPY requirements.txt`를 `COPY main.py`보다 먼저(본 문서대로) |
| `denied: requested access ... ` (push) | 로그인/네이밍 불일치 | `docker login` 재확인, 태그가 `<user>/docpilot`인지 확인 |
| GHCR `403` | 토큰에 `write:packages` 없음 | PAT 재발급 시 `write:packages` 체크 |

---

## 이번 주 과제

**제출물**: 레지스트리에 푸시된 `docpilot` 이미지 경로 + 아래 멀티스테이지 결과.

1. **필수** — 위 실습을 완주하고 이미지를 Docker Hub 또는 GHCR에 푸시한다. Dockerfile/.dockerignore를 커밋·푸시한다.
2. **멀티스테이지 빌드로 이미지 줄이기** — 아래 `Dockerfile.slim`을 작성해 빌드하고, `docker images`로 기존 이미지와 크기를 비교한다.

   ```dockerfile
   # Dockerfile.slim — 멀티스테이지: builder에서 의존성 설치, 최종엔 결과만 복사
   FROM python:3.12-slim AS builder
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

   FROM python:3.12-slim
   ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
   WORKDIR /app
   COPY --from=builder /install /usr/local
   COPY main.py .
   EXPOSE 8000
   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

   ```bash
   docker build -f Dockerfile.slim -t docpilot:0.2.0-slim .
   docker images | grep docpilot        # 크기 비교
   docker run -d --name docpilot-slim -p 8000:8000 docpilot:0.2.0-slim
   curl http://127.0.0.1:8000/health    # 여전히 동작하는지 확인
   ```

   제출물에 **두 이미지의 크기(MB)와 차이**를 기록한다.
3. **README 갱신** — 컨테이너 vs VM 차이를 3줄로, 레이어 캐시가 왜 `requirements.txt`를 먼저 복사하게 만드는지 2줄로 정리한다.

> 제출: LMS에 이미지 경로(pull 명령 포함), 크기 비교 표, 마지막 커밋 해시를 제출한다.

---

## 체크리스트

- [ ] `.dockerignore`로 `.venv`/`.git`을 제외했다.
- [ ] Dockerfile을 작성하고 `docker build`로 이미지를 만들었다.
- [ ] `docker run -p 8000:8000`으로 실행해 curl/브라우저로 확인했다.
- [ ] `docker logs`와 `docker exec`로 컨테이너 내부를 관찰했다.
- [ ] 이미지를 태깅해 Docker Hub 또는 GHCR에 푸시했다.
- [ ] 로컬 이미지를 지우고 pull 해서 재실행이 되는지 검증했다.
- [ ] (과제) 멀티스테이지 빌드로 이미지 크기를 줄이고 비교했다.
- [ ] Dockerfile/.dockerignore를 커밋·푸시했다.

---

## 다음 주 예고

[Week 3 — Docker Compose 멀티 컨테이너](./week03-docker-compose-멀티컨테이너.md)

지금 `docpilot`은 단일 컨테이너다. 하지만 진짜 서비스는 앱만으로 안 된다 — **데이터베이스**가 필요하다. 다음 주에는 Docker Compose로 `docpilot`(web)과 **PostgreSQL 16**을 함께 띄우고, 컨테이너 간 네트워크·볼륨·환경변수를 배운다. `docpilot`에 `/documents` 엔드포인트를 추가해 업로드 문서 메타데이터를 DB에 저장·조회하고, 볼륨으로 데이터가 영속되는 걸 직접 확인한다.
