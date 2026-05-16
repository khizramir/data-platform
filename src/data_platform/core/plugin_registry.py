import inspect
from typing import Type

from data_platform.core.base_plugin import DataSourcePlugin, PluginMetadata


class PluginRegistryError(Exception):
    pass


class PluginRegistry:
    """Central registry mapping plugin names to their classes."""

    def __init__(self) -> None:
        self._plugins: dict[str, Type[DataSourcePlugin]] = {}

    def register(self, plugin_class: Type[DataSourcePlugin]) -> None:
        """Register a plugin class. Raises if name is already registered."""
        if not (isinstance(plugin_class, type) and issubclass(plugin_class, DataSourcePlugin)):
            raise TypeError(f"{plugin_class!r} must be a subclass of DataSourcePlugin")
        if inspect.isabstract(plugin_class):
            raise TypeError(f"{plugin_class.__name__} is abstract and cannot be registered")

        try:
            metadata: PluginMetadata = plugin_class.__new__(plugin_class).metadata
        except Exception as exc:
            raise PluginRegistryError(f"Could not read metadata from {plugin_class.__name__}") from exc

        name = metadata.name
        if name in self._plugins:
            raise PluginRegistryError(f"Plugin '{name}' is already registered")
        self._plugins[name] = plugin_class

    def unregister(self, name: str) -> None:
        """Remove a plugin by name. Raises if not found."""
        if name not in self._plugins:
            raise PluginRegistryError(f"Plugin '{name}' is not registered")
        del self._plugins[name]

    def get(self, name: str) -> Type[DataSourcePlugin]:
        """Return the plugin class for *name*. Raises if not found."""
        if name not in self._plugins:
            raise PluginRegistryError(f"Plugin '{name}' is not registered")
        return self._plugins[name]

    def list_plugins(self) -> list[str]:
        """Return sorted list of registered plugin names."""
        return sorted(self._plugins)

    def is_registered(self, name: str) -> bool:
        return name in self._plugins

    def __len__(self) -> int:
        return len(self._plugins)
