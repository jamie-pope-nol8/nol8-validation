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
raw_headers = [
    arguments[index + 1]
    for index, value in enumerate(arguments[:-1])
    if value == "-H"
]
# Resolve `-H @file` the way curl does, so the header the request actually
# carries is visible even when the token is kept out of argv (T2-3).
headers = []
for value in raw_headers:
    if value.startswith("@"):
        try:
            with open(value[1:], encoding="utf-8") as handle:
                headers.extend(line.rstrip("\n") for line in handle if line.strip())
        except OSError:
            pass
    else:
        headers.append(value)
token = os.environ.get("THEMIS_TOKEN", "")
capture = {
    "authorization_header": any(
        value.startswith("Authorization: Bearer ")
        and len(value) > len("Authorization: Bearer ")
        for value in headers
    ),
    # T2-3: the token must never be a command-line argument (ps-visible).
    "authorization_in_argv": any(
        str(value).startswith("Authorization: Bearer ") for value in arguments
    ),
    "token_in_argv": bool(token) and any(token in str(value) for value in arguments),
    "connect_timeout": "--connect-timeout" in arguments
        and arguments[arguments.index("--connect-timeout") + 1] == "5",
    "max_time": "--max-time" in arguments
        and arguments[arguments.index("--max-time") + 1] == "30",
    "insecure": "--insecure" in arguments,
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
                # T2-3: authenticated, but the token is not in the argv.
                "authorization_in_argv": False,
                "token_in_argv": False,
                "connect_timeout": True,
                "max_time": True,
                # config/demo.env sets THEMIS_ALLOW_INSECURE_TLS=1.
                "insecure": True,
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


    def test_token_is_never_passed_on_the_command_line(self) -> None:
        """T2-3: the bearer token must not appear in the process argument list.

        Passed as `-H "Authorization: Bearer $TOKEN"` it is readable via `ps` by
        any local user. Both transports now write it to a 0600 temp file read
        with `-H @file`, so it is never an argv element while staying
        authenticated.
        """
        policy_path = self.root / "policy.nol"
        policy_path.write_text('"x" -> "y";\n')
        invocations = (
            ([str(POLICY_SCRIPT), "themis", str(policy_path)], None),
            ([str(RUN_SCRIPT), "themis"], json.dumps({"message": "test"})),
        )

        for command, request_body in invocations:
            with self.subTest(script=command[0]):
                self.capture_path.unlink(missing_ok=True)
                result = subprocess.run(
                    command,
                    cwd=REPOSITORY_ROOT,
                    env=self.environment,
                    input=request_body,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                capture = self.capture()
                # Still authenticated (the header reaches curl via the file)...
                self.assertTrue(capture["authorization_header"])
                # ...but the token is not exposed on the command line.
                self.assertFalse(capture["authorization_in_argv"])
                self.assertFalse(capture["token_in_argv"])

    def test_caller_can_override_insecure_tls_from_the_config(self) -> None:
        """FW-5: a caller value wins over config/demo.env.

        demo.env sets THEMIS_ALLOW_INSECURE_TLS=1. Before the fix the transport
        sourced the config after the caller's environment, so setting the
        variable to 0 on the command line had no effect.
        """
        policy_path = self.root / "policy.nol"
        policy_path.write_text('"x" -> "y";\n')

        self.environment["THEMIS_ALLOW_INSECURE_TLS"] = "0"
        result = subprocess.run(
            [str(POLICY_SCRIPT), "themis", str(policy_path)],
            cwd=REPOSITORY_ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        # The caller disabled it, so --insecure must not be passed. On bash 3.2
        # this also exercises the empty-flag path that previously crashed.
        self.assertFalse(self.capture()["insecure"])


LIBRARY = REPOSITORY_ROOT / "scripts/lib/env-config.sh"


class EnvConfigLoaderTests(unittest.TestCase):
    """FW-4: config files are parsed, never executed."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _load(self, file_contents: str, allowed: str = "", *, preamble: str = "") -> subprocess.CompletedProcess:
        env_file = self.root / "sample.env"
        env_file.write_text(file_contents)
        script = (
            "set -euo pipefail\n"
            f"source {LIBRARY}\n"
            f"{preamble}"
            f"load_env_file {env_file} {allowed}\n"
            "for name in THEMIS_PROCESS_ENDPOINT THEMIS_ALLOW_INSECURE_TLS "
            "THEMIS_TOKEN EVIL LD_PRELOAD; do\n"
            # Direct indirect expansion - never eval, which would re-parse a
            # value containing $ or backticks and defeat the point of the test.
            "  printf '%s=[%s]\\n' \"$name\" \"${!name-UNSET}\"\n"
            "done\n"
        )
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_command_substitution_is_not_executed(self) -> None:
        sentinel = self.root / "PWNED"
        result = self._load(
            f'THEMIS_PROCESS_ENDPOINT="https://legit"\n'
            f"EVIL=$(touch {sentinel})\n"
            f"`touch {sentinel}`\n",
            allowed="THEMIS_PROCESS_ENDPOINT",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(sentinel.exists(), "config file was executed")
        self.assertIn("THEMIS_PROCESS_ENDPOINT=[https://legit]", result.stdout)
        self.assertIn("EVIL=[UNSET]", result.stdout)

    def test_allowlist_blocks_unexpected_keys(self) -> None:
        result = self._load(
            "THEMIS_PROCESS_ENDPOINT=https://legit\n"
            "LD_PRELOAD=/tmp/evil.so\n",
            allowed="THEMIS_PROCESS_ENDPOINT",
        )
        self.assertIn("LD_PRELOAD=[UNSET]", result.stdout)
        self.assertIn("unexpected key 'LD_PRELOAD'", result.stderr)

    def test_caller_environment_takes_precedence(self) -> None:
        result = self._load(
            "THEMIS_ALLOW_INSECURE_TLS=1\n",
            allowed="THEMIS_ALLOW_INSECURE_TLS",
            preamble="export THEMIS_ALLOW_INSECURE_TLS=0\n",
        )
        self.assertIn("THEMIS_ALLOW_INSECURE_TLS=[0]", result.stdout)

    def test_values_are_literal_not_expanded(self) -> None:
        # No allowlist: the secrets file accepts any key, but still no execution.
        result = self._load("THEMIS_TOKEN='ab$cd`e'\n")
        self.assertIn("THEMIS_TOKEN=[ab$cd`e]", result.stdout)


if __name__ == "__main__":
    unittest.main()
