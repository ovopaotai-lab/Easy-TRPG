# Third-Party Open-Source Notices (Easy-TRPG)

Easy-TRPG itself (`server.py`, `enterprise_engine.py`, `static/*`, and launcher scripts)
is licensed under the **MIT License** (see `LICENSE`).

The standalone Windows and Linux release archives (`AI跑团工作台_Windows纯净版_*.zip` and
`AI跑团工作台_Linux纯净版_*.tar.gz`) bundle unmodified binary distributions of the following
open-source projects for zero-setup local inference:

1. **Strata** (`engine/strata/`)
   - Upstream: https://github.com/Niko1221/Strata
   - License: MIT License

2. **llama.cpp** (`engine/llama/` & `engine/strata/third_party/llama.cpp/`)
   - Upstream: https://github.com/ggml-org/llama.cpp
   - License: MIT License (`Copyright (c) 2023-2026 Georgi Gerganov and contributors`)

3. **Ollama** (`engine/ollama/`)
   - Upstream: https://github.com/ollama/ollama
   - License: MIT License (`Copyright (c) Ollama`)

4. **Python (CPython Embeddable Runtime)** (`runtime/python/`)
   - Upstream: https://www.python.org/
   - License: Python Software Foundation License Version 2 (PSF-2.0)

5. **GNU libgomp** (`libgomp.so.1` in Linux bundle)
   - Upstream: https://gcc.gnu.org/
   - License: GPLv3 with GCC Runtime Library Exception v3.1
