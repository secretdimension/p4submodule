from __future__ import annotations

from collections.abc import Callable
from os.path import expanduser
from pathlib import Path
from typing import Optional, T, TYPE_CHECKING
from urllib.parse import urlparse, urlunparse, ParseResult

import click
import pygit2
import tomlkit.api
import tomlkit.exceptions
from paramiko.config import SSHConfig
from pygit2.enums import MergeAnalysis, ResetMode

if TYPE_CHECKING:
    from .config_file import ConfigFile
    from .p4_context import P4Path

URL = ParseResult

class MyRemoteCallbacks(pygit2.RemoteCallbacks):

    def __init__(self, progress_bar, credentials = None, certificate = None) -> None:
        super().__init__(credentials, certificate)
        self.progress_bar = progress_bar

    def credentials(self, url_str, username_from_url, allowed_types):
        url = urlparse(url_str)

        if allowed_types & pygit2.enums.CredentialType.USERNAME:
            return pygit2.Username(username_from_url)

        elif allowed_types & pygit2.enums.CredentialType.SSH_KEY:
            ssh_config_path = Path(expanduser('~/.ssh/config'))
            if not ssh_config_path.exists():
                config = SSHConfig.from_path(ssh_config_path)
                if url_config := config.lookup(url.hostname):
                    if privkey := url_config.get('identityfile'):
                        return pygit2.Keypair(username_from_url, expanduser(privkey) + ".pub", expanduser(privkey), "")

            # Attempt default ssh keys
            return pygit2.Keypair(username_from_url, expanduser("~/.ssh/id_rsa.pub"), expanduser("~/.ssh/id_rsa"), "")

        else:
            return None

    def transfer_progress(self, stats: pygit2.remotes.TransferProgress):
        if self.progress_bar:
            self.progress_bar.length = stats.total_objects
            self.progress_bar.update(stats.indexed_objects - self.progress_bar._completed_intervals)

def _toml_property(key: str, reader: Callable[[str], T] = lambda x: x, writer: Callable[[T], str] = lambda x: x) -> property:
    """Helper for generating properties accessing a toml table"""
    cache_key = f'_{key}'
    def _get(self: Submodule):
        if cached := getattr(self, cache_key, None):
            return cached
        try:
            result = reader(self._table[key])
            setattr(self, cache_key, result)
            return result
        except tomlkit.exceptions.NonExistentKey:
            return None

    def _set(self, new):
        setattr(self, cache_key, new)
        self._table[key] = writer(new)

    def _del(self):
        setattr(self, cache_key, None)
        return self._table.__delitem__(key)

    return property(_get, _set, _del)

