import re
from os.path import expanduser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

import click
import pygit2
from paramiko.config import SSHConfig

from .config_file import ConfigFile

# Replace git@github.com:org/repo.git with ssh://git@github.com/org/repo.git
GIT_SSH_REGEX = re.compile(R"([\w\.]+)@([\w\.]+):([\w\.@\:/\-~]+)")

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
        repo = pygit2.clone_repository(
            new.remote.geturl(),
            new.full_path,
            checkout_branch=tracking,
            # depth=1, # NOTE: This breaks everything
            callbacks=MyRemoteCallbacks())

        # If user didn't specify a tracking branch, populate it from the default cloned
        if not new.tracking:
            new.tracking = repo.head.shorthand

        new.current_ref = repo.head.resolve().target

    config.save()
