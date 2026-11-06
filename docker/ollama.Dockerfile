# Ollama with Sparky's AI model already inside, so it works with no internet.
FROM ollama/ollama:latest AS build

RUN sh -c 'ollama serve & pid=$!; \
    for i in $(seq 1 30); do ollama list >/dev/null 2>&1 && break; sleep 1; done; \
    ollama pull qwen3.5:4b; status=$?; kill $pid; exit $status'
# Libraries for other generations of graphics card, and a framework this model doesn't use: 3.3 GB
RUN rm -rf /usr/lib/ollama/cuda_v12 /usr/lib/ollama/mlx_cuda_v13

# Copying into a fresh image is what actually frees that space
FROM scratch
COPY --from=build / /
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV OLLAMA_HOST=0.0.0.0:11434
ENV LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV NVIDIA_VISIBLE_DEVICES=all
EXPOSE 11434
ENTRYPOINT ["/bin/ollama"]
CMD ["serve"]
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 CMD ollama list
