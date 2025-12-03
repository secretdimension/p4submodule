# SPDX-FileCopyrightText: © 2025 Secret Dimension, Inc. <info@secretdimension.com>. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Callable
from os.path import expanduser
from pathlib import Path
from typing import Optional, TypeVar, TYPE_CHECKING
from urllib.parse import urlparse, urlunparse, ParseResult

import click
import pygit2
import tomlkit.api
import tomlkit.exceptions
from paramiko.config import SSHConfig
from pygit2.enums import BranchType, DescribeStrategy, MergeAnalysis, ResetMode

if TYPE_CHECKING:
    from .config_file import ConfigFile
    from .p4_context import P4Path
    T = TypeVar('T')

URL = ParseResult

class MyRemoteCallbacks(pygit2.RemoteCallbacks):

    def __init__(self, progress_bar: Optional[click.termui.ProgressBar], credentials = None, certificate = None) -> None:
        super().__init__(credentials, certificate)
        self.progress_bar = progress_bar

    def credentials(self, url_str, username_from_url, allowed_types):
        url = urlparse(url_str)

        if allowed_types & pygit2.enums.CredentialType.USERNAME:
            return pygit2.Username(username_from_url)

        elif allowed_types & pygit2.enums.CredentialType.SSH_KEY:
            ssh_config_path = Path(expanduser('~/.ssh/config'))
            if not ssh_config_path.exists():
                config = SSHConfig.from_path(str(ssh_config_path))
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

    _table: tomlkit.api.Container
    """The table describing the configuration of the submodule"""

    _repo: Optional[pygit2.Repository]
    """The git repository for the submodule (if it exists)"""

    # The below come from the config

    path: Path = _toml_property('path', Path, str) # type: ignore
    """The path to the repo (relative to the file) (MAY BE NONE, see local_path)"""

    remote: URL = _toml_property('remote', urlparse, urlunparse) # type: ignore
    """The remote URL to sync with"""

    tracking: str = _toml_property('tracking') # type: ignore
    """The remote ref to track when syncing"""

    current_ref: Optional[pygit2.Oid] = _toml_property('current_ref', lambda str: pygit2.Oid(hex=str), lambda oid: oid.raw.hex()) # type: ignore
    """The currently synced revision"""

    def __init__(self, name: Optional[str], config: ConfigFile, table: tomlkit.api.Container, path: Optional[Path] = None) -> None:
        self._config = config
        self._table = table
        if path:
            self.path = path

        self.name = name or self.local_path.name

        if repo_path := pygit2.discover_repository(str(self.local_path)):
            self._repo = pygit2.Repository(repo_path)
        else:
            self._repo = None

    @property
    def local_path(self) -> Path:
        return (self._config.directory / (self.path or '.')).resolve()

    @local_path.setter
    def local_path(self, path: Path):
        self.path = path.relative_to(self._config.directory)

    @property
    def ws_path(self) -> P4Path:
        return self._config.directory_ws / (self.path or '.')

    @property
    def depot_path(self) -> P4Path:
        return self._config.directory_depot / (self.path or '.')

    def __repr__(self) -> str:
        return f'Submodule(name="{self.name}" path="{self.local_path}")'


    def _p4_add_index(self, change_num: int) -> None:
        self._config._p4.run_add("-c", str(change_num), "-I", *[(self.ws_path / e.path).as_posix() for e in self._repo.index])


    # Functionality

    def clone(self, change_num: int) -> pygit2.Repository:
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
                str(self.local_path),
                checkout_branch=self.tracking,
                # depth=1, # NOTE: This breaks everything
                callbacks=MyRemoteCallbacks(progress_bar))

        # If user didn't specify a tracking branch, populate it from the default cloned
        if not self.tracking:
            self.tracking = self._repo.head.shorthand

        self.current_ref = self._repo.head.resolve().target

        self._p4_add_index(change_num)

        return self._repo


    def update(self, change_number: int, commit_message: Optional[str] = None) -> bool:
        if not self.current_ref:
            raise Exception("Repo is missing current_ref, cannot update!")

        tracking_branch: Optional[pygit2.Branch] = None
        remote_name: Optional[str] = None
        if self._repo:
            tracking_branch = self._repo.lookup_branch(self.tracking, BranchType.LOCAL)
            if tracking_branch and tracking_branch.upstream:
                remote_name = tracking_branch.upstream.remote_name
            elif self._repo.remotes:
                remote_name = next((remote.name for remote in self._repo.remotes if remote.url == self.remote.geturl()), "origin")

        else:
            self._repo = pygit2.init_repository(
                path=self.local_path,
                origin_url=self.remote.geturl(),
                initial_head=self.tracking,
            )
            remote_name = 'origin'

        # Fetch latest changes
        with click.progressbar(
                label=f"Fetching {remote_name}...",
                show_percent=True,
                length=100,
            ) as progress_bar:
            self._repo.remotes[remote_name].fetch(callbacks=MyRemoteCallbacks(progress_bar))

        if not tracking_branch:
            tracking_branch = self._repo.create_branch(self.tracking, self._repo[self.current_ref].peel(pygit2.Commit))
            self._repo.reset(self.current_ref, ResetMode.MIXED)

        remote_tracking = self._repo.lookup_branch(f'{remote_name}/{self.tracking}', BranchType.REMOTE)

        if remote_tracking.target == self.current_ref:
            print("Up to date!")
            return False

        # Update the index to the last known commit
        self._repo.reset(self.current_ref, ResetMode.MIXED)
        tracking_branch = self._repo.lookup_branch(self.tracking)

        # Check for uncommitted changes
        if self._repo.status():
            if not commit_message:
                raise Exception("Unstaged changes, but commit message not provided!")

            self._repo.index.add_all()
            self._repo.index.write()

            new_commit = self._repo.create_commit(
                tracking_branch.name,
                self._repo.default_signature,
                self._repo.default_signature,
                commit_message,
                self._repo.index.write_tree(),
                [tracking_branch.target])

            # Re-lookup branch since it's changed
            tracking_branch = self._repo.lookup_branch(self.tracking)

            assert tracking_branch.target == new_commit, "New commit did not land correctly"

            print(f"Committed local changes on branch {tracking_branch.name} as {new_commit}")

        ahead, behind = self._repo.ahead_behind(tracking_branch.target, remote_tracking.target)
        merge_analysis, _ = self._repo.merge_analysis(remote_tracking.target)
        base = self._repo.merge_base(tracking_branch.target, remote_tracking.target)
        assert base == self.current_ref, "Merge base should be the most recently pulled remote change"

        print(f"Local branch is {ahead} commits ahead of remote, {behind} commits behind remote")

        if merge_analysis & MergeAnalysis.UP_TO_DATE:
            assert False, "This should have been caught above"

        elif merge_analysis & MergeAnalysis.NONE:
            raise Exception("No merge possible!")

        elif merge_analysis & MergeAnalysis.FASTFORWARD:
            assert ahead == 0

        elif merge_analysis & MergeAnalysis.NORMAL:
            assert ahead > 0

        self._config.p4.run_edit('-c', str(change_number), self.ws_path / '...')

        to_cherrypick: list[pygit2.Oid] = []

        current_commit: pygit2.Commit = self._repo.head.peel(pygit2.Commit)
        for _ in range(ahead):
            to_cherrypick.insert(0, current_commit.id)
            assert len(current_commit.parents) == 1, "Multi-parent commits are not supported!"
            current_commit = current_commit.parents[0]

        assert current_commit.id == base, "Found incorrect rebase base!"

        # Point the tracking branch at the remote branch
        tracking_branch.set_target(remote_tracking.target)
        # Update the index
        self._repo.checkout(tracking_branch)
        # Update the working tree
        self._repo.reset(tracking_branch.target, ResetMode.HARD)

        try:
            tag = self._repo.describe(describe_strategy=DescribeStrategy.TAGS, max_candidates_tags=1)
            self._table['current_ref'].comment(tag)

        except pygit2.GitError:
            pass

        for commit in to_cherrypick:
            self._repo.cherrypick(commit)

        print(f"Updated {behind} commits to {remote_tracking.branch_name} ({remote_tracking.target})")

        if to_cherrypick:
            print(f"Files changed locally are staged in git's index (use \"git cherry-pick --continue\" in {self.local_path} to commit them)")

        self._config.p4.run_revert('-c', str(change_number), '-a')

        self._p4_add_index(change_number)

        # Update the current_ref and save it
        self.current_ref = remote_tracking.target

        return True
