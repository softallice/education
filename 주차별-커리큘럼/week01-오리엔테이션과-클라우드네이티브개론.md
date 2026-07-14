# Week 1 — 오리엔테이션과 클라우드 네이티브 개론

> 이번 주 한 줄: 클라우드 네이티브가 무엇인지 감을 잡고, 러닝 프로젝트 `docpilot`의 첫 코드를 로컬에서 띄워 GitHub에 올린다.
> docpilot 진화: **아무것도 없음 → FastAPI 로컬 웹앱** (`GET /` → "Hello, DocPilot", `GET /health` → `{"status":"ok"}`)

이 문서는 [주차별 커리큘럼 목차](./README.md)의 첫 주차다. 실습 환경이 아직 안 잡혀 있다면 먼저 [실습 환경과 기술 스택](../02-실습환경과-기술스택.md)을 끝내고 오자.

---

## 학습 목표

- [ ] IaaS / PaaS / SaaS의 책임 경계를 한 문장으로 설명할 수 있다.
- [ ] 온프레미스와 클라우드의 비용·운영 구조 차이를 말할 수 있다.
- [ ] "클라우드 네이티브"와 12-Factor App의 핵심을 이해한다.
- [ ] 마이크로서비스가 왜 등장했는지 개괄한다.
- [ ] Python 가상환경을 만들고 FastAPI 앱을 `uvicorn`으로 실행한다.
- [ ] `git init` → 첫 커밋 → GitHub 푸시까지 완주한다.

## 사전 준비

- 지난주 산출물: 없음 (이번 주가 시작점)
- 필요한 도구·계정
  - Python 3.12 (`python3 --version`으로 확인)
  - Git (`git --version`으로 확인)
  - GitHub 계정 + `gh` CLI 또는 SSH 키 (푸시용)
  - 터미널(bash/zsh), 코드 에디터(VS Code 권장)
- 확인 명령:

```bash
python3 --version   # Python 3.12.x 가 보여야 함
git --version       # git version 2.x
```

> 위 두 명령 중 하나라도 실패하면 [실습 환경과 기술 스택](../02-실습환경과-기술스택.md)으로 돌아가 설치를 마치고 온다.

---

## 개념 (요약)

### 1. 클라우드 컴퓨팅: IaaS / PaaS / SaaS

클라우드는 "내가 어디까지 관리하고, 어디부터 제공자가 관리하는가"의 경계로 나뉜다.

| 모델 | 제공자가 관리 | 내가 관리 | 예시 |
|---|---|---|---|
| **IaaS** (Infrastructure) | 서버·네트워크·스토리지·가상화 | OS·런타임·앱·데이터 | AWS EC2, GCP Compute Engine |
| **PaaS** (Platform) | 위 + OS·런타임 | 앱 코드·데이터 | Heroku, Cloud Run, App Engine |
| **SaaS** (Software) | 전부 | 설정·데이터 입력만 | Gmail, Notion, Slack |

핵심: **위로 갈수록 내가 신경 쓸 게 줄어들지만, 통제권도 줄어든다.** 이 강의의 `docpilot`은 IaaS/PaaS 위에 올려 운영하는 앱을 직접 만드는 과정이다.

### 2. 온프렘 vs 클라우드

| 구분 | 온프레미스(On-Prem) | 클라우드 |
|---|---|---|
| 초기 비용 | 서버 구매(CapEx, 큰 선투자) | 없음(OpEx, 쓴 만큼 과금) |
| 확장 | 장비 추가 = 수주~수개월 | 수 분 내 스케일 |
| 운영 책임 | 전기·냉방·하드웨어까지 전부 | 물리 계층은 제공자 |
| 적합 | 규제·초저지연·고정 부하 | 가변 부하·빠른 실험 |

### 3. 클라우드 네이티브란

> **클라우드 네이티브** = 클라우드의 탄력성·자동화를 "전제로" 설계·운영하는 방식.

단순히 "클라우드에 올린 앱"이 아니라, **컨테이너**로 패키징하고, **선언적으로** 배포하며, **자동 확장·자가 치유**되도록 만든 앱이다. CNCF는 컨테이너·마이크로서비스·불변 인프라·선언적 API를 대표 특성으로 꼽는다. 이 강의의 블록 1(1~5주)이 바로 이걸 다룬다.

