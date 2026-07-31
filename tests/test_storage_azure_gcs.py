"""
Purpose: Tests for the Azure Blob and GCS storage providers (mock SDKs),
their pricing snapshots, and --backend CLI routing.
Author(s): John Reed
"""

import datetime
from types import SimpleNamespace
from unittest import mock

import pytest

from tagmanager.storage import cli
from tagmanager.storage.azure_provider import AzureBlobStorageProvider
from tagmanager.storage.base import StorageObject
from tagmanager.storage.gcs_provider import GcsStorageProvider
from tagmanager.storage.pricing import load_pricing

NOW = datetime.datetime(2026, 7, 31, tzinfo=datetime.timezone.utc)


def test_azure_provider_maps_blob_properties():
    """BlobProperties fields land on StorageObject; tier uppercased;
    last_accessed_on carried through."""
    blob = SimpleNamespace(name="logs/a.log", size=100,
                           last_modified=NOW - datetime.timedelta(days=100),
                           blob_tier="Cool",
                           last_accessed_on=NOW - datetime.timedelta(days=5))
    container_client = mock.Mock()
    container_client.list_blobs.return_value = iter([blob])
    service = mock.Mock()
    service.get_container_client.return_value = container_client

    objs = list(AzureBlobStorageProvider(
        "https://acct.blob.core.windows.net",
        service_client=service).list_objects("docs", prefix="logs/"))

    assert objs[0].backend == "azure"
    assert objs[0].storage_class == "COOL"
    assert objs[0].last_accessed == NOW - datetime.timedelta(days=5)
    container_client.list_blobs.assert_called_once_with(
        name_starts_with="logs/")


def test_azure_provider_defaults_missing_tier_to_hot():
    """Blobs with no tier report HOT."""
    blob = SimpleNamespace(name="x", size=1, last_modified=NOW,
                           blob_tier=None, last_accessed_on=None)
    container_client = mock.Mock()
    container_client.list_blobs.return_value = iter([blob])
    service = mock.Mock()
    service.get_container_client.return_value = container_client

    obj = next(AzureBlobStorageProvider(
        "u", service_client=service).list_objects("c"))
    assert obj.storage_class == "HOT"
    assert obj.last_accessed is None


def test_azure_capabilities_supports_last_access():
    caps = AzureBlobStorageProvider("u", service_client=mock.Mock()).capabilities()
    assert caps.supports_last_access is True


def test_gcs_provider_maps_blob_fields():
    """GCS Blob fields land on StorageObject; no last_accessed ever."""
    blob = SimpleNamespace(name="data/x.bin", size=50,
                           updated=NOW - datetime.timedelta(days=400),
                           storage_class="COLDLINE")
    client = mock.Mock()
    client.list_blobs.return_value = iter([blob])

    objs = list(GcsStorageProvider(client=client).list_objects("bkt"))

    assert objs[0].storage_class == "COLDLINE"
    assert objs[0].last_modified == NOW - datetime.timedelta(days=400)
    assert objs[0].last_accessed is None
    client.list_blobs.assert_called_once_with("bkt", prefix=None)


def test_gcs_capabilities_no_last_access():
    caps = GcsStorageProvider(client=mock.Mock()).capabilities()
    assert caps.supports_last_access is False


def test_pricing_snapshots_load():
    """Azure and GCS snapshots parse and answer rate questions."""
    azure = load_pricing(provider="azure")
    assert azure.flat_rate("COOL") == 0.01
    assert azure.min_duration_days("ARCHIVE") == 180

    gcs = load_pricing(provider="gcs")
    assert gcs.flat_rate("ARCHIVE") == 0.0014
    assert gcs.min_duration_days("ARCHIVE") == 365
    assert gcs.retrieval_per_gb("COLDLINE") == 0.02


def test_cli_backend_routing_azure_scan(tmp_path, monkeypatch, capsys):
    """--backend azure scan persists an azure run; cost report prices it
    with the azure snapshot."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "azure"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="azure", container=container,
                                key="old/x.dat", size_bytes=1024 ** 3,
                                last_modified=now - datetime.timedelta(days=400),
                                storage_class="COOL")

        def capabilities(self):
            raise NotImplementedError

    rc = cli.main(["--backend", "azure", "--bucket", "docs"],
                  provider=_Provider())
    assert rc == 0

    rc = cli.main(["--backend", "azure", "--cost-report"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "eastus" in out


def test_cli_azure_requires_account_url(tmp_path, monkeypatch):
    """azure backend without --account-url is a config error."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'x.db'}")
    assert cli.main(["--backend", "azure", "--bucket", "docs"]) == 4


def test_cli_backend_isolation(tmp_path, monkeypatch):
    """An s3 report-only run doesn't pick up the azure run."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "azure"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="azure", container=container,
                                key="k", size_bytes=10,
                                last_modified=now, storage_class="HOT")

        def capabilities(self):
            raise NotImplementedError

    assert cli.main(["--backend", "azure", "--bucket", "docs"],
                    provider=_Provider()) == 0
    # No s3 runs exist — s3 report-only must refuse, not price azure data.
    assert cli.main(["--cost-report"]) == 4


def test_missing_sdk_error_message():
    """Constructing the azure provider without the SDK names the packages."""
    with mock.patch.dict("sys.modules", {"azure": None, "azure.identity": None,
                                         "azure.storage.blob": None}):
        with pytest.raises(RuntimeError, match="azure-storage-blob"):
            AzureBlobStorageProvider("https://acct.blob.core.windows.net")