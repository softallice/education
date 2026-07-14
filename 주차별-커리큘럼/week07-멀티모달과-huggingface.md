# Week 7 — 멀티모달과 Hugging Face (이미지·음성 + 임베딩)

> 이번 주 한 줄: 텍스트만 다루던 docpilot에 **이미지/음성**을 이해하는 능력과, 다음 주 RAG의 연료가 될 **텍스트 임베딩**을 더한다.
> docpilot 진화: 멀티모달 엔드포인트(이미지 캡셔닝 또는 음성→텍스트) + Hugging Face **임베딩 모델** 도입.

지난주 `/chat`은 "글자를 만드는" 능력이었다. 이번 주는 (1) 다른 형태의 입력을 이해하는 **멀티모달**, (2) 문장을 숫자 벡터로 바꾸는 **임베딩** — 이 둘을 붙인다. 임베딩은 [week08 RAG](./week08-rag-검색증강생성.md)에서 검색의 심장이 된다.

---

## 학습 목표

- [ ] 멀티모달(이미지/음성/비전)의 개념과 대표 태스크(captioning, ASR)를 예를 들어 설명할 수 있다.
- [ ] Hugging Face 생태계(Hub, `transformers`, Inference API, 임베딩 모델)를 구성 요소별로 구분해 설명할 수 있다.
- [ ] **자체호스팅(local transformers) vs 매니지드(Inference API)** 트레이드오프를 설명할 수 있다.
- [ ] docpilot에 이미지 캡셔닝 **또는** 음성→텍스트 엔드포인트를 추가한다.
- [ ] HF 임베딩 모델로 텍스트를 벡터로 변환하고 유사도를 계산한다(RAG 준비).

---

## 사전 준비

