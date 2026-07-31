"""
Purpose: Unit tests for the Azure provider (stubbed Resource Graph client).
Author(s): John Reed
"""

from unittest import mock

from tagmanager.providers.azure_provider import AzureProvider
from tagmanager.providers.base import ScopeConfig


def _response(rows, skip_token=None):
    """Create a mock response object."""
    resp = mock.Mock()
    resp.data = rows
    resp.skip_token = skip_token
    return resp


def test_list_resources_pages_and_normalizes():
    """
    Verify list_resources pages through results and normalizes to standard format.
    """
    client = mock.Mock()
    client.resources.side_effect = [
        _response([{"id": "/subscriptions/s1/rg/vm1", "name": "vm1",
                    "type": "microsoft.compute/virtualmachines",
                    "location": "eastus", "tags": {"Environment": "Prod"},
                    "subscriptionId": "s1"}], skip_token="next"),
        _response([{"id": "/subscriptions/s1/rg/sa1", "name": "sa1",
                    "type": "microsoft.storage/storageaccounts",
                    "location": "eastus", "tags": None, "subscriptionId": "s1"}]),
    ]
    provider = AzureProvider(client_builder=lambda scope: client)
    scope = ScopeConfig(cloud="azure", scope_id="s1", credentials={})

    resources = list(provider.list_resources(scope))

    assert len(resources) == 2
    assert resources[0].rtype == "microsoft.compute/virtualmachines"
    assert resources[0].tags == {"Environment": "Prod"}
    assert resources[1].tags == {}
    assert client.resources.call_count == 2
    # Verify the QueryRequest is called with correct subscriptions and QUERY
    call_args_list = client.resources.call_args_list
    for call in call_args_list:
        query_request = call[0][0]  # First positional arg is the QueryRequest
        assert query_request.subscriptions == ["s1"]
        assert query_request.query == "Resources | project id, name, type, location, tags, subscriptionId"


def test_capabilities_direct_write():
    """
    Verify Azure provider supports direct tag writes.
    """
    provider = AzureProvider(client_builder=lambda scope: mock.Mock())
    assert provider.capabilities().supports_direct_write is True
