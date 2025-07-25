import os
import textwrap
from importlib import import_module
from pathlib import Path
from typing import Optional

import click
from jinja2 import Environment, FileSystemLoader, select_autoescape

def _generate_commands(name: str, root_command: click.Command) -> list[click.Context]:
    results: list[click.Context] = []

    def _recurse(name: str, child: click.Command, parent: Optional[click.Context]) -> None:
        ctx = click.Context(child, parent=parent, info_name=name)
        results.append(ctx)

        for sub_name, sub_child in getattr(child, 'commands', {}).items():
            _recurse(sub_name, sub_child, ctx)

    _recurse(name, root_command, None)

    return results

def _generate_readme(template_path: Path, out_path: Path, commands: list[click.Context]) -> None:
    jinja = Environment(
        loader=FileSystemLoader([os.getcwd()]),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    jinja.filters.update({
        "dedent": textwrap.dedent,
    })

    template = jinja.get_template(str(template_path))

    stream = template.stream(commands=commands)

    with click.open_file(out_path, mode="w") as readme:
        stream.dump(readme)

@click.command()
@click.pass_context
@click.option("--name", type=str, required=False, help="(defaults to the root of module) The name of the script to use as the base")
@click.option("--module", type=str, required=True, prompt=True, help="The module containing the command to write")
@click.option("--command", type=str, required=True, default="main", help="The name of the root command")
@click.option("--template", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True, prompt=True, help="The template file to use when generating the output file")
@click.option("--out", type=click.Path(exists=False, dir_okay=False, writable=True, path_type=Path), required=True, prompt=True, help="The path to write the output file to")
def main(ctx: click.Context, name: Optional[str], module: str, command: str, template: Path, out: Path) -> None:
    try:
        target_module = import_module(module)
    except Exception as e:
        ctx.fail(f"Could not import module: '{module}' Error: {str(e)}")

    try:
        target_command: click.Command = getattr(target_module, command)
    except:
        ctx.fail(f"Could not find command '{command}' in module '{module}'")

    name = name or module.split('.')[0]

    commands = _generate_commands(name, target_command)
    _generate_readme(template, out, commands=commands)

if __name__ == '__main__':
    main()
