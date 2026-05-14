# Pi Agent Runtime

Build the local Pi runtime image used by container-backed YACHT smokes:

```sh
docker build -t yacht/pi-agent-runtime:pi-0.74.0 containers/pi-agent-runtime
```

The image installs `@earendil-works/pi-coding-agent` from npm, runs as the
unprivileged `yacht` user, and expects YACHT to bind the trial home at
`/home/yacht` and the workspace at `/workspace`.
