from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

from .models import AppConfig, SourceSettings, TopicProfile


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        normalized_key = key.strip()
        if normalized_key.startswith("export "):
            normalized_key = normalized_key[len("export ") :].strip()
        normalized_value = value.strip()
        if len(normalized_value) >= 2 and normalized_value[0] == normalized_value[-1] and normalized_value[0] in {'"', "'"}:
            normalized_value = normalized_value[1:-1]
        os.environ.setdefault(normalized_key, normalized_value)


def _load_yaml(text: str) -> Any:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ModuleNotFoundError:
        return _parse_minimal_yaml(text)


def _parse_minimal_yaml(text: str) -> Any:
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, stripped))

    if not lines:
        return {}

    value, index = _parse_block(lines, 0, 0)
    if index != len(lines):
        raise ValueError("Could not parse the full YAML document.")
    return value


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    current_indent, current_text = lines[index]
    if current_indent != indent:
        raise ValueError(f"Unexpected indentation at line: {current_text}")
    if current_text.startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_dict(lines, index, indent)


def _parse_dict(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, current_text = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent:
            raise ValueError(f"Unexpected indentation at line: {current_text}")
        if current_text.startswith("- "):
            break
        if ":" not in current_text:
            raise ValueError(f"Expected key/value line, got: {current_text}")
        key, remainder = current_text.split(":", maxsplit=1)
        key = key.strip()
        remainder = remainder.strip()
        index += 1
        if remainder:
            result[key] = _parse_scalar(remainder)
            continue
        if index < len(lines) and lines[index][0] > indent:
            nested_indent = lines[index][0]
            nested_value, index = _parse_block(lines, index, nested_indent)
            result[key] = nested_value
        else:
            result[key] = None
    return result, index


def _parse_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, current_text = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or not current_text.startswith("- "):
            break
        remainder = current_text[2:].strip()
        index += 1
        if not remainder:
            if index < len(lines) and lines[index][0] > indent:
                nested_indent = lines[index][0]
                nested_value, index = _parse_block(lines, index, nested_indent)
                result.append(nested_value)
            else:
                result.append(None)
            continue
        if ":" in remainder and not remainder.startswith(("'", '"', "[")):
            item, index = _parse_inline_mapping_item(lines, index, indent, remainder)
            result.append(item)
            continue
        result.append(_parse_scalar(remainder))
    return result, index


def _parse_inline_mapping_item(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
    remainder: str,
) -> tuple[dict[str, Any], int]:
    key, raw_value = remainder.split(":", maxsplit=1)
    item: dict[str, Any] = {}
    key = key.strip()
    raw_value = raw_value.strip()
    if raw_value:
        item[key] = _parse_scalar(raw_value)
    elif index < len(lines) and lines[index][0] > indent:
        nested_indent = lines[index][0]
        nested_value, index = _parse_block(lines, index, nested_indent)
        item[key] = nested_value
    else:
        item[key] = None

    continuation_indent = indent + 2
    while index < len(lines):
        current_indent, current_text = lines[index]
        if current_indent < continuation_indent:
            break
        if current_indent != continuation_indent or current_text.startswith("- "):
            break
        if ":" not in current_text:
            raise ValueError(f"Expected mapping entry, got: {current_text}")
        next_key, next_value = current_text.split(":", maxsplit=1)
        next_key = next_key.strip()
        next_value = next_value.strip()
        index += 1
        if next_value:
            item[next_key] = _parse_scalar(next_value)
            continue
        if index < len(lines) and lines[index][0] > continuation_indent:
            nested_indent = lines[index][0]
            nested_value, index = _parse_block(lines, index, nested_indent)
            item[next_key] = nested_value
        else:
            item[next_key] = None
    return item, index


def _parse_scalar(value: str) -> Any:
    lowered = value.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if value.startswith(("'", '"', "[", "{")):
        return ast.literal_eval(value)
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def load_config(config_dir: str | Path = "config") -> AppConfig:
    config_path = Path(config_dir)
    topics_path = _resolve_config_path(config_path, "topics")
    sources_path = _resolve_config_path(config_path, "sources")

    topics_payload = _load_yaml(topics_path.read_text(encoding="utf-8")) or {}
    sources_payload = _load_yaml(sources_path.read_text(encoding="utf-8")) or {}

    topics = _build_topics(topics_payload.get("topics", []))
    sources = _build_sources(sources_payload.get("sources", {}))
    return AppConfig(topics=topics, sources=sources, config_dir=str(config_path))


def _resolve_config_path(config_dir: Path, stem: str) -> Path:
    primary = config_dir / f"{stem}.yaml"
    if primary.exists():
        return primary
    example = config_dir / f"{stem}.example.yaml"
    if example.exists():
        return example
    raise FileNotFoundError(f"Could not find {primary} or {example}")


def _build_topics(raw_topics: list[dict[str, Any]]) -> list[TopicProfile]:
    topics: list[TopicProfile] = []
    seen_ids: set[str] = set()
    for entry in raw_topics:
        topic_id = str(entry["topic_id"]).strip()
        if topic_id in seen_ids:
            raise ValueError(f"Duplicate topic_id: {topic_id}")
        seen_ids.add(topic_id)
        keywords = [str(keyword).strip() for keyword in entry.get("keywords", []) if str(keyword).strip()]
        if not keywords:
            raise ValueError(f"Topic {topic_id} must define at least one keyword.")
        topics.append(
            TopicProfile(
                topic_id=topic_id,
                display_name=str(entry.get("display_name") or entry.get("name") or topic_id),
                keywords=keywords,
                include_terms=[str(value).strip() for value in entry.get("include_terms", []) if str(value).strip()],
                exclude_terms=[str(value).strip() for value in entry.get("exclude_terms", []) if str(value).strip()],
                sources=[str(value).strip() for value in entry.get("sources", []) if str(value).strip()],
                min_relevance_score=float(entry.get("min_relevance_score", 2.0)),
            )
        )
    return topics


def _build_sources(raw_sources: dict[str, dict[str, Any]]) -> dict[str, SourceSettings]:
    built: dict[str, SourceSettings] = {}
    for name, payload in raw_sources.items():
        payload = payload or {}
        extra = {
            key: value
            for key, value in payload.items()
            if key not in {"enabled", "base_url", "timeout_seconds", "max_results", "user_agent"}
        }
        built[name] = SourceSettings(
            name=name,
            enabled=bool(payload.get("enabled", True)),
            base_url=payload.get("base_url"),
            timeout_seconds=int(payload.get("timeout_seconds", 20)),
            max_results=int(payload.get("max_results", 20)),
            user_agent=str(payload.get("user_agent", "tldr-feed/0.1")),
            extra=extra,
        )
    return built
