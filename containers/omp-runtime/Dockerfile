FROM node:22-bookworm-slim

ARG OMP_VERSION=17.2.15

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        git \
        openssh-client \
        ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @oh-my-pi/pi-coding-agent@$OMP_VERSION \
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

CMD ["omp", "--version"]
