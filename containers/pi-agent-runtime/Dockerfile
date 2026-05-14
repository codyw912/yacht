FROM node:22-bookworm-slim

ARG PI_CODING_AGENT_VERSION=0.74.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        git \
        openssh-client \
        ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @earendil-works/pi-coding-agent@$PI_CODING_AGENT_VERSION \
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

CMD ["pi", "--version"]
