FROM node:22-bookworm-slim

RUN mkdir -p /app/data
WORKDIR /app

# The data files the task inventories; notes.md exists so the verifier
# can tell "listed the .txt files" from "listed everything".
RUN printf 'alpha\n' > /app/data/alpha.txt \
    && printf 'beta\n' > /app/data/beta.txt \
    && printf 'gamma\n' > /app/data/gamma.txt \
    && printf 'not a txt file\n' > /app/data/notes.md
