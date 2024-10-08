from __future__ import annotations

import tomllib
from pathlib import Path, PurePath
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse, ParseResult

from pygit2 import Oid

URL = ParseResult

class Submodule(object):
    CONFIG_FILE = "submodule.toml"

    name: str
    """The Name of the submodule (defaults to the directory the config file lives in)"""

    source_file: Path
    """The path to the config file this submodule came from"""

    # The below come from the config

    path: Path
    """The path to the repo (relative to the file) (defaults to file directory)"""

    remote: URL
    """The remote URL to sync with"""

    tracking: str
    """The remote ref to track when syncing"""

    current_ref: Optional[Oid]
    """The currently synced revision"""

    def __init__(self, name: str, source_file: Path, config: dict[str, Any]) -> None:
        self.name = name
        self.source_file = source_file

        self.path = (source_file.parent / config.get('path', '.')).resolve()

        if not self.path.is_relative_to(source_file.parent):
            raise ValueError(f"Submodule {name}'s path ('{config['path']}') must be relative to the file path '{source_file.parent}'")

        self.remote = urlparse(config['remote'])
        self.tracking = config['tracking']
        if ref_str := config.get('current_ref'):
            self.current_ref = Oid(hex=ref_str)
        else:
            self.current_ref = None

    def __repr__(self) -> str:
        return f'<Submodule {self.name}>'

    def to_dict(self) -> dict[str, Any]:
        props = {
            "remote": urlunparse(self.remote),
            "tracking": self.tracking,
        }

        relative_path = self.path.relative_to(self.source_file.parent)
        if len(relative_path.parts) > 0:
            props["path"] = relative_path.as_posix()

        if self.current_ref:
            props["current_ref"] = self.current_ref.raw.hex()

        return props

    @classmethod
    def from_file(cls, file: Path) -> list[Submodule]:
        """
        Loads a config file to a list of Submodule definitions.
        """

        # If the filepath is a directory, use the default config file name
        if file.is_dir():
            file /= cls.CONFIG_FILE

        with file.open('rb') as fp:
            config = tomllib.load(fp)

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
