import json
import os

import pytest

from kosli_access.kosli import KosliClient, KosliError

from .fakes import FakeCompletedProcess, FakeRunner, trails_page


def client(runner, **kwargs):
    return KosliClient(
        binary="/opt/kosli",
        host="https://app.kosli.com",
        org="kosli",
        flow="infra-dev-instance-access",
        api_token="s3cret",
        runner=runner,
        **kwargs,
    )


def test_the_api_token_is_passed_in_the_environment_not_the_argument_list():
    runner = FakeRunner()

    client(runner).begin_trail("graham-2026-07-31-1234")

    call = runner.calls[0]
    assert "s3cret" not in call["command"]
    assert call["env"]["KOSLI_API_TOKEN"] == "s3cret"


def test_begin_trail_names_the_flow_org_and_host():
    runner = FakeRunner()

    client(runner).begin_trail("graham-2026-07-31-1234", description="why")

    assert runner.calls[0]["command"] == [
        "/opt/kosli",
        "begin",
        "trail",
        "graham-2026-07-31-1234",
        "--flow",
        "infra-dev-instance-access",
        "--description",
        "why",
        "--org",
        "kosli",
        "--host",
        "https://app.kosli.com",
    ]


def test_a_failing_cli_call_raises_rather_than_being_swallowed():
    runner = FakeRunner([FakeCompletedProcess(returncode=1, stderr="flow not found")])

    with pytest.raises(KosliError, match="flow not found"):
        client(runner).begin_trail("graham-2026-07-31-1234")


def test_list_trails_reads_the_data_key_and_follows_pagination():
    runner = FakeRunner(
        [
            FakeCompletedProcess(stdout=trails_page(["a", "b"], page=1, page_count=2)),
            FakeCompletedProcess(stdout=trails_page(["c"], page=2, page_count=2)),
        ]
    )

    trails = client(runner).list_trails()

    assert [t["name"] for t in trails] == ["a", "b", "c"]
    assert len(runner.calls) == 2


def test_list_trails_stops_at_the_page_cap_and_says_so(caplog):
    runner = FakeRunner(
        [FakeCompletedProcess(stdout=trails_page(["a"], page=n, page_count=9)) for n in range(1, 4)]
    )

    client(runner, max_pages=2).list_trails()

    assert len(runner.calls) == 2
    assert "older trails were not considered" in caplog.text


def test_list_trails_copes_with_a_flow_that_has_no_trails_yet():
    runner = FakeRunner([FakeCompletedProcess(stdout=json.dumps({"data": None}))])

    assert client(runner).list_trails() == []


def test_user_data_is_written_to_a_file_and_removed_afterwards():
    written = {}

    def runner(command, env=None, **kwargs):
        path = command[command.index("--user-data") + 1]
        with open(path) as handle:
            written["payload"] = json.load(handle)
        written["path"] = path
        return FakeCompletedProcess()

    client(runner).attest_generic(
        trail="graham-2026-07-31-1234",
        name="access-reason",
        user_data={"reason": "run the migration"},
    )

    assert written["payload"] == {"reason": "run the migration"}
    assert not os.path.exists(written["path"])


def test_attestations_can_be_reported_as_non_compliant_with_attachments():
    runner = FakeRunner()

    client(runner).attest_generic(
        trail="graham-2026-07-31-1234",
        name="terminal-session-log",
        attachments=["/tmp/session.log"],
        compliant=False,
    )

    command = runner.calls[0]["command"]
    assert "--compliant=false" in command
    assert command[command.index("--attachments") + 1] == "/tmp/session.log"


def test_annotations_become_repeated_key_value_flags():
    runner = FakeRunner()

    client(runner).attest_generic(
        trail="graham-2026-07-31-1234",
        name="elevated-aws-permissions",
        annotations={"requester": "graham@kosli.com", "approver": "faye@kosli.com"},
    )

    command = runner.calls[0]["command"]
    pairs = [command[i + 1] for i, arg in enumerate(command) if arg == "--annotate"]
    assert pairs == ["requester=graham@kosli.com", "approver=faye@kosli.com"]


def test_an_attestation_with_no_annotations_passes_no_flag_at_all():
    runner = FakeRunner()

    client(runner).attest_generic(
        trail="graham-2026-07-31-1234",
        name="access-reason",
        user_data={"reason": "run the migration"},
    )

    assert "--annotate" not in runner.calls[0]["command"]
