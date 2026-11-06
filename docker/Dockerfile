# Sparky's frontend and backend, with its models and starting content. No internet needed to run.
# Build with scripts\docker_build.bat, which prepares the private content in .docker-seed first.
# The image holds that content, so keep it private: don't push it to a public registry.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HOME=/app/models
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# The CPU build of torch saves several GB: only the search model uses it. Versions are the ones tested.
COPY deployment/requirements/ deployment/requirements/
RUN pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r deployment/requirements/simple_requirements.txt \
                                  -r deployment/requirements/voice_requirements.txt \
                                  sentence-transformers==2.7.0 faster-whisper==1.2.1 piper-tts==1.8.0 \
                                  av==18.1.0 numpy==2.5.4 onnxruntime==1.31.1 ctranslate2==4.8.5 \
                                  fastapi==0.162.0 uvicorn==0.54.0 scipy==1.18.1

# Speech recognition and search models
RUN python -c "from huggingface_hub import snapshot_download as d; d('Systran/faster-whisper-base'); d('sentence-transformers/all-MiniLM-L6-v2')"

COPY core/ core/
COPY config/ config/
COPY static/ static/
COPY simple_api.py .
# Starting content. The sparky-data volume copies this in on first run, so later changes survive.
COPY .docker-seed/data/ data/

# Everything is in the image, so never ask huggingface.co for updates
ENV HF_HUB_OFFLINE=1 API_HOST=0.0.0.0 API_PORT=8001
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=5s --start-period=120s --retries=6 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8001/ui', timeout=4)"
CMD ["python", "simple_api.py"]
