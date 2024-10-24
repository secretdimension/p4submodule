import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import click
import pygit2

from .config_file import ConfigFile

# Replace git@github.com:org/repo.git with ssh://git@github.com/org/repo.git
GIT_SSH_REGEX = re.compile(R"([\w\.]+)@([\w\.]+):([\w\.@\:/\-~]+)")


def config_argument(*param_decls: str):
    """
    Creates a click optional argument for receiving a ConfigFile parameter
    """
    return click.argument(
        *param_decls,
        type=ConfigFile,
        required=False,
        default='.',
    )

@click.group()
def main():
    pass

@main.command()
@config_argument('config')
def dump_config(config: ConfigFile):
    for module in config.submodules:
        print(f'{module}: {vars(module)}')

@main.command()
@config_argument('config')
@click.option('--name', type=str)
@click.option('--remote', type=str, prompt=True)
@click.option('--tracking', type=str)
@click.option('--path', type=Path)
@click.option('--no-sync', type=bool, is_flag=True)
def create(config: ConfigFile, name: Optional[str], remote: str, tracking: Optional[str], path: Optional[Path], no_sync: bool):
    new = config.add_submodule(name, name is None)

    if match := GIT_SSH_REGEX.match(remote):
        remote = "ssh://{}@{}/{}".format(*match.groups())

    new.remote = urlparse(remote)

    if tracking:
        new.tracking = tracking
    elif no_sync:
        raise click.UsageError('When --no-sync is passed, --tracking is required!')

    if path:
        path = path.resolve()
        if path.is_absolute():
            new.path = path = path.relative_to(config.path.parent)

    if not no_sync:
        new.clone()

    config.save()

@main.command()
@config_argument('config')
def update(config: ConfigFile):
    for module in config.submodules:
        module.update()
    config.save()
