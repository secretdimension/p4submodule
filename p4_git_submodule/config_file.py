import tomlkit.api
from pathlib import Path
from tomlkit.toml_document import TOMLDocument
from tomlkit.toml_file import TOMLFile
from typing import Optional

from .submodule import Submodule

class ConfigFile(TOMLFile):
    """
    Represents a submodule config file representing one or more git submodules
    """

    CONFIG_FILE = "submodule.toml"

    _path: Path
    """The path to the config file"""

    _document: TOMLDocument

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            path = Path(path)

        path = path.absolute()

        # If the filepath is a directory, use the default config file name
        if path.is_dir():
            path /= ConfigFile.CONFIG_FILE

        super().__init__(path)

        if path.exists():
            self._document = self.read()
        else:
            self._document = TOMLDocument()

    @property
    def submodules(self) -> list[Submodule]:
        """Collect the list of submodules from the config file"""
        submodules: list[Submodule] = []

        for name, child in self._document.get('submodule', dict()).items():
            submodules.append(Submodule(name, self._path.parent, child))

        # Create a submodule from root-level settings
        if len(self._document) > 0:
            name = self._document.get('name', self._path.parent.name)
            submodules.insert(0, Submodule(name, self._path.parent, self._document))

        return submodules

    def add_submodule(self, name: Optional[str], is_root: bool = False) -> Submodule:
        """Create a new submodule and add it to the file"""
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

        return Submodule(name, self._path.parent, new_table)

    def save(self) -> None:
        """Save changes to the config file"""
        self.write(self._document)