### 4. 12-Factor App (요약)

클라우드에서 잘 도는 앱을 위한 12가지 원칙. 이번 주부터 자연스럽게 지켜 나간다.

1. **Codebase** — 하나의 코드베이스, 버전 관리(=오늘 Git 시작)
2. **Dependencies** — 의존성 명시·격리(=`requirements.txt` + venv)
3. **Config** — 설정은 환경변수로(3주차 DB 연결에서 실전 적용)
4. **Backing services** — DB 등 백엔드는 교체 가능한 리소스로
5. **Build, release, run** — 빌드/릴리스/실행 분리(2주차 Docker에서 체감)
6. **Processes** — 무상태(stateless) 프로세스
7. **Port binding** — 포트로 서비스 노출(=오늘 uvicorn `:8000`)
8. **Concurrency** — 프로세스 모델로 수평 확장
9. **Disposability** — 빠른 기동·정상 종료
10. **Dev/prod parity** — 개발·운영 환경 최대한 동일(=Docker의 목적)
11. **Logs** — 로그는 이벤트 스트림으로(표준출력)
12. **Admin processes** — 관리 작업은 일회성 프로세스로

### 5. 마이크로서비스 개괄

- **모놀리스**: 하나의 배포 단위. 시작은 단순하지만 커지면 배포·확장이 통째로 묶인다.
- **마이크로서비스**: 기능별로 독립 배포·확장되는 작은 서비스들의 모음.
- 트레이드오프: 유연함을 얻는 대신 네트워크·운영 복잡도가 커진다.

`docpilot`은 처음엔 단일 서비스(모놀리스)로 시작해, 필요할 때 DB·벡터DB·에이전트 등 백엔드 서비스를 붙여 나간다. **작게 시작해서 필요할 때 쪼갠다**가 실무 감각이다.

---

## 실습: 단계별 따라하기

이번 주 목표 산출물은 **로컬에서 도는 FastAPI 앱 + GitHub 저장소**다. 아래를 순서대로 그대로 따라 친다.

### 1부. 프로젝트 스캐폴드와 가상환경

#### 1단계. 작업 디렉터리 생성

`docpilot` 소스를 담을 폴더를 만든다. (강의 교재 저장소와 별개인, 여러분 개인 프로젝트다.)

```bash
mkdir -p ~/projects/docpilot
cd ~/projects/docpilot
```

**확인**: `pwd`를 치면 `.../projects/docpilot`가 출력된다.

#### 2단계. Python 가상환경 만들기 (12-Factor #2 의존성 격리)

프로젝트마다 의존성을 격리해 다른 프로젝트와 충돌하지 않게 한다.

```bash
python3 -m venv .venv        # .venv 폴더에 격리된 파이썬 환경 생성
source .venv/bin/activate    # (Windows PowerShell: .venv\Scripts\Activate.ps1)
```

**확인**: 프롬프트 앞에 `(.venv)`가 붙는다. `which python`(Windows는 `where python`)이 `.../docpilot/.venv/...`를 가리킨다.

#### 3단계. 의존성 설치와 requirements.txt 고정

FastAPI와 ASGI 서버 uvicorn을 설치한다.

```bash
pip install --upgrade pip
pip install "fastapi==0.115.*" "uvicorn[standard]==0.32.*"
```

설치한 버전을 파일로 고정한다(재현 가능한 빌드의 기본).

`requirements.txt` — 아래 내용을 프로젝트 루트에 저장한다:

```text
fastapi==0.115.6
uvicorn[standard]==0.32.1
```

> `pip freeze > requirements.txt`로 자동 생성해도 되지만, 실습 재현성을 위해 위 버전으로 고정해 두자. 팀 전체가 같은 버전을 쓰면 "내 컴에선 되는데" 문제가 준다.

**확인**:

```bash
pip install -r requirements.txt   # 이미 설치돼 있으면 "already satisfied"
python -c "import fastapi, uvicorn; print('ok')"   # ok 출력
```

