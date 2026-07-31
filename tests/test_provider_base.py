"""
Purpose: Unit tests for the provider base interface and normalized resource.
Author(s): John Reed
"""

import pytest

from tagmanager.providers.base import (
    NormalizedResource,
    Provider,
    ProviderCapabilities,
    ScopeConfig,
)


class _FakeProvider(Provider):
    cloud_name = "fake"

    def list_resources(self, scope):
        yield NormalizedResource(cloud="fake", scope_id=scope.scope_id,
                                 region="r1", rtype="thing", resource_id="x-1",
                                 name="one", tags={"k": "v"})

    def capabilities(self):
        return ProviderCapabilities(supports_direct_write=False)


def test_normalized_resource_fields():
    """Verify NormalizedResource stores tags and scope_id correctly."""
    scope = ScopeConfig(cloud="fake", scope_id="s1", credentials={})
    resources = list(_FakeProvider().list_resources(scope))
    assert resources[0].tags == {"k": "v"}
    assert resources[0].scope_id == "s1"


def test_provider_cannot_instantiate_abstract():
    """Verify Provider cannot be instantiated directly (abstract class)."""
    with pytest.raises(TypeError):
        Provider()  # pylint: disable=abstract-class-instantiated


def test_write_methods_reserved_for_sp2():
    """Verify apply_tags and export_changeset raise NotImplementedError."""
    provider = _FakeProvider()
    scope = ScopeConfig(cloud="fake", scope_id="s1", credentials={})
    with pytest.raises(NotImplementedError):
        provider.apply_tags(scope, "x-1", {"k": "v"})
    with pytest.raises(NotImplementedError):
        provider.export_changeset([])
