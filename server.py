"""
Whisper EdgeCloud Transcription Server
Self-hosted faster-whisper API for Wave OS lyric video transcription.

Endpoints:
  POST /transcribe   — upload audio file, get back timestamped segments
  POST /transcribe-url — pass audio URL, server fetches and transcribes
  GET  /health        — health check
  GET  /models        — list available models
  POST /load-model    — hot-swap model at runtime
"""

import os
import tempfile
import httpx
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

# ── Config ─────────────────────────────────────────────
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "large-v3")
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
NUM_WORKERS = int(os.environ.get("WHISPER_WORKERS", "1"))

app = FastAPI(title="Whisper EdgeCloud", version="1.0.0")

# Lazy-loaded model (loads on first request to avoid startup timeout)
_model = None
_model_lock = None

def get_model():
    global _model
    if _model is None:
        print(f"Loading faster-whisper model: {MODEL_SIZE} on {DEVICE} ({COMPUTE_TYPE})")
        _model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            num_workers=NUM_WORKERS,
        )
        print(f"Model loaded: {MODEL_SIZE}")
    return _model


def transcribe_audio(audio_path: str, language: str = None, word_timestamps: bool = True):
    """Transcribe audio file and return segments with timestamps."""
    model = get_model()
    
    segments, info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=word_timestamps,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    
    result_segments = []
    for i, segment in enumerate(segments):
        result_segments.append({
            "id": i,
            "text": segment.text.strip(),
            "start_time": round(segment.start, 2),
            "end_time": round(segment.end, 2),
        })
    
    return {
        "language": info.language,
        "duration": round(info.duration, 2),
        "segments": result_segments,
    }


# ── Endpoints ──────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "model": MODEL_SIZE, "device": DEVICE}


@app.get("/models")
async def list_models():
    return {
        "current": MODEL_SIZE,
        "available": ["tiny", "base", "small", "medium", "large-v3"],
    }


@app.post("/transcribe")
async def transcribe_upload(
    file: UploadFile = File(...),
    language: str = Form(default=None),
):
    """Upload an audio file and get back timestamped transcription segments."""
    # Save to temp file
    suffix = os.path.splitext(file.filename or "audio.mp3")[1] or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        result = transcribe_audio(tmp_path, language=language)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


@app.post("/transcribe-url")
async def transcribe_url(body: dict):
    """Pass an audio URL — server fetches and transcribes.
    
    Body: { "url": "https://...", "language": "en" (optional) }
    """
    url = body.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url' field")
    
    language = body.get("language")
    
    # Download the audio file
    suffix = ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to download audio: {resp.status_code}"
                )
            tmp.write(resp.content)
            tmp_path = tmp.name
    
    try:
        result = transcribe_audio(tmp_path, language=language)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


@app.post("/load-model")
async def load_model(body: dict):
    """Hot-swap the Whisper model at runtime."""
    global MODEL_SIZE, _model
    new_model = body.get("model")
    if new_model not in ["tiny", "base", "small", "medium", "large-v3"]:
        raise HTTPException(status_code=400, detail="Invalid model name")
    
    MODEL_SIZE = new_model
    _model = None  # Force reload on next request
    return {"status": "model_swapped", "new_model": new_model}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        workers=1,
    )
