from __future__ import annotations

from collections.abc import Callable
from os.path import expanduser
from pathlib import Path
from typing import Optional, T
from urllib.parse import urlparse, urlunparse, ParseResult

import pygit2
import tomlkit.api
import tomlkit.exceptions
from paramiko.config import SSHConfig
from pygit2.enums import MergeAnalysis, ResetMode

URL = ParseResult

class MyRemoteCallbacks(pygit2.RemoteCallbacks):

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

    _repo: Optional[pygit2.Repository]
    """The git repository for the submodule (if it exists)"""

    # The below come from the config

    path: Path = _toml_property('path', Path, str)
    """The path to the repo (relative to the file) (MAY BE NONE, see full_path)"""

    remote: URL = _toml_property('remote', urlparse, urlunparse)
    """The remote URL to sync with"""

    tracking: str = _toml_property('tracking')
    """The remote ref to track when syncing"""

    current_ref: Optional[pygit2.Oid] = _toml_property('current_ref', lambda str: pygit2.Oid(hex=str), lambda oid: oid.raw.hex())
    """The currently synced revision"""

    def __init__(self, name: str, config_dir: Path, config: tomlkit.api.Table) -> None:
        self.name = name
        self._config_dir = config_dir
        self._table = config

        if path := pygit2.discover_repository(self.full_path):
            self._repo = pygit2.Repository(path)
        else:
            self._repo = None

    @property
    def full_path(self) -> Path:
        return (self._config_dir / (self.path or '.')).resolve()

    @full_path.setter
    def set_full_path(self, path: Path):
        self.path = path.relative_to(self._config_dir)

    def __repr__(self) -> str:
        return f'Submodule(name="{self.name}" path="{self.full_path}")'


    # Functionality

    def clone(self) -> pygit2.Repository:
        """Clone the submodule into the relevant directory (directory _cannot_ already exist)"""
        if self._repo:
            raise Exception("Cannot clone() submodule that is already cloned!")

        self._repo = pygit2.clone_repository(
            self.remote.geturl(),
            self.full_path,
            checkout_branch=self.tracking,
            # depth=1, # NOTE: This breaks everything
            callbacks=MyRemoteCallbacks())

        # If user didn't specify a tracking branch, populate it from the default cloned
        if not self.tracking:
            self.tracking = self._repo.head.shorthand

        self.current_ref = self._repo.head.resolve().target

        return self._repo


    def update(self, commit_message: Optional[str] = None) -> None:
        if not self._repo:
            raise Exception("Cannot update submodule which has not been cloned!")
        if not self.current_ref:
            raise Exception("Repo is missing current_ref, cannot update!")

        tracking_branch = self._repo.lookup_branch(self.tracking)

        # Fetch latest changes
        self._repo.remotes[tracking_branch.upstream.remote_name].fetch(callbacks=MyRemoteCallbacks())

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

            # Point the tracking branch at the remote branch
            tracking_branch.set_target(remote_tracking.target)
            # Update the index
            self._repo.checkout(tracking_branch)
            # Update the working tree
            self._repo.reset(tracking_branch.target, ResetMode.HARD)

            print(f"Fast-forward updated {behind} commits to {tracking_branch.upstream_name} ({remote_tracking.target})")

        elif merge_analysis & MergeAnalysis.NORMAL:
            assert(ahead > 0)

            print(f"Local branch is {ahead} commits ahead of remote, {behind} commits behind remote")
            raise Exception("Merge commit is required, unsupported")

        elif merge_analysis & MergeAnalysis.NONE:
            raise Exception("No merge possible!")

        # Update the current_ref and save it
        self.current_ref = self._repo.head.resolve().target

