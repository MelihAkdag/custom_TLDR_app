from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import NormalizedItem, SummaryRecord
from .utils import truncate_text, utc_now


class Summarizer(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    def full_provider_name(self) -> str:
        return self.provider_name

    def summarize(self, item: NormalizedItem) -> SummaryRecord:
        metadata_markdown = build_metadata_markdown(item)
        excerpt = truncate_text(item.abstract_or_body, limit=10000)
        if not excerpt:
            return _build_metadata_only_summary(item, metadata_markdown, self.full_provider_name)

        prompt = build_summary_prompt(item, excerpt)
        short_summary = self._request_summary(prompt)
        return SummaryRecord(
            item_id=item.item_id or "",
            provider=self.full_provider_name,
            metadata_markdown=metadata_markdown,
            source_excerpt=excerpt,
            short_summary=short_summary,
            generated_at=utc_now(),
        )

    @abstractmethod
    def _request_summary(self, prompt: str) -> str:
        raise NotImplementedError



def build_summarizer_from_env() -> Summarizer:
    provider = os.getenv("SUMMARIZER_PROVIDER", "azure_openai").strip().casefold()
    if provider in {"azure", "azure_openai"}:
        return AzureOpenAISummarizer()
    if provider == "ollama":
        return OllamaSummarizer()
    if provider == "gemini":
        return GeminiSummarizer()
    if provider in {"deterministic", "local"}:
        return DeterministicSummarizer()
    if provider == "noop":
        return NoopSummarizer()
    raise ValueError(
        "Unsupported SUMMARIZER_PROVIDER. Expected one of: azure_openai, ollama, gemini, deterministic, noop."
    )


class NoopSummarizer(Summarizer):
    @property
    def provider_name(self) -> str:
        return "noop"

    def _request_summary(self, prompt: str) -> str:
        raise NotImplementedError("NoopSummarizer does not use _request_summary")

    def summarize(self, item: NormalizedItem) -> SummaryRecord:
        metadata_markdown = build_metadata_markdown(item)
        return SummaryRecord(
            item_id=item.item_id or "",
            provider=self.provider_name,
            metadata_markdown=metadata_markdown,
            source_excerpt=truncate_text(item.abstract_or_body, limit=100000),
            short_summary="[AI Summary disabled for development]",
            generated_at=utc_now(),
        )


class AzureOpenAISummarizer(Summarizer):
    provider_name = "azure_openai"

    def __init__(self) -> None:
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "")
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
        missing = [
            name
            for name, value in {
                "AZURE_OPENAI_ENDPOINT": self.endpoint,
                "AZURE_OPENAI_API_KEY": self.api_key,
                "AZURE_OPENAI_API_VERSION": self.api_version,
                "AZURE_OPENAI_DEPLOYMENT": self.deployment,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing Azure OpenAI environment variables: {', '.join(missing)}")

    @property
    def provider_name(self) -> str:
        return "azure_openai"

    def _request_summary(self, prompt: str) -> str:
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?"
            + urlencode({"api-version": self.api_version})
        )
        body = json.dumps(self._build_request_payload(prompt)).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Azure OpenAI request failed with HTTP {exc.code}. Response body: {error_body}"
            ) from exc
        message = payload["choices"][0]["message"]["content"]
        return str(message).strip()

    def _build_request_payload(self, prompt: str) -> dict[str, object]:
        messages = [
            {
                "role": "system",
                "content": "Summarize only from the provided text. Keep it concise and factual.",
            },
            {"role": "user", "content": prompt},
        ]
        payload: dict[str, object] = {"messages": messages}
        if self._uses_gpt5_style_tokens():
            payload["max_completion_tokens"] = 1024
        else:
            payload["temperature"] = 0.2
            payload["max_tokens"] = 1024
        return payload

    def _uses_gpt5_style_tokens(self) -> bool:
        deployment = self.deployment.casefold()
        return deployment.startswith(("gpt-5", "o1", "o3", "o4"))


