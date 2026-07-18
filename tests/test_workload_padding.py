from __future__ import annotations

import json
import random
import time
import unittest
from html.parser import HTMLParser
from xml.etree.ElementTree import fromstring

from framework.workload.generate_workload import _pad_document


class _BalancedHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {"meta"}:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack.pop() != tag:
            raise AssertionError(f"Unbalanced HTML closing tag: {tag}")


class WorkloadPaddingTests(unittest.TestCase):
    def test_near_limit_padding_completes_promptly(self) -> None:
        started = time.perf_counter()
        result = _pad_document(
            content="original\n",
            target_size=973_380,
            format_name="log",
            random_source=random.Random(42),
        )
        elapsed = time.perf_counter() - started

        self.assertEqual(len(result.encode("utf-8")), 973_380)
        self.assertLess(elapsed, 2.0)

    def test_padding_is_deterministic_for_same_seed(self) -> None:
        first = _pad_document(
            content="original\n",
            target_size=100_000,
            format_name="text",
            random_source=random.Random(17),
        )
        second = _pad_document(
            content="original\n",
            target_size=100_000,
            format_name="text",
            random_source=random.Random(17),
        )
        self.assertEqual(first, second)

    def test_json_padding_preserves_valid_structure(self) -> None:
        original = json.dumps({"message": "original"}, indent=2) + "\n"
        result = _pad_document(
            content=original,
            target_size=100_000,
            format_name="json",
            random_source=random.Random(1),
        )
        parsed = json.loads(result)
        self.assertEqual(parsed["message"], "original")
        self.assertIn("_synthetic_padding", parsed)
        self.assertLessEqual(len(result.encode("utf-8")), 100_000)

    def test_xml_padding_preserves_valid_structure(self) -> None:
        original = "<enterprise_record><message>original</message></enterprise_record>\n"
        result = _pad_document(
            content=original,
            target_size=100_000,
            format_name="xml",
            random_source=random.Random(2),
        )
        parsed = fromstring(result)
        self.assertEqual(parsed.findtext("message"), "original")
        self.assertIsNotNone(parsed.find("synthetic_padding"))
        self.assertLessEqual(len(result.encode("utf-8")), 100_000)

    def test_html_padding_preserves_valid_structure(self) -> None:
        original = "<html><body><p>original</p></body></html>\n"
        result = _pad_document(
            content=original,
            target_size=100_000,
            format_name="html",
            random_source=random.Random(3),
        )
        parser = _BalancedHtmlParser()
        parser.feed(result)
        self.assertEqual(parser.stack, [])
        self.assertIn("<p>original</p>", result)
        self.assertIn("<pre>", result)
        self.assertLessEqual(len(result.encode("utf-8")), 100_000)

    def test_plain_formats_preserve_original_and_trim_only_filler(self) -> None:
        for format_name in ("text", "log", "email", "csv"):
            with self.subTest(format_name=format_name):
                original = f"original {format_name} content\n"
                result = _pad_document(
                    content=original,
                    target_size=10_000,
                    format_name=format_name,
                    random_source=random.Random(4),
                )
                self.assertTrue(result.startswith(original))
                self.assertEqual(len(result.encode("utf-8")), 10_000)

    def test_content_larger_than_target_is_returned_unchanged(self) -> None:
        original = '{"message":"original content"}\n'
        result = _pad_document(
            content=original,
            target_size=10,
            format_name="json",
            random_source=random.Random(5),
        )
        self.assertEqual(result, original)
        self.assertEqual(json.loads(result)["message"], "original content")

    def test_negative_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            _pad_document(
                content="original",
                target_size=-1,
                format_name="text",
                random_source=random.Random(6),
            )


if __name__ == "__main__":
    unittest.main()
