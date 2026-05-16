import pytest

from data_platform.core.plugin_manager import PluginManager, PluginManagerError
from data_platform.core.plugin_registry import PluginRegistryError
from conftest import DummyPlugin, AnotherPlugin

DUMMY_CONFIG = {"dsn": "dummy://localhost"}


class TestPluginManagerRegistration:
    def test_register_plugin(self, manager):
        manager.register_plugin(DummyPlugin)
        assert manager.registry.is_registered("dummy")

    def test_uses_provided_registry(self):
        from data_platform.core.plugin_registry import PluginRegistry
        r = PluginRegistry()
        r.register(DummyPlugin)
        assert PluginManager(registry=r).registry.is_registered("dummy")


class TestPluginManagerLoad:
    def test_load_plugin_connects(self, manager_with_dummy):
        assert manager_with_dummy.load_plugin("dummy", DUMMY_CONFIG).is_connected()

    def test_load_plugin_adds_to_loaded(self, manager_with_dummy):
        manager_with_dummy.load_plugin("dummy", DUMMY_CONFIG)
        assert "dummy" in manager_with_dummy.list_loaded()

    def test_load_unknown_plugin_raises(self, manager):
        with pytest.raises(PluginRegistryError):
            manager.load_plugin("nonexistent", {})

    def test_load_already_loaded_raises(self, manager_with_dummy):
        manager_with_dummy.load_plugin("dummy", DUMMY_CONFIG)
        with pytest.raises(PluginManagerError, match="already loaded"):
            manager_with_dummy.load_plugin("dummy", DUMMY_CONFIG)

    def test_load_invalid_config_raises(self, manager_with_dummy):
        with pytest.raises(ValueError):
            manager_with_dummy.load_plugin("dummy", {})


class TestPluginManagerUnload:
    def test_unload_disconnects_plugin(self, manager_with_dummy):
        plugin = manager_with_dummy.load_plugin("dummy", DUMMY_CONFIG)
        manager_with_dummy.unload_plugin("dummy")
        assert not plugin.is_connected()

    def test_unload_removes_from_loaded(self, manager_with_dummy):
        manager_with_dummy.load_plugin("dummy", DUMMY_CONFIG)
        manager_with_dummy.unload_plugin("dummy")
        assert "dummy" not in manager_with_dummy.list_loaded()

    def test_unload_not_loaded_raises(self, manager):
        with pytest.raises(PluginManagerError, match="not loaded"):
            manager.unload_plugin("dummy")

    def test_unload_all(self, manager):
        manager.register_plugin(DummyPlugin)
        manager.register_plugin(AnotherPlugin)
        manager.load_plugin("dummy", DUMMY_CONFIG)
        manager.load_plugin("another", {})
        manager.unload_all()
        assert manager.list_loaded() == []


class TestPluginManagerGet:
    def test_get_plugin_returns_instance(self, manager_with_dummy):
        plugin = manager_with_dummy.load_plugin("dummy", DUMMY_CONFIG)
        assert manager_with_dummy.get_plugin("dummy") is plugin

    def test_get_not_loaded_raises(self, manager):
        with pytest.raises(PluginManagerError, match="not loaded"):
            manager.get_plugin("dummy")


class TestPluginManagerListLoaded:
    def test_empty_initially(self, manager):
        assert manager.list_loaded() == []

    def test_sorted_names(self, manager):
        manager.register_plugin(AnotherPlugin)
        manager.register_plugin(DummyPlugin)
        manager.load_plugin("another", {})
        manager.load_plugin("dummy", DUMMY_CONFIG)
        assert manager.list_loaded() == ["another", "dummy"]


class TestPluginManagerContextManager:
    def test_context_manager_unloads_all_on_exit(self, manager_with_dummy):
        with manager_with_dummy as m:
            plugin = m.load_plugin("dummy", DUMMY_CONFIG)
            assert plugin.is_connected()
        assert manager_with_dummy.list_loaded() == []
        assert not plugin.is_connected()


class TestPluginManagerDiscover:
    def test_discover_plugins_from_package(self, manager):
        assert "postgresql" in manager.discover_plugins("data_platform.plugins")

    def test_discover_plugins_skips_already_registered(self, manager):
        manager.discover_plugins("data_platform.plugins")
        assert manager.discover_plugins("data_platform.plugins") == []

    def test_discover_bad_package_raises(self, manager):
        with pytest.raises(PluginManagerError, match="Cannot import"):
            manager.discover_plugins("no_such_package_xyz")
