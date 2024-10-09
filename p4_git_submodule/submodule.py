from __future__ import annotations
from collections.abc import Callable

import tomlkit
import tomlkit.api
import tomlkit.exceptions
from pathlib import Path
from typing import Any, Optional, T
from urllib.parse import urlparse, urlunparse, ParseResult

from pygit2 import Oid

URL = ParseResult

def _toml_property(key: str, reader: Callable[[str], T] = lambda x: x, writer: Callable[[T], str] = lambda x: x) -> property:
    """Helper for generating properties accessing a toml table"""
    def _get(self: Submodule):
        try:
            return reader(self._table[key])
        except tomlkit.exceptions.NonExistentKey:
            return None

    def _set(self, new):
        self._table[key] = writer(new)

    def _del(self):
        return self._table.__delitem__(key)

    return property(_get, _set, _del)

class Submodule(object):
    CONFIG_FILE = "submodule.toml"

    name: str
    """The Name of the submodule (defaults to the directory the config file lives in)"""

    source_file: Path
    """The path to the config file this submodule came from"""

    _table: tomlkit.api.Table

    # The below come from the config

    path: Path = _toml_property('path', Path, str)
    """The path to the repo (relative to the file) (MAY BE NONE, see full_path)"""

    remote: URL = _toml_property('remote', urlparse, urlunparse)
    """The remote URL to sync with"""

    tracking: str = _toml_property('tracking')
    """The remote ref to track when syncing"""

    current_ref: Optional[Oid] = _toml_property('current_ref', lambda str: Oid(hex=str), lambda oid: oid.raw.hex())
    """The currently synced revision"""

    def __init__(self, name: str, source_file: Path, config: tomlkit.api.Table) -> None:
        self.name = name
        self.source_file = source_file
        self._table = config

        if self.path and not self.path.is_relative_to(source_file.parent):
            raise ValueError(f"Submodule {name}'s path ('{config['path']}') must be relative to the file path '{source_file.parent}'")

    @property
    def full_path(self) -> Path:
        return (self.source_file.parent / (self.path or '.')).resolve()

    @full_path.setter
    def set_full_path(self, path: Path):
        self.path = path.relative_to(self.source_file.parent)

    def __repr__(self) -> str:
        return f'Submodule(name={self.name})'

    @classmethod
    def from_file(cls, file: Path) -> list[Submodule]:
        """
        Loads a config file to a list of Submodule definitions.
        """

        # If the filepath is a directory, use the default config file name
        if file.is_dir():
            file /= cls.CONFIG_FILE

        with file.open('rb') as fp:
            config = tomlkit.load(fp)

        # The list to return
        submodules: list[Submodule] = []

        named_submodules: dict[str, dict[str, Any]] = config.pop('submodule', dict())
        for name, child in named_submodules.items():
            submodules.append(cls(name, file, child))

        # Create a submodule from root-level settings
        if len(config) > 0:
            name = config.get('name', file.parent.name)
            submodules.insert(0, cls(name, file, config))

        return submodules