class Submodule(object):
    """
    Represents the configuration of a submodule
    """

    name: str
    """The Name of the submodule (defaults to the directory the config file lives in)"""

    _config: ConfigFile
    """The config file this submodule came from"""

    _table: tomlkit.api.Table
    """The table describing the configuration of the submodule"""

    _repo: Optional[pygit2.Repository]
    """The git repository for the submodule (if it exists)"""

    # The below come from the config

    path: Path = _toml_property('path', Path, str)
    """The path to the repo (relative to the file) (MAY BE NONE, see local_path)"""

    remote: URL = _toml_property('remote', urlparse, urlunparse)
    """The remote URL to sync with"""

    tracking: str = _toml_property('tracking')
    """The remote ref to track when syncing"""

    current_ref: Optional[pygit2.Oid] = _toml_property('current_ref', lambda str: pygit2.Oid(hex=str), lambda oid: oid.raw.hex())
    """The currently synced revision"""

    def __init__(self, name: Optional[str], config: ConfigFile, table: tomlkit.api.Table, path: Optional[Path] = None) -> None:
        self._config = config
        self._table = table
        if path:
            self.path = path

        self.name = name or self.local_path.name

        if path := pygit2.discover_repository(self.local_path):
            self._repo = pygit2.Repository(path)
        else:
            self._repo = None

    @property
    def local_path(self) -> Path:
        return (self._config.directory / (self.path or '.')).resolve()

    @local_path.setter
    def set_local_path(self, path: Path):
        self.path = path.relative_to(self._config.directory)

    @property
    def ws_path(self) -> P4Path:
        return self._config.directory_ws / (self.path or '.')

    def __repr__(self) -> str:
        return f'Submodule(name="{self.name}" path="{self.local_path}")'


    # Functionality

    def clone(self) -> tuple[pygit2.Repository, int]:
        """Clone the submodule into the relevant directory (directory _cannot_ already exist)"""
        if self._repo:
            raise Exception("Cannot clone() submodule that is already cloned!")

        with click.progressbar(
                label="Cloning...",
                show_percent=True,
                length=100,
            ) as progress_bar:
            self._repo = pygit2.clone_repository(
                self.remote.geturl(),
                self.local_path,
                checkout_branch=self.tracking,
                # depth=1, # NOTE: This breaks everything
                callbacks=MyRemoteCallbacks(progress_bar))

        # If user didn't specify a tracking branch, populate it from the default cloned
        if not self.tracking:
            self.tracking = self._repo.head.shorthand

        self.current_ref = self._repo.head.resolve().target

        change = self._config._p4.fetch_change()
        change._description = f"""
        Adding submodule {self.name}
        """.strip()
        change_num = self._config.p4.save_change(change)
        self._config._p4.run_add("-c", str(change_num), *[(self.ws_path / e.path).as_posix() for e in self._repo.index])

        return self._repo, change_num


    def update(self, change_number: int, commit_message: Optional[str] = None) -> None:
        if not self._repo:
            raise Exception("Cannot update submodule which has not been cloned!")
        if not self.current_ref:
            raise Exception("Repo is missing current_ref, cannot update!")

        tracking_branch = self._repo.lookup_branch(self.tracking)

        # Fetch latest changes
        with click.progressbar(
                label="Fetching...",
                show_percent=True,
                length=100,
            ) as progress_bar:
            self._repo.remotes[tracking_branch.upstream.remote_name].fetch(callbacks=MyRemoteCallbacks(progress_bar))

        remote_tracking = self._repo.lookup_reference(tracking_branch.upstream_name)

        # Check for uncommitted changes
        if self._repo.status():
            if not commit_message:
                raise Exception("Unstaged changes, but commit message not provided!")

            self._repo.index.add_all()
            self._repo.index.write()

            self._repo.create_commit(
                tracking_branch.name,
                self._repo.default_signature,
                self._repo.default_signature,
                commit_message,
                self._repo.index.write_tree(),
                [tracking_branch.target])

            # Re-lookup branch since it's changed
            tracking_branch = self._repo.lookup_branch(self.tracking)

        ahead, behind = self._repo.ahead_behind(tracking_branch.target, remote_tracking.target)
        merge_analysis, _ = self._repo.merge_analysis(remote_tracking.target)

        if merge_analysis & MergeAnalysis.UP_TO_DATE:
            assert(ahead == 0)

            print("Up to date!")
            return

        elif merge_analysis & MergeAnalysis.FASTFORWARD:
            assert(ahead == 0)

            self._config.p4.run_edit('-c', str(change_number), self.ws_path / '...')

            # Point the tracking branch at the remote branch
            tracking_branch.set_target(remote_tracking.target)
            # Update the index
            self._repo.checkout(tracking_branch)
            # Update the working tree
            self._repo.reset(tracking_branch.target, ResetMode.HARD)

            self._config.p4.run_add('-c', str(change_number), self.ws_path / '...')

            print(f"Fast-forward updated {behind} commits to {tracking_branch.upstream_name} ({remote_tracking.target})")

        elif merge_analysis & MergeAnalysis.NORMAL:
            assert(ahead > 0)

            print(f"Local branch is {ahead} commits ahead of remote, {behind} commits behind remote")
            raise Exception("Merge commit is required, unsupported")

        elif merge_analysis & MergeAnalysis.NONE:
            raise Exception("No merge possible!")

        # Update the current_ref and save it
        self.current_ref = self._repo.head.resolve().target

