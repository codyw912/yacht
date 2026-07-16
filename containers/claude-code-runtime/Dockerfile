FROM node:22-bookworm-slim

ARG CLAUDE_CODE_VERSION=2.1.211

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        git \
        openssh-client \
        ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@$CLAUDE_CODE_VERSION \
    && npm cache clean --force

RUN groupmod --new-name yacht node \
    && usermod \
        --login yacht \
        --gid yacht \
        --home /home/yacht \
        --move-home \
        node

USER yacht
WORKDIR /workspace

ENV HOME=/home/yacht

CMD ["claude", "--version"]
