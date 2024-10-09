import click
import os
from pathlib import Path
from typing import Optional

from p4_git_submodule.submodule import Submodule

@click.group()
def main():
    pass

@main.command()
@click.argument('path', type=Path, required=False)
def dump_config(path: Optional[Path]):
    cwd = Path(os.getcwd())
    if not path:
        path = cwd
    if not path or not path.is_absolute():
        path = cwd / path
    for module in Submodule.from_file(path):
        print(vars(module))
