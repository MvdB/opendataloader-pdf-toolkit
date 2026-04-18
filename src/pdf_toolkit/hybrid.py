from __future__ import annotations

import socket
import subprocess
import time
from contextlib import contextmanager
from typing import Iterator


class HybridBackendError(RuntimeError):
    pass


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


@contextmanager
def hybrid_backend(
    port: int = 5002,
    ocr_lang: str = "en",
    force_ocr: bool = True,
    enrich_pictures: bool = False,
    startup_timeout: float = 60.0,
) -> Iterator[str]:
    """Spawn opendataloader-pdf-hybrid as a subprocess; yield its base URL."""
    cmd = ["opendataloader-pdf-hybrid", "--port", str(port)]
    if force_ocr:
        cmd.append("--force-ocr")
    if ocr_lang:
        cmd.extend(["--ocr-lang", ocr_lang])
    if enrich_pictures:
        cmd.append("--enrich-picture-description")

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError as exc:
        raise HybridBackendError(
            "opendataloader-pdf-hybrid not installed; try: pip install 'opendataloader-pdf[hybrid]'"
        ) from exc

    deadline = time.monotonic() + startup_timeout
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout is not None else b""
                raise HybridBackendError(
                    f"hybrid backend exited early (code {proc.returncode}):\n{(out or b'').decode(errors='replace')}"
                )
            if _port_open("127.0.0.1", port):
                break
            time.sleep(0.5)
        else:
            raise HybridBackendError(
                f"hybrid backend did not open port {port} within {startup_timeout}s"
            )
        yield f"http://127.0.0.1:{port}"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
