"""
Purpose: Tests for the read-only live-config reads on S3StorageProvider —
lifecycle 404->empty and 403->unknown, intelligent-tiering pagination and
empty-list, and the headline invariant: the fetch path calls ONLY GET /
list methods, never a mutating Put/Delete (apply-ladder rung one).
Author(s): John Reed
"""

import pytest
from botocore.exceptions import ClientError

from tagmanager.storage.s3_provider import S3StorageProvider


class _RecordingClient:
    """A stub S3 client that records every method name it's asked for."""

    def __init__(self, lifecycle=None, tiering_pages=None, error=None):
        self.calls = []
        self._lifecycle = lifecycle
        self._tiering_pages = tiering_pages or [
            {"IntelligentTieringConfigurationList": [], "IsTruncated": False}]
        self._error = error
        self._page = 0

    def __getattr__(self, name):
        # Any attribute access is a would-be API call — record it, then
        # return a callable so a mutating call would still be logged.
        def _call(*_args, **_kwargs):
            self.calls.append(name)
            if self._error and name == self._error[0]:
                raise ClientError({"Error": {"Code": self._error[1]}}, name)
            if name == "get_bucket_lifecycle_configuration":
                return self._lifecycle
            if name == "list_bucket_intelligent_tiering_configurations":
                page = self._tiering_pages[self._page]
                self._page += 1
                return page
            return {}
        return _call


class _Session:
    def __init__(self, client):
        self._client = client

    def client(self, _name):
        return self._client


def _provider(client):
    return S3StorageProvider(session=_Session(client))


def _assert_read_only(client):
    """No mutating S3 call may ever appear in the recorded calls."""
    mutating = [c for c in client.calls
                if c.startswith(("put_", "delete_", "create_", "write_"))]
    assert not mutating, f"read-only violated: {mutating}"


def test_fetch_lifecycle_returns_rules():
    rules = [{"ID": "r1", "Status": "Enabled"}]
    client = _RecordingClient(lifecycle={"Rules": rules})
    result = _provider(client).fetch_lifecycle("bkt")
    assert result.present is True
    assert result.rules == rules
    _assert_read_only(client)


def test_fetch_lifecycle_404_is_absent_not_unknown():
    client = _RecordingClient(error=("get_bucket_lifecycle_configuration",
                                     "NoSuchLifecycleConfiguration"))
    result = _provider(client).fetch_lifecycle("bkt")
    assert result.present is False
    assert result.unknown is False
    assert result.rules == []
    _assert_read_only(client)


def test_fetch_lifecycle_403_is_unknown():
    client = _RecordingClient(error=("get_bucket_lifecycle_configuration",
                                     "AccessDenied"))
    result = _provider(client).fetch_lifecycle("bkt")
    assert result.unknown is True
    _assert_read_only(client)


def test_fetch_lifecycle_other_error_reraises():
    client = _RecordingClient(error=("get_bucket_lifecycle_configuration",
                                     "InternalError"))
    with pytest.raises(ClientError):
        _provider(client).fetch_lifecycle("bkt")


def test_fetch_tiering_empty_is_absent():
    client = _RecordingClient()
    result = _provider(client).fetch_tiering("bkt")
    assert result.present is False
    assert result.rules == []
    _assert_read_only(client)


def test_fetch_tiering_paginates():
    pages = [
        {"IntelligentTieringConfigurationList": [{"Id": "a"}],
         "IsTruncated": True, "NextContinuationToken": "t1"},
        {"IntelligentTieringConfigurationList": [{"Id": "b"}],
         "IsTruncated": False},
    ]
    client = _RecordingClient(tiering_pages=pages)
    result = _provider(client).fetch_tiering("bkt")
    assert [c["Id"] for c in result.rules] == ["a", "b"]
    assert result.present is True
    # two list calls, no mutation
    assert client.calls.count(
        "list_bucket_intelligent_tiering_configurations") == 2
    _assert_read_only(client)


def test_fetch_tiering_403_is_unknown():
    client = _RecordingClient(
        error=("list_bucket_intelligent_tiering_configurations",
               "AccessDenied"))
    result = _provider(client).fetch_tiering("bkt")
    assert result.unknown is True
    _assert_read_only(client)