### 2부. FastAPI 앱 작성과 실행

#### 4단계. main.py 작성 (완결된 코드)

프로젝트 루트에 `main.py`를 만든다. 아래는 복붙해서 바로 돌아가는 완결 코드다.

```python
# main.py — docpilot week01: 첫 FastAPI 앱
from fastapi import FastAPI

# app 인스턴스가 곧 우리 서비스. 제목/버전은 자동 문서(/docs)에 노출된다.
app = FastAPI(title="docpilot", version="0.1.0")


@app.get("/")
def root() -> dict:
    """루트 엔드포인트: 서비스가 살아 있는지 사람이 눈으로 확인하는 용도."""
    return {"message": "Hello, DocPilot"}


@app.get("/health")
def health() -> dict:
    """헬스 체크: 로드밸런서/쿠버네티스가 기계적으로 확인하는 용도.

    4주차 이후 쿠버네티스 liveness/readiness probe가 이 엔드포인트를 부른다.
    지금부터 습관처럼 만들어 둔다.
    """
    return {"status": "ok"}
```

> `GET /`은 `{"message": "Hello, DocPilot"}` JSON을 반환한다. 과제 요구는 "Hello, DocPilot" 문구 노출이므로 JSON 메시지로 담았다. 순수 텍스트가 필요하면 `PlainTextResponse`로 바꿀 수 있지만, API는 JSON이 기본이다.

#### 5단계. uvicorn으로 로컬 실행 (12-Factor #7 포트 바인딩)

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- `main:app` = `main.py`의 `app` 객체를 실행
- `--reload` = 코드 저장 시 자동 재시작(개발용)
- `--port 8000` = 8000번 포트로 서비스 노출

**확인**: 터미널에 아래와 비슷한 로그가 뜨고 멈추지 않고 대기한다.

```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

#### 6단계. 브라우저와 curl로 확인

서버는 그대로 두고, **새 터미널**을 하나 더 연다.

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/health
```

**확인**: 각각 아래 JSON이 나온다.

```json
{"message":"Hello, DocPilot"}
{"status":"ok"}
```

브라우저에서도 확인하자:

- <http://127.0.0.1:8000/> → `{"message":"Hello, DocPilot"}`
- <http://127.0.0.1:8000/health> → `{"status":"ok"}`
- <http://127.0.0.1:8000/docs> → FastAPI가 자동 생성한 Swagger UI (엔드포인트를 눌러 직접 실행 가능)

확인이 끝나면 서버 터미널에서 `Ctrl+C`로 서버를 멈춘다.

### 3부. Git 시작과 GitHub 푸시 (12-Factor #1 코드베이스)

#### 7단계. .gitignore 작성

가상환경·캐시는 저장소에 넣지 않는다. 루트에 `.gitignore` 생성:

```text
# Python
.venv/
__pycache__/
*.pyc
.pytest_cache/

# Env / secrets
.env
.env.*

# OS / editor
.DS_Store
.idea/
.vscode/
```

#### 8단계. git init과 첫 커밋

```bash
git init
git add .
git status          # 커밋될 파일 목록 확인
git commit -m "feat: docpilot week01 FastAPI 스캐폴드 (/, /health)"
```

**확인**: `git status`에 `.venv/`가 **안 보여야** 한다(정상적으로 무시됨). `git log --oneline`에 방금 커밋 한 줄이 보인다.

```bash
git log --oneline   # 예: 3f2a1b0 feat: docpilot week01 FastAPI 스캐폴드 (/, /health)
```

#### 9단계. GitHub 저장소 생성과 푸시

**방법 A — `gh` CLI (권장, 가장 간단)**:

```bash
gh auth login                       # 최초 1회 로그인 (브라우저 인증)
gh repo create docpilot --public --source=. --remote=origin --push
```

**방법 B — 웹에서 빈 저장소 만든 뒤 연결**:

GitHub 웹에서 `docpilot`라는 **빈** 저장소(README 없이)를 만든 다음:

```bash
git branch -M main
git remote add origin https://github.com/<your-username>/docpilot.git
git push -u origin main
```

