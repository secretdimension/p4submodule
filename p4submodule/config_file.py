# SPDX-FileCopyrightText: © 2025 Secret Dimension, Inc. <info@secretdimension.com>. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

import tomlkit.api
from pathlib import Path
from tomlkit.toml_document import TOMLDocument
from tomlkit.toml_file import TOMLFile
from typing import Optional

from .p4_context import P4Path, P4Context
from .submodule import Submodule

class ConfigFile(TOMLFile):
    """
    Represents a submodule config file representing one or more git submodules
    """

    CONFIG_FILE = "submodule.toml"

    _path: Path
    """The path to the config file"""

    _p4: P4Context

    _document: TOMLDocument

    _is_new: bool

    def __init__(self, path: Path, p4: P4Context) -> None:
        if not isinstance(path, Path):
            path = Path(path)

        path = path.absolute()

        # If the filepath is a directory, use the default config file name
        if path.is_dir():
            path /= ConfigFile.CONFIG_FILE

        super().__init__(path)

        self._p4 = p4

        if path.exists():
            self._is_new = False
            self._document = self.read()
        else:
            self._is_new = True
            self._document = TOMLDocument()

    @property
    def p4(self) -> P4Context:
        return self._p4

    @property
    def directory(self) -> Path:
        return self._path.parent

    @property
    def directory_ws(self) -> P4Path:
        return P4Path(f'//{self._p4.client}') / self.directory.relative_to(self._p4.client_root)

    @property
    def directory_depot(self) -> P4Path:
        return P4Path(self._p4.run_where(self.directory)[0]['depotFile'])

    @property
    def submodules(self) -> list[Submodule]:
        """Collect the list of submodules from the config file"""
        submodules: list[Submodule] = []

        for name, child in self._document.get('submodule', dict()).items():
            submodules.append(Submodule(name, self, child))

        # Create a submodule from root-level settings
        if len(self._document) > 0:
            name = self._document.get('name', self.directory.name)
            submodules.insert(0, Submodule(name, self, self._document))

        return submodules

    def add_submodule(self, name: Optional[str], path: Optional[Path], is_root: bool = False) -> Submodule:
        """Create a new submodule and add it to the file"""
        if path:
            path = path.resolve()
            if path.is_absolute():
                path = path.relative_to(self.directory)

        if is_root:
            new_table = tomlkit.api.Table(self._document, tomlkit.api.Trivia(), False)
            if name:
                new_table.add('name', name)
        else:
            if not name:
                raise ValueError('If is_root is false, a name is required')

            submodule_table = self._document.setdefault('submodule', tomlkit.api.table(True))
            new_table = tomlkit.api.table()
            submodule_table.add(name, new_table)

        return Submodule(name, self, new_table.value, path=path)

    def save(self, change_number: int) -> None:
        """Save changes to the config file"""

        file_path_ws = P4Path(f'//{self._p4.client}') / self._path.relative_to(self._p4.client_root)
        p4_args = ['-c', str(change_number), file_path_ws]

        if not self._is_new:
            self.p4.run_edit(*p4_args)

        self.write(self._document)

        if self._is_new:
            self.p4.run_add(*p4_args)
