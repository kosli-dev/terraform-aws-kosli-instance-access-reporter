from kosli_access import reason

from .fakes import REAL_COMMAND


def test_extracts_the_reason_from_a_real_captured_command():
    result = reason.extract_access_reason(REAL_COMMAND)

    assert result["status"] == reason.PARSED
    assert result["reason"] == "Testing of cloudtrail messages"
    assert result["operator_login"] == "graham"
    assert reason.is_compliant(result)


def test_tolerates_arbitrary_whitespace_runs():
    command = (
        "/bin/bash -c 'echo XXXXXXXX Access reason XXXXXXXX;"
        "\t\n     echo    run the migration;   \n  echo User: graham; bash'"
    )

    assert reason.extract_access_reason(command)["reason"] == "run the migration"


def test_a_semicolon_in_the_reason_does_not_truncate_it():
    # ${REASON} is interpolated unquoted, so a semicolon lands inside the
    # extracted region. Taking everything between the markers recovers the
    # whole reason as typed; splitting on ';' would silently lose half of it.
    command = (
        "/bin/bash -c 'echo XXXXXXXX Access reason XXXXXXXX;"
        " echo restart the worker; then verify;"
        " echo User: graham; bash'"
    )

    result = reason.extract_access_reason(command)

    assert result["status"] == reason.PARSED
    assert result["reason"] == "restart the worker; then verify"


def test_a_bypassed_wrapper_script_is_reported_as_absent_not_omitted():
    result = reason.extract_access_reason("/bin/bash")

    assert result["status"] == reason.ABSENT
    assert result["reason"] is None
    assert "bypassed" in result["note"]
    assert not reason.is_compliant(result)


def test_changed_wrapper_markers_are_reported_as_unparseable():
    # Distinct from absent: the wrapper was used, but this pipeline could not
    # read its output. Reporting "no reason" would say something very
    # different to an auditor.
    command = "/bin/bash -c 'echo Access reason: run the migration; bash'"

    result = reason.extract_access_reason(command)

    assert result["status"] == reason.UNPARSEABLE
    assert result["reason"] is None
    assert not reason.is_compliant(result)


def test_an_empty_reason_between_the_markers_is_unparseable():
    command = (
        "/bin/bash -c 'echo XXXXXXXX Access reason XXXXXXXX;  echo User: graham'"
    )

    assert reason.extract_access_reason(command)["status"] == reason.UNPARSEABLE


def test_a_missing_command_is_reported_rather_than_crashing():
    result = reason.extract_access_reason(None)

    assert result["status"] == reason.NO_COMMAND
    assert result["reason"] is None
