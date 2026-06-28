---
title: Llama Swap Container Capabilities Research
description: Research notes on PiWatcher llama-swap and llama.cpp inference deployment options
ms.date: 2026-06-28
ms.topic: research
---

## Research Questions

* Does `ghcr.io/mostlygeek/llama-swap:unified-vulkan` include `llama-server`? If not certain, how should we verify locally?
* Conceptually, does llama-swap serve inference directly, or does it proxy/manage provider commands such as llama-server?
* If PiWatcher uses an external Pi 5 inference stack, what settings does PiWatcher need? Does it need model paths?
* If PiWatcher owns inference in compose, should it use llama-swap plus bundled server, llama-swap plus separate llama.cpp container, or only llama.cpp server?
* What is the simplest robust recommendation for this project?

## Local Evidence

* docker-compose.yml defines a `llama-swap` service using
  `ghcr.io/mostlygeek/llama-swap:unified-vulkan` by default. It mounts
  `deploy/llama-swap/config.yaml` into `/etc/llama-swap/config/config.yaml`,
  mounts `${LLAMA_SWAP_MODELS_DIR:-./tmp/llama-swap/models}` at `/models`, and
  runs `llama-swap --config /etc/llama-swap/config/config.yaml --listen
  0.0.0.0:8080`.
* deploy/llama-swap/config.yaml configures model `lfm2-vl-450m` with `cmd:
  llama-server --host 127.0.0.1 --port ${PORT} --model
  /models/lfm2-vl-450m.gguf --mmproj /models/lfm2-vl-450m-mmproj.gguf` and
  `ttl: 300`. That config assumes `llama-server` is available inside whatever
  environment runs the command.
* deploy/setup-llama-swap.sh writes the same config shape from environment
  variables. It prepares model files and config, but it does not install
  llama.cpp or llama-server on the host.
* packages/base/src/piwatcher_base/inference.py sends POST requests to
  `{LLAMA_SWAP_URL.rstrip('/')}/chat/completions` with an OpenAI-compatible
  chat-completions payload. It sends `model: LLAMA_SWAP_MODEL`, JSON response
  formatting, and a base64 data URL image. It does not reference local model
  file paths.
* packages/base/src/piwatcher_base/config.py exposes only `llama_swap_url`,
  `llama_swap_model`, thermal settings, and `inference_enabled` to the base
  application. Model file paths are compose and llama-swap deployment concerns,
  not PiWatcher app settings.
* README.md documents `LLAMA_SWAP_URL=http://127.0.0.1:8080/v1`,
  `LLAMA_SWAP_MODEL=lfm2-vl-450m`, the llama-swap image, model directory, model
  file names, and optional model download URLs. It says `make base-up` prepares
  model storage, starts llama-swap, and requires model GGUF files before using
  inference.
* Makefile target `base-llama-up` runs `bash deploy/setup-llama-swap.sh` and
  then `docker compose up -d llama-swap`.
* Local Docker inspection found the configured image already cached as
  `linux/amd64` with entrypoint `llama-swap` and default command pointing at
  `/etc/llama-swap/config/config.yaml`.
* A local container shell check found both `/usr/local/bin/llama-swap` and
  `/usr/local/bin/llama-server` inside the cached
  `ghcr.io/mostlygeek/llama-swap:unified-vulkan` image. The check warned that
  the cached image platform is `linux/amd64` while the current Mac host is
  `linux/arm64/v8`, so the Pi 5 arm64 variant should still be verified on the
  target host.

## External Evidence

* The llama-swap README describes llama-swap as a Go proxy and model-switching
  layer for local OpenAI-compatible and Anthropic-compatible servers. It says
  llama-swap works with any OpenAI-compatible server, including llama.cpp,
  vLLM, tabbyAPI, and stable-diffusion.cpp.
* The llama-swap README says the Docker unified container includes
  `llama-server`, `ik-llama-server`, stable-diffusion.cpp, whisper.cpp, and
  llama-swap built from source. The unified image family is described as
  recommended and available for CUDA and Vulkan.
* The llama-swap minimum viable config is a model ID whose `cmd` is
  `llama-server --port ${PORT} --model /path/to/model.gguf`. Its explanation
  says `cmd` is the command to run to start the server and `${PORT}` is an
  automatically assigned port.
* The llama-swap README explains that on an OpenAI-compatible request,
  llama-swap extracts the request `model` value, loads the corresponding server
  configuration, replaces the wrong upstream server when needed, and proxies to
  the appropriate upstream process.
* The llama-swap README directly answers whether llama-server is required: any
  OpenAI-compatible server works, but llama-swap was originally designed for
  llama-server and llama-server is the best supported upstream.
* The llama.cpp Docker documentation lists `ghcr.io/ggml-org/llama.cpp:server`
  as the image that only includes the `llama-server` executable, with
  `linux/amd64`, `linux/arm64`, and `linux/s390x` platforms.
* The llama.cpp server README documents an OpenAI-compatible HTTP server with
  `/v1/chat/completions`, `/v1/models`, multimodal support through typed
  `image_url` content, `response_format` JSON output, and Docker examples using
  `ghcr.io/ggml-org/llama.cpp:server`.
