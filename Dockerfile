FROM python:3.11

# Install ffmpeg and build tools needed by CTranslate2
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# CPU mode — int8 quantization for speed on CPU
ENV WHISPER_MODEL=medium
ENV WHISPER_DEVICE=cpu
ENV WHISPER_COMPUTE_TYPE=int8
ENV PORT=8000

EXPOSE 8000

CMD ["python", "server.py"]
