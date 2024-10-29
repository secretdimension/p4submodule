import re
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
    return click.argument(
        *param_decls,
        type=ConfigFile,
        required=False,
        default='.',
    )

pass_p4 = click.make_pass_decorator(P4Context, ensure=True)

@click.group()
@click.pass_context
@click.option('--p4-port', type=str)
@click.option('--p4-user', type=str)
@click.option('--p4-client', type=str)
def main(ctx: click.Context, p4_port: str, p4_user: str, p4_client: str):
    p4 = P4Context()

    if p4_port:
        p4.port = p4_port
    if p4_user:
        p4.user = p4_user
    if p4_client:
        p4.client = p4_client

    ctx.obj = ctx.with_resource(p4)

@main.command()
@config_argument('config')
def dump_config(config: ConfigFile):
    for module in config.submodules:
        print(f'{module}: {vars(module)}')

@main.command()
@pass_p4
@config_argument('config')
@click.option('--name', type=str)
@click.option('--remote', type=str, prompt=True)
@click.option('--tracking', type=str)
@click.option('--path', type=Path)
@click.option('--no-sync', type=bool, is_flag=True)
def create(p4: P4Context, config: ConfigFile, name: Optional[str], remote: str, tracking: Optional[str], path: Optional[Path], no_sync: bool):
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
@pass_p4
@config_argument('config')
@click.option('-m', '--message', type=str)
def update(p4: P4Context, config: ConfigFile, message: Optional[str]):
    for module in config.submodules:
        module.update(commit_message=message)
    config.save()