- week06까지의 docpilot(`/chat` 동작). [week06](./week06-llm-api-연동.md) 참고.
- **Hugging Face 계정 + Access Token**: [huggingface.co](https://huggingface.co) → Settings → Access Tokens → New token(`read` 권한이면 충분). 무료 티어로 Inference API를 소량 사용할 수 있다.
- 디스크 여유: 로컬 `transformers` 모델은 수백 MB~수 GB를 내려받는다.
- (음성 실습 시) 시스템에 `ffmpeg` 설치 권장.

```bash
# ffmpeg (오디오 디코딩에 필요할 수 있음)
sudo apt-get update && sudo apt-get install -y ffmpeg   # Debian/Ubuntu
# macOS: brew install ffmpeg
```

---

## 개념 (요약)

### 1) 멀티모달이란

"모달리티(modality)"는 데이터의 형태다: 텍스트, 이미지, 음성, 비디오. **멀티모달** 모델/시스템은 여러 형태를 함께 다룬다. 대표 태스크:

| 태스크 | 입력 → 출력 | 예 모델 |
|---|---|---|
| 이미지 캡셔닝(image-to-text) | 이미지 → 설명 문장 | `Salesforce/blip-image-captioning-base` |
| 자동 음성 인식(ASR, speech-to-text) | 오디오 → 텍스트 | `openai/whisper-small` |
| 비전 질의응답(VQA) / 멀티모달 LLM | 이미지+질문 → 답 | GPT-4o, Gemini(비전) |
| 텍스트 임베딩 | 문장 → 숫자 벡터 | `sentence-transformers/all-MiniLM-L6-v2` |

docpilot 관점: 사용자가 **스크린샷/다이어그램(이미지)** 이나 **음성 메모** 로 질문을 던질 수 있게 된다.

### 2) Hugging Face 생태계

- **Hub**: 모델·데이터셋·데모(Spaces)를 공유하는 "깃허브 for ML". 모델마다 카드(설명)와 태스크 태그가 있다.
- **`transformers`**: 모델을 **내 컴퓨터/서버에서 직접** 실행하는 파이썬 라이브러리. `pipeline("task", model=...)` 한 줄로 추론.
- **Inference API / Inference Providers**: HF가 **대신 호스팅**해 주는 HTTP API. 모델을 내려받지 않고 호출.
- **임베딩 모델**: `sentence-transformers` 계열이 대표적. 문장을 고정 길이 벡터로 바꾼다.

### 3) 임베딩과 유사도 (RAG의 씨앗)

- **임베딩(embedding)**: 문장을 의미를 담은 숫자 벡터(예: 384차원)로 변환. 뜻이 비슷한 문장은 벡터도 가깝다.
- **코사인 유사도(cosine similarity)**: 두 벡터가 이루는 각도로 유사도를 잰다. 1에 가까울수록 비슷, 0이면 무관.

```
"강아지가 뛴다"  →  [0.12, -0.4, ...]   ┐  두 벡터의 코사인 유사도 ↑ (비슷)
"개가 달린다"    →  [0.10, -0.38, ...]  ┘
"세금 신고 방법" →  [-0.5, 0.2, ...]       코사인 유사도 ↓ (무관)
```

week08에서는 "질문 임베딩"과 "문서 조각 임베딩"의 유사도로 **관련 조각을 검색**한다.

### 4) 자체호스팅 vs 매니지드 트레이드오프

| 기준 | 로컬 `transformers`(자체호스팅) | Inference API(매니지드) |
|---|---|---|
| 초기 지연 | 모델 다운로드·로딩 필요(수 초~분) | 없음(HTTP 호출) |
| 비용 | 하드웨어(특히 GPU)·전기 | 호출량 기반 요금(무료 티어 있음) |
| 데이터 프라이버시 | 데이터가 서버 밖으로 안 나감 | 외부로 전송됨 |
| 오프라인 | 가능 | 불가(네트워크 필요) |
| 확장성 | 직접 스케일링(week12 K8s) | 제공자가 처리 |
| 콜드스타트 | 프로세스가 모델 상주 | 모델에 따라 콜드스타트 있음 |

실무 감각: **개인정보/규제 데이터·대량 처리·오프라인**이면 자체호스팅, **빠른 시작·간헐적 사용**이면 매니지드.

---

## 실습: 단계별 따라하기

이번 주 흐름:
- **1부**: 임베딩 붙이기(로컬) — RAG 준비. (가장 중요, 반드시 완료)
- **2부**: 멀티모달 엔드포인트 — 이미지 캡셔닝(로컬) **또는** 음성→텍스트.
- **3부**: 매니지드 대안(HF Inference API)로 같은 일을 해보고 트레이드오프 체감.

### 1부. 임베딩 붙이기 (RAG 준비)

#### 1단계. 패키지 설치

무엇을/왜: 임베딩 모델(`sentence-transformers`)과 멀티모달 파이프라인(`transformers`)을 설치한다.

```bash
pip install "sentence-transformers>=3.0" "transformers>=4.44" "torch>=2.2" "pillow>=10.0" "huggingface_hub>=0.24" numpy
```

`requirements.txt`에도 추가한다.

```text
# requirements.txt (추가)
sentence-transformers>=3.0
transformers>=4.44
torch>=2.2
pillow>=10.0
huggingface_hub>=0.24
numpy
```

**확인**:

```bash
python -c "import sentence_transformers, transformers, torch; print('ml stack ok, torch', torch.__version__)"
```

기대 출력: `ml stack ok, torch 2.x.x`.

#### 2단계. HF 토큰을 환경변수로 등록

무엇을/왜: 공개 모델은 토큰 없이도 받아지지만, Inference API(3부)와 rate limit 완화를 위해 토큰을 둔다. week06처럼 `.env`에 넣는다.

`.env`에 추가:

```bash
# Hugging Face
HF_TOKEN=hf_...본인_토큰...
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CAPTION_MODEL=Salesforce/blip-image-captioning-base
ASR_MODEL=openai/whisper-small
```

`app/config.py`의 `Settings`에 필드를 추가한다(week06에서 만든 파일).

```python
# app/config.py  (Settings 클래스 안에 추가)
    # Hugging Face
    hf_token: str | None = None
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    caption_model: str = "Salesforce/blip-image-captioning-base"
    asr_model: str = "openai/whisper-small"
```

**확인**:

```bash
python -c "from app.config import get_settings; s=get_settings(); print(s.embedding_model, '| hf token set:', bool(s.hf_token))"
```

기대 출력: `sentence-transformers/all-MiniLM-L6-v2 | hf token set: True`.

#### 3단계. 임베딩 모듈 (`app/embeddings.py`)

무엇을/왜: 문장 리스트를 벡터로 바꾸는 함수와 코사인 유사도를 제공한다. 모델은 **한 번만 로딩**해 재사용(매 호출 로딩은 느리고 낭비).

```python
# app/embeddings.py
from __future__ import annotations

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import get_settings


@lru_cache
def get_model() -> SentenceTransformer:
    """임베딩 모델을 최초 1회만 로딩(프로세스 내 재사용)."""
    settings = get_settings()
    return SentenceTransformer(settings.embedding_model)


def embed(texts: list[str]) -> np.ndarray:
    """문장 리스트 → (n, dim) 벡터 배열. 코사인용으로 정규화한다."""
    model = get_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,  # L2 정규화 → 내적이 곧 코사인 유사도
        convert_to_numpy=True,
    )
    return vectors


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """정규화된 두 벡터의 코사인 유사도(=내적)."""
    return float(np.dot(a, b))
```

동작을 스크립트로 확인한다:

```python
# scratch_embed.py
from app.embeddings import embed, cosine_similarity

sentences = ["강아지가 공원에서 뛴다", "개가 달리고 있다", "오늘 세금 신고를 했다"]
vecs = embed(sentences)
print("shape:", vecs.shape)  # 예: (3, 384)
print("뜻 비슷:", round(cosine_similarity(vecs[0], vecs[1]), 3))   # 높게
print("뜻 무관:", round(cosine_similarity(vecs[0], vecs[2]), 3))   # 낮게
```

```bash
python scratch_embed.py
```

**확인**: (최초 실행은 모델 다운로드로 지연) `shape: (3, 384)` 그리고 "뜻 비슷" 값이 "뜻 무관" 값보다 확실히 크다. → 임베딩이 의미를 담고 있음을 확인.

#### 4단계. `/embed` 엔드포인트 추가

무엇을/왜: 임베딩을 API로 노출해, week08 인덱싱 파이프라인이 재사용하게 한다.

`app/main.py`에 추가:

```python
# app/main.py  (추가)
from pydantic import BaseModel, Field
from app import embeddings


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=64)


class EmbedResponse(BaseModel):
    model: str
    dim: int
    vectors: list[list[float]]


@app.post("/embed", response_model=EmbedResponse)
async def create_embeddings(req: EmbedRequest) -> EmbedResponse:
    """텍스트 리스트를 임베딩 벡터로 변환한다(week08 RAG에서 재사용)."""
    from app.config import get_settings

    vecs = embeddings.embed(req.texts)
    return EmbedResponse(
        model=get_settings().embedding_model,
        dim=int(vecs.shape[1]),
        vectors=vecs.tolist(),
    )
```

```bash
uvicorn app.main:app --reload
```

```bash
curl -s -X POST http://localhost:8000/embed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["docpilot은 문서 도우미다", "kubernetes 배포"]}' \
  | python -c "import sys, json; d=json.load(sys.stdin); print('model:', d['model']); print('dim:', d['dim']); print('vec0 앞 5개:', d['vectors'][0][:5])"
```

**확인**: `dim: 384`와 벡터 앞 5개 숫자가 출력된다.

---

### 2부. 멀티모달 엔드포인트 (택1: 이미지 캡셔닝 / 음성→텍스트)

둘 중 하나만 해도 이번 주 목표는 충족된다. 시간이 되면 둘 다. 모두 **로컬 `transformers`** 로 구현한다.

#### 5단계-A. 이미지 캡셔닝 (`/caption`)

무엇을/왜: 업로드한 이미지를 설명 문장으로 바꾼다. BLIP 모델 사용.

`app/vision.py`:

```python
# app/vision.py
from __future__ import annotations

import io
from functools import lru_cache

from PIL import Image
from transformers import pipeline

from app.config import get_settings


@lru_cache
def get_captioner():
    """이미지 캡셔닝 파이프라인을 1회 로딩."""
    settings = get_settings()
    return pipeline("image-to-text", model=settings.caption_model)


def caption_image(image_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    result = get_captioner()(image)
    # result 예: [{"generated_text": "a dog running in a park"}]
    return result[0]["generated_text"].strip()
```

`app/main.py`에 업로드 엔드포인트 추가:

```python
# app/main.py  (추가)
from fastapi import UploadFile, File, HTTPException
from app import vision

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8MB


@app.post("/caption")
async def caption(file: UploadFile = File(...)) -> dict:
    """이미지를 업로드하면 설명 문장을 돌려준다."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail=f"unsupported type: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large (max 8MB)")
    text = vision.caption_image(data)
    return {"filename": file.filename, "caption": text}
```

테스트용 이미지를 하나 받아 호출한다:

```bash
# 아무 샘플 이미지 (또는 본인 이미지 사용)
# 외부 URL은 언제든 사라질 수 있다(link rot). 아래 curl이 실패하거나 빈 파일이 받아지면
# 로컬에 있는 아무 jpg/png(예: 강아지 사진)를 sample.jpg로 복사해 그대로 진행한다.
curl -sL -o sample.jpg "https://huggingface.co/datasets/mishig/sample_images/resolve/main/dog.jpg"

curl -s -X POST http://localhost:8000/caption \
  -F "file=@sample.jpg;type=image/jpeg" | python -m json.tool
```

**확인**: (최초는 모델 다운로드로 지연) 아래처럼 영어 캡션이 나온다.

```json
{
    "filename": "sample.jpg",
    "caption": "a dog running through a grassy field"
}
```

> 응용: 캡션을 week06의 `/chat`에 넘겨 "이 이미지에 대해 한국어로 설명해줘"처럼 결합하면 멀티모달 대화가 된다(과제).

#### 5단계-B. 음성 → 텍스트 (`/transcribe`)

무엇을/왜: 업로드한 오디오를 텍스트로 받아쓴다. Whisper 사용.

`app/audio.py`:

```python
# app/audio.py
from __future__ import annotations

import tempfile
from functools import lru_cache

from transformers import pipeline

from app.config import get_settings


@lru_cache
def get_transcriber():
    settings = get_settings()
    return pipeline("automatic-speech-recognition", model=settings.asr_model)


def transcribe(audio_bytes: bytes, suffix: str = ".wav") -> str:
    # transformers ASR 파이프라인은 파일 경로/배열을 받는다 → 임시파일로 저장
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        # Whisper는 기본적으로 30초 창만 처리한다. 30초를 넘는 입력은 chunk_length_s로
        # 잘게 나눠 넣고 return_timestamps=True로 조각을 이어붙여야 잘리거나 실패하지 않는다.
        result = get_transcriber()(tmp.name, chunk_length_s=30, return_timestamps=True)
    return result["text"].strip()
```

`app/main.py`에 추가:

```python
# app/main.py  (추가)
import os
from app import audio

ALLOWED_AUDIO_TYPES = {"audio/wav", "audio/x-wav", "audio/flac", "audio/x-flac", "audio/mpeg", "audio/mp3", "audio/m4a", "audio/webm"}


@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)) -> dict:
    """오디오를 업로드하면 받아쓴 텍스트를 돌려준다."""
    if file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail=f"unsupported type: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large (max 8MB)")
    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    text = audio.transcribe(data, suffix=suffix)
    return {"filename": file.filename, "text": text}
```

샘플 오디오로 호출:

```bash
# 이 샘플은 실제로 flac 포맷이므로 확장자·MIME 타입을 flac로 맞춘다(ffmpeg 필요, 사전 준비 참고).
# 외부 URL이 사라졌거나 다운로드가 실패하면, 로컬에 있는 아무 오디오 파일(.flac/.wav/.mp3 등)로 대체한다.
curl -sL -o sample.flac "https://huggingface.co/datasets/Narsil/asr_dummy/resolve/main/1.flac"

curl -s -X POST http://localhost:8000/transcribe \
  -F "file=@sample.flac;type=audio/flac" | python -m json.tool
```

**확인**: `"text": "..."`에 받아쓴 문장이 담긴다.

---

### 3부. 매니지드 대안 — HF Inference API

무엇을/왜: 모델을 내려받지 않고 **HF가 호스팅**하는 엔드포인트를 호출한다. 로컬과 결과를 비교하며 트레이드오프를 체감한다.

#### 6단계. Inference API로 임베딩/캡셔닝 호출

`app/hf_managed.py`:

```python
# app/hf_managed.py
from __future__ import annotations

from huggingface_hub import AsyncInferenceClient

from app.config import get_settings

# 참고: 예전 serverless 엔드포인트(api-inference.huggingface.co/models/...)는
# 현재 Inference Providers(router.huggingface.co)로 이전됐고, all-MiniLM 같은
# 소형 모델은 무료 serverless로 안 뜨는 경우가 많다. 직접 URL을 치지 말고
# huggingface_hub의 InferenceClient가 최신 라우팅을 대신 처리하게 한다.
# (배포 전 https://huggingface.co/docs/huggingface_hub 에서 현행 사용법 재확인 권장)


def _client() -> AsyncInferenceClient:
    settings = get_settings()
    if not settings.hf_token:
        raise RuntimeError("HF_TOKEN is required for the Inference API")
    return AsyncInferenceClient(token=settings.hf_token)


async def embed_via_api(texts: list[str]) -> list[list[float]]:
    """feature-extraction으로 문장 임베딩을 받는다.

    무료 티어에서 특정 모델이 안 뜨면 404/`model not deployed`가 날 수 있다.
    그럴 땐 config의 embedding_model을 배포 가능한 모델로 교체한다.
    """
    settings = get_settings()
    client = _client()
    vectors: list[list[float]] = []
    for text in texts:
        vec = await client.feature_extraction(text, model=settings.embedding_model)
        vectors.append(vec.tolist())  # numpy 배열 → list[float]
    return vectors


async def caption_via_api(image_bytes: bytes) -> str:
    """이미지 바이트로 캡션을 받는다."""
    settings = get_settings()
    client = _client()
    out = await client.image_to_text(image_bytes, model=settings.caption_model)
    return out.generated_text.strip()
```

`app/main.py`에 확인용 엔드포인트 추가(선택):

```python
# app/main.py  (추가)
from app import hf_managed


@app.post("/embed-managed", response_model=EmbedResponse)
async def create_embeddings_managed(req: EmbedRequest) -> EmbedResponse:
    from app.config import get_settings

    vectors = await hf_managed.embed_via_api(req.texts)
    dim = len(vectors[0]) if vectors else 0
    return EmbedResponse(model=get_settings().embedding_model, dim=dim, vectors=vectors)
```

```bash
curl -s -X POST http://localhost:8000/embed-managed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["docpilot", "kubernetes"]}' \
  | python -c "import sys, json; d=json.load(sys.stdin); print('dim:', d['dim'])"
```

**확인**: `dim: 384`. 로컬(`/embed`)과 차원이 같다. → 같은 모델이면 로컬/매니지드 결과가 호환된다(week08에서 인덱싱·질의를 같은 모델로 맞추는 게 중요한 이유).

> 참고: 무료 티어 모델은 첫 호출에서 콜드스타트(모델 로딩) 때문에 503 `currently loading`을 반환할 수 있다. 잠시 후 재시도하면 된다.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| 최초 호출이 매우 느림 | 모델 다운로드/로딩 | 정상. 이후 캐시(`~/.cache/huggingface`)로 빨라짐. 컨테이너면 캐시 볼륨 마운트 |
| `torch` 설치 실패/무거움 | 플랫폼별 휠 | CPU만 쓰면 그대로 OK. 그래도 무거우면 `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| 이미지 `cannot identify image file` | 실제 이미지가 아님/손상 | 파일이 진짜 jpg/png인지 확인. `content_type` 헤더 확인 |
| ASR에서 `ffmpeg not found` | ffmpeg 미설치 | `apt-get install ffmpeg` / `brew install ffmpeg` |
| ASR이 30초 넘는 오디오에서 뒷부분이 잘리거나 실패 | Whisper 기본은 30초 창만 처리 | 파이프라인 호출에 `chunk_length_s=30`(긴 입력 청킹) 또는 `return_timestamps=True` 추가(본 문서 `transcribe` 참고) |
| Inference API 503 `loading` | 매니지드 모델 콜드스타트 | 수 초~수십 초 대기 후 재시도 |
| Inference API 401 | 토큰 없음/무효 | `.env`의 `HF_TOKEN` 확인, `read` 권한 토큰인지 확인 |
| `OutOfMemory`/프로세스 강제종료 | RAM 부족(대형 모델) | 더 작은 모델 사용(`whisper-base`, `MiniLM`), 배치 크기 축소 |
| 임베딩 유사도가 이상함 | 정규화 누락/모델 불일치 | `normalize_embeddings=True` 확인. 인덱싱·질의를 **같은 모델**로 |
| 매번 모델 다시 로딩 | 함수 안에서 매번 생성 | `@lru_cache`로 파이프라인/모델을 1회만 로딩했는지 확인 |

---

## 이번 주 과제

제출물(커밋 + 실행 로그/스크린샷):

1. **필수** — `/embed`가 동작하고, 의미가 비슷한 두 문장의 코사인 유사도가 무관한 문장보다 높음을 보이기(수치 캡처).
2. **필수** — 멀티모달 엔드포인트(`/caption` 또는 `/transcribe`) 중 하나를 구현하고 실제 입력으로 결과를 받기.
3. **도전** — 멀티모달 + LLM 결합: 이미지 캡션(또는 전사 텍스트)을 week06 `/chat`에 넣어 "이 내용을 한국어로 요약해줘"를 수행하는 `/describe` 엔드포인트 만들기.
4. **도전** — 같은 임베딩을 로컬(`/embed`)과 매니지드(`/embed-managed`)로 뽑아 응답 시간·차원·첫 5개 값의 차이를 비교하고, 어떤 상황에 어느 쪽이 유리한지 한 문단으로 서술.
5. **분석** — 자체호스팅 vs 매니지드 트레이드오프 표를 **docpilot 관점**(우리 서비스가 학교 서버에 배포될 때)으로 다시 작성.

---

## 체크리스트

- [ ] `sentence-transformers`, `transformers`, `torch`, `pillow` 설치 및 `requirements.txt` 반영
- [ ] `.env`에 `HF_TOKEN`·모델명 추가, `Settings`에 필드 추가
- [ ] `app/embeddings.py`로 임베딩·코사인 유사도 구현(모델 1회 로딩)
- [ ] `/embed` 동작, 의미 유사도 관찰
- [ ] `/caption` 또는 `/transcribe` 중 하나 이상 구현·확인
- [ ] (선택) HF Inference API(`/embed-managed`)로 매니지드 방식 체감
- [ ] 자체호스팅 vs 매니지드 트레이드오프를 설명할 수 있음

---

## 다음 주 예고

[Week 8 — RAG(검색증강생성)](./week08-rag-검색증강생성.md): 이번 주의 **임베딩**과 week06의 **LLM 생성**을 하나로 잇는다. 업로드 문서를 잘게 쪼개(청킹) 임베딩해 **벡터DB(Chroma)** 에 저장하고, 질문이 오면 관련 조각을 검색해 LLM에 컨텍스트로 주입하는 `/ask`를 만든다. 이것이 **Block 2 미니 과제**다. 이번 주 `/embed`가 그 파이프라인의 첫 부품이 된다.
