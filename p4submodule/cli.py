# SPDX-FileCopyrightText: © 2025 Secret Dimension, Inc. <info@secretdimension.com>. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

import glob
import re
import textwrap
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import click

from .config_file import ConfigFile
from .p4_context import P4Context

# Replace git@github.com:org/repo.git with ssh://git@github.com/org/repo.git
GIT_SSH_REGEX = re.compile(R"([\w\.]+)@([\w\.]+):([\w\.@\:/\-~]+)")


def config_argument(*param_decls: str):
    """
    Creates a click optional argument for receiving a ConfigFile parameter
    """
    class ConfigFileParamType(click.ParamType):
        name = "ConfigFile"

        def convert(self, value, param: click.Parameter | None, ctx: click.Context | None):
            if not ctx:
                raise Exception("ctx must be set!")

            if not isinstance(value, Path):
                value = Path(value)

            p4 = ctx.find_object(P4Context)
            if not p4:
                ctx.fail("internal error: p4 object must be set!")

            return ConfigFile(value, p4)

    return click.argument(
        *param_decls,
        type=ConfigFileParamType(),
        required=False,
        default='.',
        metavar="[PATH TO submodule.toml]",
    )

changelist_option = click.option('-c', '--changelist', type=int, metavar="CHANGELIST", help="(Defaults to creating a new CL) The P4 changelist to place changes in")

@click.group()
@click.pass_context
@click.option('--p4-port', type=str, help="P4 server address to use intead of inferring from `p4 set`")
@click.option('--p4-user', type=str, help="P4 username to use intead of inferring from `p4 set`")
@click.option('--p4-client', type=str, help="P4 workspace to use intead of inferring from `p4 set`")
def main(ctx: click.Context, p4_port: str, p4_user: str, p4_client: str):
    """A tool for managing git repositories inside of Perforce depots."""

    p4 = P4Context()

    if p4_port:
        p4.port = p4_port
    if p4_user:
        p4.user = p4_user
    if p4_client:
        p4.client = p4_client

    ctx.obj = ctx.with_resource(p4)

@main.command(hidden=True)
@config_argument('config')
def dump_config(config: ConfigFile):
    for module in config.submodules:
        print(f'{module}: {vars(module)}')

@main.command()
@config_argument('config')
@click.option('--name', type=str, metavar="NAME", help="(defaults to the checkout directory name) A name used to refer to the submodule", show_default=False)
@click.option('--remote', type=str, prompt=True, metavar="URL", help="The URL for the remote repository to track")
@click.option('--tracking', type=str, metavar="BRANCH", help="The branch to track from the remote")
@click.option('--path', type=Path, help="The optional relative path from the config file to the checkout directory")
@click.option('--no-sync', type=bool, is_flag=True, help="Create the submodule config file, but don't clone it")
@changelist_option
def create(config: ConfigFile, name: Optional[str], remote: str, tracking: Optional[str], path: Optional[Path], no_sync: bool, changelist: Optional[int]):
    """Creates a new submodule."""

    new = config.add_submodule(name, path, name is None)

    if match := GIT_SSH_REGEX.match(remote):
        remote = "ssh://{}@{}/{}".format(*match.groups())

    new.remote = urlparse(remote)

    if tracking:
        new.tracking = tracking
    elif no_sync:
        raise click.UsageError('When --no-sync is passed, --tracking is required!')

    if changelist:
        change_number = changelist
    else:
        change = config.p4.fetch_change()
        change._description = textwrap.dedent(f"""
        Creating {new.name} submodule in {new.depot_path}

        url: {remote}
        tracking: {tracking}
        """).strip()
        change_number = config.p4.save_change(change)

    if not no_sync:
        _ = new.clone(change_number)

    config.save(change_number)

    print(f"Added submodule {new.name} in CL {change_number}")

@main.command()
@click.pass_context
@click.argument('configs', type=str, nargs=-1)
@click.option('-m', '--message', type=str, default="[p4submodule] updating repo", help="The commit message to use when converting local changes to the target repository type")
@changelist_option
def update(ctx: click.Context, configs: list[str], message: Optional[str], changelist: Optional[int]):
    """
    Fetch & update submodules in config to the latest revision of their tracking branches.

    This command will do it's best to preserve your local/p4 changes to directories by commiting them to the local git repository,
    fetching the remote, and rebasing your change on top of the newest tracking version, but it is possible that conflicts may arise.
    """
    p4 = ctx.find_object(P4Context)

    for config_entry in configs:
        if not config_entry.endswith("submodule.toml"):
            config_entry = config_entry + "/submodule.toml"

        for config_file in glob.iglob(f"{config_entry}", recursive=True):
            config = ConfigFile(Path(config_file), p4)

            if not changelist:
                change = p4.fetch_change()
                change._description = textwrap.dedent(f"""
                Update submodule{'s' if len(config.submodules) > 1 else ''} in {config.directory_depot}
                """).strip()
                change_number = p4.save_change(change)
            else:
                change_number = changelist

            for module in config.submodules:
                if module.update(change_number=change_number, commit_message=message):
                    config.save(change_number)
                    print(f"Updated submodules in {config.directory} in CL {change_number}")
                elif not changelist:
                    p4.delete_change(change_number)
