# Pinned launcher image for SWE-bench grading (the pattern from ADR 0012,
# applied to the last host-process native evaluator; see also
# containers/lcb-runner). The official swebench harness runs inside this
# container and drives per-instance evaluation containers through the
# mounted Docker socket; grading never runs on the host.
#
# Build:
#   docker build -t yacht/swebench-runner:swebench-4.1.0 containers/swebench-runner

FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir swebench==4.1.0

WORKDIR /work