class OllamaSummarizer(Summarizer):
    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def full_provider_name(self) -> str:
        return f"{self.provider_name}:{self.model}"

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "").strip()
        self.timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
        missing = [name for name, value in {"OLLAMA_MODEL": self.model}.items() if not value]
        if missing:
            raise ValueError(f"Missing Ollama environment variables: {', '.join(missing)}")


    def _request_summary(self, prompt: str) -> str:
        body = json.dumps(self._build_request_payload(prompt)).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama request failed with HTTP {exc.code}. Response body: {error_body}") from exc
        except URLError as exc:
            raise RuntimeError(
                f"Ollama request failed. Confirm Ollama is running and reachable at {self.base_url}."
            ) from exc

        message = str(payload.get("response") or "").strip()
        if not message:
            raise RuntimeError(f"Ollama response did not include generated text. Payload: {payload}")
        return message

    def _build_request_payload(self, prompt: str) -> dict[str, object]:
        return {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 1024,
            },
        }


class GeminiSummarizer(Summarizer):
    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def full_provider_name(self) -> str:
        return f"{self.provider_name}:{self.model}"

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        if not self.api_key:
            raise ValueError("Missing Gemini environment variable: GEMINI_API_KEY")


    def _request_summary(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        body = json.dumps(self._build_request_payload(prompt)).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(5):
            try:
                with urlopen(request, timeout=45) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    break
            except HTTPError as exc:
                if exc.code == 429 and attempt < 4:
                    time.sleep(15 * (attempt + 1))
                    continue
                error_body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Gemini API request failed with HTTP {exc.code}. Response body: {error_body}") from exc
            except URLError as exc:
                raise RuntimeError("Gemini API request failed to connect.") from exc

        try:
            message = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
             raise RuntimeError(f"Unexpected response format from Gemini: {payload}") from exc
        return str(message).strip()

    def _build_request_payload(self, prompt: str) -> dict[str, object]:
        return {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {
                "role": "system",
                "parts": [{"text": "Summarize only from the provided text. Keep it concise and factual."}]
            },
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024,
            }
        }


class DeterministicSummarizer(Summarizer):
    @property
    def provider_name(self) -> str:
        return "deterministic"

    def _request_summary(self, prompt: str) -> str:
        raise NotImplementedError("DeterministicSummarizer does not use _request_summary")

    def summarize(self, item: NormalizedItem) -> SummaryRecord:
        metadata_markdown = build_metadata_markdown(item)
        excerpt = truncate_text(item.abstract_or_body, limit=10000)
        if excerpt:
            summary = (
                f"{item.title} is included in this week's digest for {', '.join(item.topic_ids)}. "
                f"The available text highlights: {truncate_text(excerpt, limit=240)}"
            )
        else:
            summary = "No abstract or body text was available, so this entry is reported from metadata only."
        return SummaryRecord(
            item_id=item.item_id or "",
            provider=self.provider_name,
            metadata_markdown=metadata_markdown,
            source_excerpt=excerpt,
            short_summary=summary,
            generated_at=utc_now(),
        )


def build_metadata_markdown(item: NormalizedItem) -> str:
    lines = [
        f"- Date: {item.published_at.isoformat() if item.published_at else 'Unknown'}",
        f"- Authors: {', '.join(item.authors_or_author) if item.authors_or_author else 'Unknown'}",
        f"- DOI: {item.doi or 'N/A'}",
        f"- Link: {item.url}",
    ]
    return "\n".join(lines)


def build_summary_prompt(item: NormalizedItem, excerpt: str) -> str:
    authors = ", ".join(item.authors_or_author) if item.authors_or_author else "Unknown authors"
    published_at = item.published_at.isoformat() if item.published_at else "Unknown date"
    return (
        "You are writing a precise weekly research digest.\n"
        "Use only the supplied title, authors, date, and abstract/body text.\n"
        "Do not invent results, methods, or claims beyond the text.\n"
        "Write 2 to 4 sentences in plain English. Do not include any introductory phrases like 'Here is a summary' or conversational filler. Start directly with the summary.\n\n"
        f"Title: {item.title}\n"
        f"Authors: {authors}\n"
        f"Published: {published_at}\n"
        f"Type: {item.item_type}\n"
        f"Abstract or body:\n{excerpt}\n"
    )


def _build_metadata_only_summary(
    item: NormalizedItem,
    metadata_markdown: str,
    provider_name: str,
) -> SummaryRecord:
    return SummaryRecord(
        item_id=item.item_id or "",
        provider=f"{provider_name}:fallback",
        metadata_markdown=metadata_markdown,
        source_excerpt=None,
        short_summary="No abstract or body text was available, so this entry is reported from metadata only.",
        generated_at=utc_now(),
    )
