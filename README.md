# Whisper EdgeCloud Transcription Server

Self-hosted faster-whisper API running on Theta EdgeCloud GPU containers.
Replaces OpenAI Whisper API dependency for Wave OS lyric video transcription.

## Architecture

```
Wave OS transcribeLyrics()  →  POST /transcribe-url  →  faster-whisper (GPU)
                                    ↓                        ↓
                            downloads audio            transcribes with
                            from private URL            word-level timestamps
                                    ↓                        ↓
                            temp file                  returns JSON segments
                                                              ↓
                                               Wave OS creates LyricLine records
```

## Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Health check + current model info |
| `/transcribe` | POST | Upload audio file directly (multipart) |
| `/transcribe-url` | POST | Pass audio URL, server fetches + transcribes |
| `/models` | GET | List available Whisper models |
| `/load-model` | POST | Hot-swap model at runtime |

## /transcribe-url Response Format

```json
{
  "language": "en",
  "duration": 187.42,
  "segments": [
    {
      "id": 0,
      "text": "I've been waiting for you",
      "start_time": 0.0,
      "end_time": 2.34
    },
    {
      "id": 1,
      "text": "under the neon lights tonight",
      "start_time": 2.34,
      "end_time": 5.12
    }
  ]
}
```

## Models

| Model | Size | VRAM | Speed | Accuracy |
|---|---|---|---|---|
| tiny | 75MB | ~1GB | Fastest | Basic |
| base | 145MB | ~1GB | Very Fast | Good |
| small | 485MB | ~2GB | Fast | Better |
| medium | 1.5GB | ~5GB | Medium | Great |
| large-v3 | 3GB | ~10GB | Slower | Best (default) |

## Deployment on Theta EdgeCloud

### Build & Push Image
```bash
docker build -t xbuildyteam/whisper-edge:latest .
docker push xbuildyteam/whisper-edge:latest
```

### Deploy via Theta Dashboard
1. Create custom template "Whisper EdgeCloud"
2. Select GPU instance (minimum: 1x GPU with 10GB+ VRAM for large-v3)
3. Set Docker image: `xbuildyteam/whisper-edge:latest`
4. Expose port 8000
5. Environment variables:
   - `WHISPER_MODEL=large-v3` (or `medium` for faster/cheaper)
   - `WHISPER_DEVICE=cuda`
   - `WHISPER_COMPUTE_TYPE=float16`
   - `PORT=8000`

### On-Demand vs Always-On

**Always-on** (recommended for now):
- Container stays running, responds instantly
- Cost: ~$0.05-0.10/hr GPU idle
- Simplest integration

**On-demand** (future optimization):
- Start container when transcription requested
- Stop after 5min idle timeout
- Cost: only pays for actual transcription time
- Requires ComputeSession management in Wave OS

## Cost Comparison

| Provider | Per-minute cost | 3-min song |
|---|---|---|
| OpenAI Whisper API | $0.006/min | $0.018 |
| Theta EdgeCloud GPU | ~$0.05/hr | ~$0.003 (large-v3 runs ~12x real-time on GPU) |
| Base44 integration | Credits-based | Varies |

Self-hosted on Theta is ~6x cheaper per transcription AND removes the external billing dependency entirely.

## Integration with Wave OS

The `transcribeLyrics` backend function calls:
```
POST {edgecloud_url}/transcribe-url
Body: { "url": "<private audio URL>", "language": "en" }
```

The EdgeCloud URL comes from the ComputeSession's `access_url` field, or is stored as a config constant when running always-on.
