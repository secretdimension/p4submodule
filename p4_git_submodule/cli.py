import click
from pathlib import Path
from urllib.parse import urlparse

from .config_file import ConfigFile

def config_argument(*param_decls: str):
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
@click.option('--root', type=bool, is_flag=True)
@click.option('--name', type=str, prompt=True)
@click.option('--remote', type=urlparse, prompt=True)
@click.option('--tracking', type=str, prompt=True)
@click.option('--path', type=Path)
def create(config: ConfigFile, root: bool, name: str, remote: str, tracking: str, path: Path):
    new = config.add_submodule(name, root)
    new.remote = remote
    new.tracking = tracking

    path = path.resolve()
    if path.is_absolute():
        path = path.relative_to(config.path.parent)
    new.path = path

    config.save()
