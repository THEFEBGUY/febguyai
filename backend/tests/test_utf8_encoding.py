import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import UTF8JSONResponse, encode_json, iter_utf8_response_lines


TEST_TEXT = "“Hello” — here are emojis: 🤖 🚀 🔥 ✅ 🎉"


class FakeUtf8StreamResponse:
    def iter_lines(self, decode_unicode=False):
        yield TEST_TEXT.encode("utf-8")


class Utf8EncodingTests(unittest.TestCase):
    def test_json_response_preserves_utf8_text(self):
        response = UTF8JSONResponse({"text": TEST_TEXT})
        payload = json.loads(response.body.decode("utf-8"))
        self.assertEqual(payload["text"], TEST_TEXT)

    def test_storage_json_preserves_utf8_text(self):
        payload = encode_json({"text": TEST_TEXT})
        self.assertIn(TEST_TEXT, payload)
        self.assertEqual(json.loads(payload)["text"], TEST_TEXT)

    def test_stream_line_decoder_preserves_utf8_text(self):
        lines = list(iter_utf8_response_lines(FakeUtf8StreamResponse()))
        self.assertEqual(lines, [TEST_TEXT])


if __name__ == "__main__":
    unittest.main()
