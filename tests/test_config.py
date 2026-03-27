from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tldr_feed.config import load_config, load_dotenv


class ConfigTests(unittest.TestCase):
    def test_load_dotenv_strips_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dotenv_path = Path(tmp_dir) / ".env"
            dotenv_path.write_text(
                '\n'.join(
                    [
                        'AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com/"',
                        "export AZURE_OPENAI_DEPLOYMENT='gpt-5.4'",
                    ]
                ),
                encoding="utf-8",
            )
            previous_endpoint = os.environ.pop("AZURE_OPENAI_ENDPOINT", None)
            previous_deployment = os.environ.pop("AZURE_OPENAI_DEPLOYMENT", None)
            try:
                load_dotenv(dotenv_path)
                self.assertEqual(os.environ["AZURE_OPENAI_ENDPOINT"], "https://example.openai.azure.com/")
                self.assertEqual(os.environ["AZURE_OPENAI_DEPLOYMENT"], "gpt-5.4")
            finally:
                os.environ.pop("AZURE_OPENAI_ENDPOINT", None)
                os.environ.pop("AZURE_OPENAI_DEPLOYMENT", None)
                if previous_endpoint is not None:
                    os.environ["AZURE_OPENAI_ENDPOINT"] = previous_endpoint
                if previous_deployment is not None:
                    os.environ["AZURE_OPENAI_DEPLOYMENT"] = previous_deployment

    def test_loads_example_style_yaml_without_pyyaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            (config_dir / "topics.yaml").write_text(
                """
topics:
  - topic_id: "ai_research"
    display_name: "AI Research"
    keywords: ["edge ai", "tinyml"]
    include_terms: ["deployment"]
    exclude_terms: ["job posting"]
    sources: ["arxiv", "openalex", "linkedin_import"]
""".strip(),
                encoding="utf-8",
            )
            (config_dir / "sources.yaml").write_text(
                """
sources:
  arxiv:
    enabled: true
    max_results: 10
  linkedin_import:
    enabled: true
    import_dir: "imports/linkedin"
""".strip(),
                encoding="utf-8",
            )

            config = load_config(config_dir)

        self.assertEqual(len(config.topics), 1)
        self.assertEqual(config.topics[0].topic_id, "ai_research")
        self.assertEqual(config.topics[0].keywords, ["edge ai", "tinyml"])
        self.assertEqual(config.topics[0].min_relevance_score, 2.0)
        self.assertEqual(config.topics[0].allowed_paper_languages, [])
        self.assertEqual(config.sources["arxiv"].max_results, 10)
        self.assertEqual(config.sources["linkedin_import"].extra["import_dir"], "imports/linkedin")

    def test_topic_allowed_paper_languages_are_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            (config_dir / "topics.yaml").write_text(
                """
topics:
  - topic_id: "ship_autonomy"
    display_name: "Ship Autonomy"
    keywords: ["autonomous ship"]
    allowed_paper_languages: ["en", "eng"]
    sources: ["openalex"]
""".strip(),
                encoding="utf-8",
            )
            (config_dir / "sources.yaml").write_text("sources: {}", encoding="utf-8")

            config = load_config(config_dir)

        self.assertEqual(config.topics[0].allowed_paper_languages, ["en", "eng"])

    def test_duplicate_topic_ids_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            (config_dir / "topics.yaml").write_text(
                """
topics:
  - topic_id: "dup"
    display_name: "One"
    keywords: ["a"]
    sources: ["arxiv"]
  - topic_id: "dup"
    display_name: "Two"
    keywords: ["b"]
    sources: ["openalex"]
""".strip(),
                encoding="utf-8",
            )
            (config_dir / "sources.yaml").write_text("sources: {}", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(config_dir)
