from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
POLICY_SCRIPT = REPOSITORY_ROOT / "scripts/load-policy.sh"
RUN_SCRIPT = REPOSITORY_ROOT / "scripts/run-validation.sh"


FAKE_CURL = r'''#!/usr/bin/env python3
import json
import os
import sys

arguments = sys.argv[1:]
headers = [
    arguments[index + 1]
    for index, value in enumerate(arguments[:-1])
    if value == "-H"
]
capture = {
    "authorization_header": any(
        value.startswith("Authorization: Bearer ")
        and len(value) > len("Authorization: Bearer ")
        for value in headers
    ),
    "connect_timeout": "--connect-timeout" in arguments
        and arguments[arguments.index("--connect-timeout") + 1] == "5",
    "max_time": "--max-time" in arguments
        and arguments[arguments.index("--max-time") + 1] == "30",
}
with open(os.environ["TRANSPORT_CAPTURE"], "w", encoding="utf-8") as handle:
    json.dump(capture, handle)

mode = os.environ.get("FAKE_CURL_MODE")
if mode == "timeout":
    raise SystemExit(28)

output_path = arguments[arguments.index("-o") + 1]
is_policy = "-X" in arguments
if mode == "service_error":
    response = {
        "error": "temporarily_unavailable",
        "message": "processing service unavailable",
        "status": 503,
        "detail": {"retryable": True, "authorization": "must-not-persist"},
        "token": "must-not-persist",
        "unrelated": "must-not-persist",
    }
elif is_policy:
    response = {"ok": True, "command_id": "cmd-test", "stage": "apollo", "rules": 1}
else:
    response = {"result": {"message": "processed"}}
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(response, handle)

write_format = arguments[arguments.index("-w") + 1]
http_status = "503" if mode == "service_error" else "200"
sys.stdout.write(
    f"{http_status} 0.0069" if "time_total" in write_format else http_status
)
'''


class TransportScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.bin_directory = self.root / "bin"
        self.bin_directory.mkdir()
        fake_curl = self.bin_directory / "curl"
        fake_curl.write_text(FAKE_CURL)
        fake_curl.chmod(0o755)
        self.capture_path = self.root / "capture.json"
        self.environment = os.environ.copy()
        self.environment["PATH"] = (
            str(self.bin_directory) + os.pathsep + self.environment["PATH"]
        )
        self.environment["TRANSPORT_CAPTURE"] = str(self.capture_path)
        self.environment["THEMIS_TOKEN"] = "test-token"

    def capture(self) -> dict:
        return json.loads(self.capture_path.read_text())

    def test_policy_transport_authenticates_and_uses_bounded_curl(self) -> None:
        policy_path = self.root / "policy.nol"
        policy_path.write_text('"x" -> "y";\n')

        result = subprocess.run(
            [str(POLICY_SCRIPT), "themis", str(policy_path)],
            cwd=REPOSITORY_ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["http_status"], 200)
        self.assertEqual(
            self.capture(),
            {
                "authorization_header": True,
                "connect_timeout": True,
                "max_time": True,
            },
        )

    def test_run_transport_preserves_success_contract_with_authentication(self) -> None:
        result = subprocess.run(
            [str(RUN_SCRIPT), "themis"],
            cwd=REPOSITORY_ROOT,
            env=self.environment,
            input=json.dumps({"message": "test"}),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response["http_status"], 200)
        self.assertAlmostEqual(response["latency_ms"], 6.9)
        self.assertEqual(response["response"], {"message": "processed"})
        self.assertTrue(self.capture()["authorization_header"])

    def test_run_transport_retains_sanitized_error_response_body(self) -> None:
        self.environment["FAKE_CURL_MODE"] = "service_error"
        result = subprocess.run(
            [str(RUN_SCRIPT), "themis"],
            cwd=REPOSITORY_ROOT,
            env=self.environment,
            input=json.dumps({"message": "test"}),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 6)
        evidence = json.loads(result.stdout)
        self.assertEqual(evidence["http_status"], 503)
        self.assertEqual(
            evidence["response"],
            {
                "error": "temporarily_unavailable",
                "message": "processing service unavailable",
                "status": 503,
                "detail": {"retryable": True},
            },
        )
        serialized = json.dumps(evidence).lower()
        self.assertNotIn("must-not-persist", serialized)
        self.assertNotIn("authorization", serialized)
        self.assertNotIn("token", serialized)

    def test_both_transports_preserve_network_failure_semantics(self) -> None:
        self.environment["FAKE_CURL_MODE"] = "timeout"
        policy_path = self.root / "policy.nol"
        policy_path.write_text('"x" -> "y";\n')
        invocations = (
            ([str(POLICY_SCRIPT), "themis", str(policy_path)], None),
            ([str(RUN_SCRIPT), "themis"], json.dumps({"message": "test"})),
        )

        for command, request_body in invocations:
            with self.subTest(script=command[0]):
                result = subprocess.run(
                    command,
                    cwd=REPOSITORY_ROOT,
                    env=self.environment,
                    input=request_body,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 5)
                capture = self.capture()
                self.assertTrue(capture["connect_timeout"])
                self.assertTrue(capture["max_time"])
                self.assertTrue(capture["authorization_header"])


if __name__ == "__main__":
    unittest.main()
