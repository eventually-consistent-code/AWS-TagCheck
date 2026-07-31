"""
Purpose: Unit tests for the GCP provider (stubbed Asset Inventory client).
Author(s): John Reed
"""

from unittest import mock

from tagmanager.providers.gcp_provider import GcpProvider
from tagmanager.providers.base import ScopeConfig


def _asset(name, asset_type, labels, location="us-central1"):
    asset = mock.Mock()
    asset.name = name
    asset.asset_type = asset_type
    asset.resource.data = {"labels": labels, "name": name.rsplit("/", 1)[-1]}
    asset.resource.location = location
    return asset


def test_list_resources_normalizes_labels_to_tags():
    client = mock.Mock()
    client.list_assets.return_value = iter([
        _asset("//compute.googleapis.com/projects/p1/zones/z/instances/web1",
               "compute.googleapis.com/Instance", {"environment": "prod"})])
    provider = GcpProvider(client_builder=lambda scope: client)
    scope = ScopeConfig(cloud="gcp", scope_id="p1", credentials={})

    resources = list(provider.list_resources(scope))

    assert len(resources) == 1
    res = resources[0]
    assert res.tags == {"environment": "prod"}
    assert res.rtype == "compute.googleapis.com/Instance"
    assert res.region == "us-central1"
    kwargs = client.list_assets.call_args.kwargs
    assert kwargs["request"]["parent"] == "projects/p1"


def test_capabilities_read_only():
    provider = GcpProvider(client_builder=lambda scope: mock.Mock())
    assert provider.capabilities().supports_direct_write is False