* The llama.cpp server README also documents built-in router mode for multiple
  models when `llama-server` starts without a single `--model`, including model
  load and unload endpoints. That provides an alternative to llama-swap for some
  multi-model cases, though it is llama.cpp-specific.

## Findings

1. `ghcr.io/mostlygeek/llama-swap:unified-vulkan` appears to include
   `llama-server`. Upstream documentation says unified images include
   `llama-server`, and the cached local image contains
   `/usr/local/bin/llama-server`. Because the local cached image is amd64, the
   exact Pi 5 arm64 image should be verified on the Pi 5 or with an explicit
   platform pull.
2. llama-swap does not perform model inference by itself in the same sense that
   llama.cpp does. It serves API endpoints, chooses a model from the request,
   starts or stops an upstream provider command, and proxies requests to that
   provider. In this repo, the provider command is `llama-server`.
3. PiWatcher only needs an OpenAI-compatible base URL and model name when using
   an external inference stack. For the current code, that means:
   `ENABLE_INFERENCE=true`, `LLAMA_SWAP_URL` or `PIWATCHER_LLAMA_SWAP_URL`, and
   `LLAMA_SWAP_MODEL` or `PIWATCHER_LLAMA_SWAP_MODEL`. The app does not need
   model file paths. Model paths are needed only by the external stack, such as
   llama-swap config or llama-server container args.
4. If PiWatcher owns inference in compose and only one model matters, a plain
   llama.cpp `llama-server` container is simpler than llama-swap. PiWatcher can
   keep its `LLAMA_SWAP_URL` setting name as a generic OpenAI-compatible endpoint
   for now because a direct llama-server also exposes `/v1/chat/completions`.
5. If PiWatcher wants automatic unload after idle, model switching, a UI for
   model status/logs, or future multi-provider routing, llama-swap remains useful.
   With the unified image, a separate llama.cpp container is unnecessary because
   the provider binary is bundled into the same image.
6. Running llama-swap plus a separate llama.cpp container is the most complex
   option for this project unless there is a specific need for container
   isolation, a custom llama.cpp build, or using provider containers managed via
   `cmd` and `cmdStop`.

## Recommended Approach

For the current PiWatcher project, the simplest robust path is to use one direct
llama.cpp `llama-server` container if the user is not worried about swapping
models. Configure it with the LFM2-VL model path and multimodal projector path,
serve on `0.0.0.0:8080`, and point PiWatcher at `http://127.0.0.1:8080/v1` with
`LLAMA_SWAP_MODEL` set to the server's model ID or alias.

If keeping the current compose file with minimal change is more valuable than
reducing layers, the existing llama-swap unified-image approach is plausible:
the unified image contains `llama-server`, and the repo config already starts it
inside llama-swap. That setup should be verified on the Pi 5 arm64 target before
depending on it unattended.

Do not add a separate llama.cpp container behind llama-swap for the default path.
It adds another service, another health boundary, and more networking/config
surface without solving a current PiWatcher requirement.

## Evaluated Alternatives

* External Pi 5 inference stack managed outside this repo. PiWatcher needs only
  `ENABLE_INFERENCE=true`, endpoint URL, and model name. This is operationally
  clean if the Pi 5 stack is already installed and maintained separately.
* Current llama-swap unified image in compose. This can work as a single
  inference service because the unified image bundles `llama-server`, and the
  repo's `cmd` starts `llama-server` internally. It preserves future model
  swapping and TTL unload behavior.
* llama-swap plus separate llama.cpp container. This is appropriate only when
  the upstream provider needs its own image/runtime lifecycle, such as a custom
  llama.cpp build or a provider container that llama-swap starts and stops via
  Docker or Podman commands. It is too much machinery for one fixed wildlife VLM.
* Direct llama.cpp `llama-server` container. This is the best fit when there is
  one model, no swapping requirement, and the app already speaks
  OpenAI-compatible `/v1/chat/completions`.

## Uncertainties and Verification

* The local image check verified an amd64 cached image. Verify the actual target
  image on the Pi 5 with:

```bash
docker run --rm --entrypoint sh ghcr.io/mostlygeek/llama-swap:unified-vulkan -c 'command -v llama-server && llama-server --version'
```

* To verify the manifest/platform behavior from another machine, use:

```bash
docker buildx imagetools inspect ghcr.io/mostlygeek/llama-swap:unified-vulkan
```

* To verify the PiWatcher API contract against either llama-swap or direct
  llama-server, start the inference endpoint and run:

```bash
curl http://127.0.0.1:8080/v1/models
```

* For direct llama.cpp, ensure the chosen image supports the Pi 5 target
  architecture and backend. The official `ghcr.io/ggml-org/llama.cpp:server`
  image supports `linux/arm64`; Vulkan-specific images also exist, but host
  device mapping and driver support on Raspberry Pi OS still need target
  validation.
* The current PiWatcher payload uses base64 `image_url` content and
  `response_format: {"type": "json_object"}`. llama.cpp docs document both
  capabilities, but the specific LFM2-VL GGUF, mmproj pairing, chat template,
  and JSON reliability should be smoke-tested with a real frame.
