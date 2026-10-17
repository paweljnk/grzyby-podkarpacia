"""Klient HTTP dla importów: cache na dysku, limit zapytań na host, ponawianie z wykładniczym opóźnieniem.

Odmowy dostępu (401/403/407) nie są ponawiane — zgłaszamy je wprost jako SourceUnavailable.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..config import CACHE_DIR

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
DENIED_STATUS = {401, 403, 407}
# Wikimedia i część usług publicznych wymagają User-Agenta z adresem kontaktowym projektu.
USER_AGENT = "GrzybyPodkarpacia/0.5 (+https://github.com/paweljnk/grzyby-podkarpacia)"


class SourceUnavailable(RuntimeError):
    """Źródło niedostępne (odmowa dostępu, brak sieci po wyczerpaniu prób)."""


@dataclass
class CachedResponse:
    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes
    from_cache: bool

    def json(self) -> Any:
        return json.loads(self.content)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class HttpClient:
    def __init__(
        self,
        cache_dir: Path = CACHE_DIR / "http",
        min_interval_s: float = 1.0,
        max_retries: int = 5,
        backoff_base_s: float = 1.0,
        backoff_max_s: float = 60.0,
        timeout_s: float = 60.0,
        sleep=time.sleep,
        transport: httpx.BaseTransport | None = None,
    ):
        self.cache_dir = cache_dir
        self.min_interval_s = min_interval_s
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.backoff_max_s = backoff_max_s
        self._sleep = sleep
        self._last_request: dict[str, float] = {}
        self._client = httpx.Client(
            timeout=timeout_s,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @staticmethod
    def cache_key(method: str, url: str, params: dict | None) -> str:
        raw = json.dumps([method, url, sorted((params or {}).items())], default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cache_paths(self, key: str) -> tuple[Path, Path]:
        d = self.cache_dir / key[:2]
        return d / f"{key}.body", d / f"{key}.meta.json"

    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            wait = self.min_interval_s - (time.monotonic() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = time.monotonic()

    def backoff_delay(self, attempt: int, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.backoff_max_s)
            except ValueError:
                pass
        delay = self.backoff_base_s * (2 ** attempt)
        return min(delay, self.backoff_max_s) * (0.8 + 0.4 * random.random())

    def request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        use_cache: bool = True,
        max_age_s: float | None = None,
    ) -> CachedResponse:
        key = self.cache_key(method, url, params)
        body_p, meta_p = self._cache_paths(key)
        if use_cache and body_p.exists() and meta_p.exists():
            meta = json.loads(meta_p.read_text())
            if max_age_s is None or time.time() - meta["fetched_at"] < max_age_s:
                return CachedResponse(meta["url"], meta["status_code"], meta["headers"], body_p.read_bytes(), True)

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle(url)
            try:
                r = self._client.request(method, url, params=params)
            except (httpx.ProxyError,) as e:
                # Odmowa tunelu przez proxy (np. polityka sieci) — nie ponawiamy.
                raise SourceUnavailable(f"{url}: odmowa połączenia przez proxy ({e})") from e
            except httpx.TransportError as e:
                last_error = e
                log.warning("Błąd sieci %s (próba %d): %s", url, attempt + 1, e)
            else:
                if r.status_code in DENIED_STATUS:
                    raise SourceUnavailable(f"{url}: HTTP {r.status_code} — dostęp zabroniony / wymaga uwierzytelnienia")
                if r.status_code in RETRY_STATUS:
                    last_error = RuntimeError(f"HTTP {r.status_code}")
                    log.warning("HTTP %d dla %s (próba %d)", r.status_code, url, attempt + 1)
                    if attempt < self.max_retries:
                        self._sleep(self.backoff_delay(attempt, r.headers.get("Retry-After")))
                    continue
                resp = CachedResponse(str(r.url), r.status_code, dict(r.headers), r.content, False)
                if use_cache and r.status_code == 200:
                    body_p.parent.mkdir(parents=True, exist_ok=True)
                    body_p.write_bytes(r.content)
                    meta_p.write_text(json.dumps({
                        "url": resp.url, "status_code": r.status_code,
                        "headers": resp.headers, "fetched_at": time.time(),
                    }))
                return resp
            if attempt < self.max_retries:
                self._sleep(self.backoff_delay(attempt))
        raise SourceUnavailable(f"{url}: niedostępne po {self.max_retries + 1} próbach ({last_error})")

    def get(self, url: str, **kw) -> CachedResponse:
        return self.request("GET", url, **kw)

    def download(self, url: str, dest: Path, chunk: int = 1 << 20) -> Path:
        """Pobiera duży plik strumieniowo; pomija, jeśli plik już istnieje i ma zgodny rozmiar."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(self.max_retries + 1):
            self._throttle(url)
            try:
                with self._client.stream("GET", url) as r:
                    if r.status_code in DENIED_STATUS:
                        raise SourceUnavailable(f"{url}: HTTP {r.status_code}")
                    if r.status_code in RETRY_STATUS:
                        raise httpx.TransportError(f"HTTP {r.status_code}")
                    r.raise_for_status()
                    size = int(r.headers.get("Content-Length", -1))
                    if dest.exists() and dest.stat().st_size == size:
                        return dest
                    tmp = dest.with_suffix(dest.suffix + ".part")
                    with open(tmp, "wb") as f:
                        for block in r.iter_bytes(chunk):
                            f.write(block)
                    tmp.replace(dest)
                    return dest
            except httpx.ProxyError as e:
                raise SourceUnavailable(f"{url}: odmowa połączenia przez proxy ({e})") from e
            except httpx.TransportError as e:
                log.warning("Pobieranie %s nieudane (próba %d): %s", url, attempt + 1, e)
                if attempt < self.max_retries:
                    self._sleep(self.backoff_delay(attempt))
        raise SourceUnavailable(f"{url}: pobieranie nieudane po {self.max_retries + 1} próbach")
