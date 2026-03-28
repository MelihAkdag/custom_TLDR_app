from __future__ import annotations

import json
import os
import ssl
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from ..models import RawItem, SourceSettings, TopicProfile


class SourceAdapter(ABC):
    source_name: str
    item_type: str

    def __init__(self, settings: SourceSettings) -> None:
        self.settings = settings

    @abstractmethod
    def search(self, topic: TopicProfile, start_date: date, end_date: date) -> list[RawItem]:
        raise NotImplementedError

    def _get_json(self, url: str, params: dict[str, object]) -> dict:
        payload = self._get_text(url, params=params)
        return json.loads(payload)

    def _get_text(self, url: str, params: dict[str, object]) -> str:
        query = urlencode({key: value for key, value in params.items() if value is not None}, doseq=True)
        target = f"{url}?{query}" if query else url
        request = Request(target, headers={"User-Agent": self.settings.user_agent})
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds, context=self._build_ssl_context()) as response:
                return response.read().decode("utf-8")
        except URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, ssl.SSLCertVerificationError):
                host = urlparse(target).netloc or target
                raise RuntimeError(
                    f"SSL verification failed for {host}. Configure TLDR_FEED_CA_BUNDLE or "
                    "the source ca_bundle with your organization's trusted CA certificate."
                ) from exc
            raise

    def _build_ssl_context(self) -> ssl.SSLContext:
        if not self._should_verify_ssl():
            return ssl._create_unverified_context()

        ca_bundle = self._resolve_ca_bundle()
        if ca_bundle:
            return ssl.create_default_context(cafile=ca_bundle)
        return ssl.create_default_context()

    def _should_verify_ssl(self) -> bool:
        configured = self.settings.extra.get("verify_ssl")
        if configured is not None:
            return bool(configured)
        return not _is_truthy(os.getenv("TLDR_FEED_INSECURE_SSL"))

    def _resolve_ca_bundle(self) -> str | None:
        configured = self.settings.extra.get("ca_bundle")
        if configured is not None:
            candidate = _normalize_path(str(configured))
            return candidate if candidate else None

        for env_name in ("TLDR_FEED_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
            candidate = _normalize_path(os.getenv(env_name))
            if candidate:
                return candidate

        for candidate in (
            "/etc/ssl/certs/ca-certificates.crt",
            "/etc/pki/tls/certs/ca-bundle.crt",
            "/etc/ssl/cert.pem",
        ):
            resolved = _normalize_path(candidate)
            if resolved:
                return resolved
        return None


def _normalize_path(value: str | None) -> str | None:
    if not value:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    return candidate if Path(candidate).exists() else None


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().casefold() in {"1", "true", "yes", "on"}
