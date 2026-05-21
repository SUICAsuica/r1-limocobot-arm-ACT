#!/usr/bin/env bash
set -euo pipefail

export MAMBA_ROOT_PREFIX="${HOME}/.local/share/mamba"
export PATH="${HOME}/.local/bin:${PATH}"

micromamba run -n qwen2_vl2b python "${HOME}/run_qwen2_vl_2b.py" "$@"
