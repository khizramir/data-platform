import pytest

from data_platform.core.plugin_registry import PluginRegistry, PluginRegistryError
from conftest import DummyPlugin, AnotherPlugin


class TestPluginRegistryRegistration:
    def test_register_valid_plugin(self, registry):
        registry.register(DummyPlugin)
        assert registry.is_registered("dummy")

    def test_register_sets_length(self, registry):
        assert len(registry) == 0
        registry.register(DummyPlugin)
        assert len(registry) == 1

    def test_register_duplicate_raises(self, registry):
        registry.register(DummyPlugin)
        with pytest.raises(PluginRegistryError, match="already registered"):
            registry.register(DummyPlugin)

    def test_register_non_plugin_raises_type_error(self, registry):
        class NotAPlugin:
            pass
        with pytest.raises(TypeError):
            registry.register(NotAPlugin)  # type: ignore[arg-type]

    def test_register_base_class_itself_raises(self, registry):
        from data_platform.core.base_plugin import DataSourcePlugin
        with pytest.raises(TypeError):
            registry.register(DataSourcePlugin)  # type: ignore[arg-type]

    def test_register_multiple_plugins(self, registry):
        registry.register(DummyPlugin)
        registry.register(AnotherPlugin)
        assert len(registry) == 2


class TestPluginRegistryLookup:
    def test_get_returns_plugin_class(self, registry_with_dummy):
        assert registry_with_dummy.get("dummy") is DummyPlugin

    def test_get_unknown_raises(self, registry):
        with pytest.raises(PluginRegistryError, match="not registered"):
            registry.get("nonexistent")

    def test_is_registered_true(self, registry_with_dummy):
        assert registry_with_dummy.is_registered("dummy") is True

    def test_is_registered_false(self, registry):
        assert registry.is_registered("dummy") is False

    def test_list_plugins_empty(self, registry):
        assert registry.list_plugins() == []

    def test_list_plugins_sorted(self, registry):
        registry.register(AnotherPlugin)
        registry.register(DummyPlugin)
        assert registry.list_plugins() == ["another", "dummy"]


class TestPluginRegistryUnregister:
    def test_unregister_removes_plugin(self, registry_with_dummy):
        registry_with_dummy.unregister("dummy")
        assert not registry_with_dummy.is_registered("dummy")

    def test_unregister_unknown_raises(self, registry):
        with pytest.raises(PluginRegistryError, match="not registered"):
            registry.unregister("nonexistent")

    def test_can_re_register_after_unregister(self, registry_with_dummy):
        registry_with_dummy.unregister("dummy")
        registry_with_dummy.register(DummyPlugin)
        assert registry_with_dummy.is_registered("dummy")
