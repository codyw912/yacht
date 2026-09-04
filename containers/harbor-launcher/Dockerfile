FROM python:3.12-slim-bookworm

ARG HARBOR_VERSION=0.20.0
ARG LITELLM_VERSION=1.91.3

# Builds behind a TLS-intercepting proxy need its CA at build time only.
# Pass it with `--secret id=build_ca,src=<pem>`; when absent the mount is
# empty and the stock trust store is used. The mount vanishes after each
# step, so the image ships no proxy-specific trust.
#
# Some HTTP proxies also cap concurrent connections per client; apt's
# default parallel fetch trips that and fails with "Connection refused"
# partway through an update. Serial downloads are a few seconds slower
# and always work.
RUN printf 'Acquire::Queue-Mode "access";\nAcquire::Retries "3";\n' \
        > /etc/apt/apt.conf.d/99serial-downloads

RUN --mount=type=secret,id=build_ca,target=/tmp/build-ca.pem,required=false,mode=0444 \
    set -eu; \
    if [ -s /tmp/build-ca.pem ]; then \
        export CURL_CA_BUNDLE=/tmp/build-ca.pem; \
        APT_CA='-o Acquire::https::CAInfo=/tmp/build-ca.pem'; \
    else \
        APT_CA=''; \
    fi; \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get $APT_CA update \
    && apt-get $APT_CA install -y --no-install-recommends \
        docker-ce-cli \
        docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=secret,id=build_ca,target=/tmp/build-ca.pem,required=false,mode=0444 \
    set -eu; \
    if [ -s /tmp/build-ca.pem ]; then export PIP_CERT=/tmp/build-ca.pem; fi; \
    pip install --no-cache-dir \
        "harbor==${HARBOR_VERSION}" \
        "litellm==${LITELLM_VERSION}"

COPY yacht_harbor_agents /opt/yacht/yacht_harbor_agents

ENV PYTHONPATH=/opt/yacht

WORKDIR /workspace

CMD ["harbor", "--version"]
