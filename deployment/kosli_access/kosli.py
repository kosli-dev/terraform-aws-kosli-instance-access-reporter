"""A thin wrapper around the Kosli CLI, which ships as a lambda layer at /opt.

The API token is passed through the subprocess environment rather than on the
command line, so it never appears in an argument list or a log line.
"""

import json
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class KosliError(RuntimeError):
    """A Kosli CLI invocation failed."""


class KosliClient:
    """Begins trails and reports attestations for a single flow."""

    def __init__(
        self,
        binary,
        host,
        org,
        flow,
        api_token,
        page_limit=30,
        max_pages=3,
        runner=subprocess.run,
    ):
        self._binary = binary
        self._host = host
        self._org = org
        self._flow = flow
        self._api_token = api_token
        self._page_limit = page_limit
        self._max_pages = max_pages
        self._runner = runner

    @property
    def flow(self):
        return self._flow

    def _run(self, args):
        command = [self._binary] + args + ["--org", self._org, "--host", self._host]
        env = os.environ.copy()
        env["KOSLI_API_TOKEN"] = self._api_token
        logger.info("Running kosli %s", " ".join(args))
        result = self._runner(
            command,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stderr:
            logger.info("kosli stderr: %s", result.stderr.strip())
        if result.returncode != 0:
            raise KosliError(
                f"`kosli {' '.join(args)}` exited {result.returncode}: "
                f"{(result.stderr or result.stdout or '').strip()}"
            )
        return result.stdout or ""

    def list_trails(self):
        """Return the most recent trails in the flow, newest first.

        Results are ordered by ``created_at`` descending, *not* by name, so
        callers must scan the whole result rather than stopping early at the
        first name older than the window they care about.
        """
        trails = []
        page = 1
        while page <= self._max_pages:
            output = self._run(
                [
                    "list",
                    "trails",
                    "--flow",
                    self._flow,
                    "--output",
                    "json",
                    "--page-limit",
                    str(self._page_limit),
                    "--page",
                    str(page),
                ]
            )
            payload = json.loads(output or "{}") or {}
            trails.extend(payload.get("data") or [])
            page_count = (payload.get("pagination") or {}).get("page_count") or 1
            if page >= page_count:
                break
            page += 1
        else:
            logger.warning(
                "Stopped listing trails in flow %s after %d pages of %d; "
                "older trails were not considered for the rendezvous window",
                self._flow,
                self._max_pages,
                self._page_limit,
            )
        return trails

    def begin_trail(self, name, description=None):
        args = ["begin", "trail", name, "--flow", self._flow]
        if description:
            args += ["--description", description]
        self._run(args)
        return name

    def attest_generic(
        self,
        trail,
        name,
        user_data=None,
        attachments=None,
        compliant=True,
        description=None,
    ):
        """Report a generic attestation against ``trail``."""
        args = [
            "attest",
            "generic",
            "--name",
            name,
            "--flow",
            self._flow,
            "--trail",
            trail,
            "--compliant={}".format("true" if compliant else "false"),
        ]
        if description:
            args += ["--description", description]
        for attachment in attachments or []:
            args += ["--attachments", attachment]

        if user_data is None:
            self._run(args)
            return

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir="/tmp", delete=False
        ) as handle:
            json.dump(user_data, handle, default=str, indent=2)
            user_data_path = handle.name
        try:
            self._run(args + ["--user-data", user_data_path])
        finally:
            os.unlink(user_data_path)
