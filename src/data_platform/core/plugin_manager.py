import importlib
import importlib.util
import pkgutil
from pathlib import Path
from typing import Any, Type

from data_platform.core.base_plugin import DataSourcePlugin
from data_platform.core.plugin_registry import PluginRegistry, PluginRegistryError


class PluginManagerError(Exception):
    pass


class PluginManager:
    """Manages plugin lifecycle: loading, configuration, and access."""

    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self._registry = registry or PluginRegistry()
        self._instances: dict[str, DataSourcePlugin] = {}

    @property
    def registry(self) -> PluginRegistry:
        return self._registry

    def register_plugin(self, plugin_class: Type[DataSourcePlugin]) -> None:
        """Register a plugin class in the underlying registry."""
        self._registry.register(plugin_class)

    def discover_plugins(self, package: str) -> list[str]:
        """
        Import all modules inside *package* and auto-register any
        DataSourcePlugin subclasses found at module level.

        Returns list of newly registered plugin names.
        """
        try:
            pkg = importlib.import_module(package)
        except ModuleNotFoundError as exc:
            raise PluginManagerError(f"Cannot import package '{package}'") from exc

        pkg_path = getattr(pkg, "__path__", [])
        registered: list[str] = []

        for _, module_name, _ in pkgutil.walk_packages(pkg_path, prefix=f"{package}."):
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue

            for attr_name in dir(module):
                obj = getattr(module, attr_name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, DataSourcePlugin)
                    and obj is not DataSourcePlugin
                ):
                    try:
                        self._registry.register(obj)
                        registered.append(obj.__new__(obj).metadata.name)
                    except PluginRegistryError:
                        pass

        return registered

    def discover_plugins_from_path(self, path: str | Path, package_name: str) -> list[str]:
        """
        Load a directory of plugin modules from an arbitrary filesystem path
        and auto-register DataSourcePlugin subclasses found there.
        """
        directory = Path(path)
        if not directory.is_dir():
            raise PluginManagerError(f"'{directory}' is not a directory")

        registered: list[str] = []
        for py_file in directory.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = f"{package_name}.{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)  # type: ignore[union-attr]
            except Exception:
                continue

            for attr_name in dir(module):
                obj = getattr(module, attr_name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, DataSourcePlugin)
                    and obj is not DataSourcePlugin
                ):
                    try:
                        self._registry.register(obj)
                        registered.append(obj.__new__(obj).metadata.name)
                    except PluginRegistryError:
                        pass

        return registered

    def load_plugin(self, name: str, config: dict[str, Any]) -> DataSourcePlugin:
        """
        Instantiate the named plugin, validate *config*, connect, and store
        the live instance. Raises if already loaded or plugin unknown.
        """
        if name in self._instances:
            raise PluginManagerError(f"Plugin '{name}' is already loaded")

        plugin_class = self._registry.get(name)
        instance = plugin_class()
        instance.validate_config(config)
        instance.connect(config)
        self._instances[name] = instance
        return instance

    def unload_plugin(self, name: str) -> None:
        """Disconnect and remove a loaded plugin instance."""
        if name not in self._instances:
            raise PluginManagerError(f"Plugin '{name}' is not loaded")
        instance = self._instances.pop(name)
        if instance.is_connected():
            instance.disconnect()

    def get_plugin(self, name: str) -> DataSourcePlugin:
        """Return the live instance for *name*. Raises if not loaded."""
        if name not in self._instances:
            raise PluginManagerError(f"Plugin '{name}' is not loaded")
        return self._instances[name]

    def list_loaded(self) -> list[str]:
        """Return sorted list of currently loaded (connected) plugin names."""
        return sorted(self._instances)

    def unload_all(self) -> None:
        """Disconnect and remove every loaded plugin."""
        for name in list(self._instances):
            self.unload_plugin(name)

    def __enter__(self) -> "PluginManager":
        return self

    def __exit__(self, *_: Any) -> None:
        self.unload_all()
