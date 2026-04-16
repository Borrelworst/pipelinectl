from pipelinectl.output import _strip_timestamp


def test_strip_timestamp():
    line = "2026-04-16T10:00:00.1234567Z some log output"
    assert _strip_timestamp(line) == "some log output"


def test_strip_timestamp_with_space():
    line = "2026-04-16T10:00:00.000Z ##[section]Starting job"
    assert _strip_timestamp(line) == "##[section]Starting job"


def test_strip_timestamp_no_timestamp():
    line = "plain line without timestamp"
    assert _strip_timestamp(line) == "plain line without timestamp"


def test_strip_timestamp_empty():
    assert _strip_timestamp("") == ""