**확인**:

```bash
git remote -v       # origin 주소가 보인다
git branch -vv      # main 이 origin/main 을 추적한다
```

GitHub 저장소 페이지를 새로고침하면 `main.py`, `requirements.txt`, `.gitignore`가 올라가 있다. 이걸로 **1주차 산출물 = 로컬 웹앱 + GitHub 저장소** 완성이다.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `command not found: uvicorn` | 가상환경 미활성 또는 미설치 | `source .venv/bin/activate` 후 `pip install -r requirements.txt` |
| `Address already in use` (포트 8000) | 이전 uvicorn이 안 죽음 | 다른 포트로 `--port 8001`, 또는 `lsof -i :8000`으로 PID 찾아 `kill <PID>` |
| 브라우저에서 접속 안 됨 | 서버가 안 떠 있음 | 서버 터미널이 "Application startup complete." 상태인지 확인 |
| `curl: (7) Failed to connect` | host를 `0.0.0.0`으로 띄웠는데 `127.0.0.1`로 접속 등 불일치 | 실행 host와 접속 host를 맞춘다 (로컬은 `127.0.0.1` 권장) |
| `ModuleNotFoundError: No module named 'fastapi'` | 다른 파이썬(전역)으로 실행 | `which python`이 `.venv`를 가리키는지 확인 후 재설치 |
| `git push` 인증 실패 | HTTPS 비밀번호 인증 폐지됨 | `gh auth login` 사용 또는 Personal Access Token / SSH 키 설정 |
| `--reload` 시 무한 재시작 | 가상환경 폴더 감시 | `.venv`를 프로젝트 밖에 두거나 `--reload-dir .`로 감시 범위 제한 |

---

## 이번 주 과제

**제출물**: GitHub `docpilot` 저장소 링크 + 아래 항목이 반영된 커밋.

1. **필수** — 위 실습(1~9단계)을 완주하고 GitHub에 푸시한다.
2. **기능 추가** — 자기 소개 엔드포인트 `GET /whoami`를 추가한다. 아래처럼 본인 정보를 담아 반환한다.

   ```python
   @app.get("/whoami")
   def whoami() -> dict:
       return {"name": "홍길동", "student_id": "20230000", "role": "docpilot builder"}
   ```

   `curl http://127.0.0.1:8000/whoami`로 확인 후, `feat: add /whoami endpoint` 메시지로 커밋·푸시한다.
3. **개념 정리(README)** — 저장소 루트에 `README.md`를 만들어 (1) IaaS/PaaS/SaaS 한 줄 정의, (2) 12-Factor 중 오늘 실제로 지킨 항목 3가지와 그 이유를 적는다.

> 제출: LMS에 저장소 URL과 마지막 커밋 해시를 제출한다.

---

## 체크리스트

- [ ] `python3 -m venv .venv`로 가상환경을 만들고 활성화했다.
- [ ] `requirements.txt`로 의존성을 고정했다.
- [ ] `main.py`에 `GET /`, `GET /health`를 구현했다.
- [ ] `uvicorn`으로 실행해 브라우저·curl로 두 엔드포인트를 확인했다.
- [ ] `/docs`에서 자동 문서를 확인했다.
- [ ] `.gitignore`를 작성해 `.venv`가 커밋되지 않게 했다.
- [ ] `git init` → 첫 커밋 → GitHub 푸시를 완료했다.
- [ ] (과제) `GET /whoami`를 추가하고 커밋·푸시했다.

---

## 다음 주 예고

[Week 2 — Docker 컨테이너 기초](./week02-docker-컨테이너-기초.md)

오늘 만든 `docpilot`은 "내 컴퓨터에선 잘 도는" 상태다. 다음 주에는 이걸 **Dockerfile로 컨테이너화**해서 어느 컴퓨터에서든 똑같이 돌게 만든다. 컨테이너 vs VM의 차이, 이미지·레이어·레지스트리 개념을 배우고, `docker build` → `docker run` → 레지스트리 푸시까지 간다. 12-Factor의 "Build, release, run"과 "Dev/prod parity"를 몸으로 체감하는 주다.
