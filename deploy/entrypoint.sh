#!/bin/sh
# faster-whisper (ctranslate2) precisa achar cuBLAS/cuDNN que vêm junto com o torch
LD=$(ls -d /usr/local/lib/python3.12/site-packages/nvidia/*/lib 2>/dev/null | tr '\n' ':')
export LD_LIBRARY_PATH="${LD}${LD_LIBRARY_PATH:-}"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${MC_PORT:-8490}"
