"""HTTPS helper: keeps TLS certificate verification ON, using the OS CA bundle when Python lacks one."""

from __future__ import annotations

import os
import ssl
import urllib.request
from typing import Any

_CA_CANDIDATES = (
    "/etc/ssl/cert.pem",  # macOS
    "/etc/ssl/certs/ca-certificates.crt",  # Debian/Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",  # RHEL/Fedora
)

_CTX: ssl.SSLContext | None = None


def _build_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    # If default store is empty (common with python.org / CLT builds on macOS), load OS bundle.
    try:
        has_default = bool(ctx.cert_store_stats().get("x509_ca"))
    except Exception:
        has_default = False
    if not has_default:
        env_ca = os.environ.get("SSL_CERT_FILE", "")
        for cand in (env_ca, *_CA_CANDIDATES):
            if cand and os.path.isfile(cand):
                ctx.load_verify_locations(cafile=cand)
                break
    return ctx


def secure_urlopen(req: Any, timeout: float = 30) -> Any:
    """urllib.request.urlopen with verified TLS (never disables verification)."""
    global _CTX
    if _CTX is None:
        _CTX = _build_context()
    return urllib.request.urlopen(req, timeout=timeout, context=_CTX)

