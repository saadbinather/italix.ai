"""Report the runtime capabilities relevant to local MLX inference."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


print(f"Python: {sys.version.split()[0]}")
print(f"Architecture: {platform.machine()}")
print(f"macOS: {platform.mac_ver()[0]}")
print(f"Free storage: {shutil.disk_usage('.').free / 1024**3:.1f} GiB")

try:
    import mlx.core as mx

    print(f"MLX: {mx.__version__}")
    print(f"MLX default device: {mx.default_device()}")
    print(f"MLX Metal available: {mx.metal.is_available()}")
except (ImportError, AttributeError) as exc:
    print(f"MLX check failed: {exc}")

try:
    import torch

    print(f"PyTorch: {torch.__version__}")
    print(f"PyTorch MPS built: {torch.backends.mps.is_built()}")
    print(f"PyTorch MPS available: {torch.backends.mps.is_available()}")
except ImportError:
    print("PyTorch: not installed (not required for the MLX inference path)")
