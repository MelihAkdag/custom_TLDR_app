from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tldr_feed.content_extraction import extract_abstract_from_html


class ContentExtractionTests(unittest.TestCase):
    def test_extracts_citation_abstract_meta(self) -> None:
        html = """
        <html>
          <head>
            <meta name="citation_abstract" content="This paper studies autonomous vessel routing with learned controllers." />
          </head>
        </html>
        """
        abstract = extract_abstract_from_html(html)
        self.assertEqual(abstract, "This paper studies autonomous vessel routing with learned controllers.")

    def test_extracts_marked_abstract_section(self) -> None:
        html = """
        <html>
          <body>
            <section class="paper-abstract">
              <p>We present a new method for safe maritime navigation under uncertainty.</p>
            </section>
          </body>
        </html>
        """
        abstract = extract_abstract_from_html(html)
        self.assertEqual(abstract, "We present a new method for safe maritime navigation under uncertainty.")
