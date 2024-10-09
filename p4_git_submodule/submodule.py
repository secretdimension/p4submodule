from __future__ import annotations

import tomlkit.api
import tomlkit.exceptions
from collections.abc import Callable
from pathlib import Path
from pygit2 import Oid
from typing import Any, Optional, T
from urllib.parse import urlparse, urlunparse, ParseResult

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
    """
    Represents the configuration of a submodule
    """

    name: str
    """The Name of the submodule (defaults to the directory the config file lives in)"""

    _config_dir: Path
    """The path to the config file this submodule came from"""

    _table: tomlkit.api.Table
    """The table describing the configuration of the submodule"""

    # The below come from the config

    path: Path = _toml_property('path', Path, str)
    """The path to the repo (relative to the file) (MAY BE NONE, see full_path)"""

    remote: URL = _toml_property('remote', urlparse, urlunparse)
    """The remote URL to sync with"""

    tracking: str = _toml_property('tracking')
    """The remote ref to track when syncing"""

    current_ref: Optional[Oid] = _toml_property('current_ref', lambda str: Oid(hex=str), lambda oid: oid.raw.hex())
    """The currently synced revision"""

    def __init__(self, name: str, config_dir: Path, config: tomlkit.api.Table) -> None:
        self.name = name
        self._config_dir = config_dir
        self._table = config

    @property
    def full_path(self) -> Path:
        return (self._config_dir / (self.path or '.')).resolve()

    @full_path.setter
    def set_full_path(self, path: Path):
        self.path = path.relative_to(self._config_dir)

    def __repr__(self) -> str:
        return f'Submodule(name="{self.name}" path="{self.full_path}")'

