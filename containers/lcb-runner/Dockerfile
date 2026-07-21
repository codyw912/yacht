FROM python:3.11-slim-bookworm

ARG LCB_COMMIT=28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/LiveCodeBench/LiveCodeBench.git /opt/lcb \
    && git -C /opt/lcb checkout "$LCB_COMMIT" \
    && rm -rf /opt/lcb/.git

RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch \
    && pip install --no-cache-dir \
        "anthropic<0.49" \
        "datasets<4" \
        numpy \
        pebble \
        tqdm

ENV PYTHONPATH=/opt/lcb \
    HF_DATASETS_TRUST_REMOTE_CODE=1

WORKDIR /opt/lcb

CMD ["python", "-m", "lcb_runner.runner.custom_evaluator", "--help"]
