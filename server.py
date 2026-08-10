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
import sys
import tempfile
import httpx
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

# ── Config ─────────────────────────────────────────────
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "medium")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
NUM_WORKERS = int(os.environ.get("WHISPER_WORKERS", "1"))
PORT = int(os.environ.get("PORT", "8000"))

app = FastAPI(title="Whisper EdgeCloud", version="1.0.0")

# Lazy-loaded model — import happens on first use
_model = None
_whisper_import_error = None

def _try_import():
    global _whisper_import_error
    if _whisper_import_error is not None:
        return None, _whisper_import_error
    try:
        from faster_whisper import WhisperModel
        return WhisperModel, None
    except Exception as e:
        _whisper_import_error = str(e)
        print(f"[ERROR] Failed to import faster_whisper: {e}", file=sys.stderr, flush=True)
        return None, _whisper_import_error

def get_model():
    global _model
    if _model is None:
        WhisperModel, err = _try_import()
        if err:
            raise HTTPException(status_code=503, detail=f"Whisper not available: {err}")
        print(f"Loading faster-whisper model: {MODEL_SIZE} on {DEVICE} ({COMPUTE_TYPE})", flush=True)
        _model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            num_workers=NUM_WORKERS,
        )
        print(f"Model loaded: {MODEL_SIZE}", flush=True)
    return _model


def transcribe_audio(audio_path: str, language: str = None, word_timestamps: bool = True,
                     vad_filter: bool = True, vad_min_silence_ms: int = 500):
    """Transcribe audio file and return segments with timestamps."""
    model = get_model()
    
    kwargs = dict(
        language=language,
        word_timestamps=word_timestamps,
    )
    
    if vad_filter:
        kwargs["vad_filter"] = True
        kwargs["vad_parameters"] = dict(min_silence_duration_ms=vad_min_silence_ms)
    else:
        kwargs["vad_filter"] = False
    
    segments, info = model.transcribe(audio_path, **kwargs)
    
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
    WhisperModel, err = _try_import()
    return {
        "status": "healthy",
        "model": MODEL_SIZE,
        "device": DEVICE,
        "whisper_available": err is None,
        "whisper_error": err,
        "port": PORT,
    }


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
    vad_filter: bool = Form(default=True),
    vad_min_silence_ms: int = Form(default=500),
):
    """Upload an audio file and get back timestamped transcription segments."""
    suffix = os.path.splitext(file.filename or "audio.mp3")[1] or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        result = transcribe_audio(tmp_path, language=language,
                                  vad_filter=vad_filter,
                                  vad_min_silence_ms=vad_min_silence_ms)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


@app.post("/transcribe-url")
async def transcribe_url(body: dict):
    """Pass an audio URL — server fetches and transcribes.
    
    Body: {
      "url": "https://...",
      "language": "en" (optional),
      "vad_filter": false (optional, default true — disable for music with vocals),
      "vad_min_silence_ms": 300 (optional, default 500)
    }
    """
    url = body.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url' field")
    
    language = body.get("language")
    vad_filter = body.get("vad_filter", True)
    vad_min_silence_ms = body.get("vad_min_silence_ms", 500)
    
    # Determine file extension from URL or default to mp3
    suffix = ".mp3"
    url_lower = url.lower()
    for ext in [".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".webm"]:
        if ext in url_lower:
            suffix = ext
            break
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to download audio: HTTP {resp.status_code}"
                )
            tmp.write(resp.content)
            tmp_path = tmp.name
    
    try:
        result = transcribe_audio(tmp_path, language=language,
                                  vad_filter=vad_filter,
                                  vad_min_silence_ms=vad_min_silence_ms)
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
    print(f"Starting Whisper EdgeCloud on port {PORT} (model={MODEL_SIZE}, device={DEVICE})", flush=True)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        workers=1,
    )