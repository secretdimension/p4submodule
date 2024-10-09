import click
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from p4_git_submodule.config_file import ConfigFile
from p4_git_submodule.submodule import Submodule

@click.group()
def main():
    pass

@main.command()
@click.argument('config_path', type=Path, required=False)
def dump_config(config_path: Optional[Path]):
    cwd = Path(os.getcwd())
    if not config_path:
        config_path = cwd
    if not config_path or not config_path.is_absolute():
        config_path = cwd / config_path

    config = ConfigFile(config_path)
    for module in config.submodules:
        print(f'{module}: {vars(module)}')

@main.command()
@click.argument('config_path', type=Path, required=False)
@click.option('--root', type=bool, is_flag=True)
@click.option('--name', type=str, prompt=True)
@click.option('--remote', type=urlparse, prompt=True)
@click.option('--tracking', type=str, prompt=True)
@click.option('--path', type=Path)
def create(config_path: Optional[Path], root: bool, name: str, remote: str, tracking: str, path: Path):
    cwd = Path(os.getcwd())
    if not config_path:
        config_path = cwd
    if not config_path or not config_path.is_absolute():
        config_path = cwd / config_path

    config = ConfigFile(config_path)

    new = config.add_submodule(name, root)
    new.remote = remote
    new.tracking = tracking

    path = path.resolve()
    if path.is_absolute():
        path = path.relative_to(config.path.parent)
    new.path = path

    config.save()
