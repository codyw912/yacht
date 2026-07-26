FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/tools
WORKDIR /app

# The existing tool registry the conventions require new tools to join.
RUN printf 'echo\n' > /app/tools/registry.txt \
    && printf 'TOOL_NAME = "echo"\n\n\ndef run(args):\n    print(" ".join(args))\n    return 0\n' > /app/tools/echo.py
