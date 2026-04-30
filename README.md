<!--
SPDX-FileCopyrightText: © 2025 Secret Dimension, Inc. <info@secretdimension.com>. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
-->

<!---
DO NOTE EDIT README.MD! Edit README.md.in instead.
-->

# p4submodule

A tool for managing git repositories inside of Perforce depots.

This tool was built for managing Unreal Engine plugins that are distributed via GitHub, but it may have other uses as well.

## Installation

1. Ensure you have python3 & [pipx](https://github.com/pypa/pipx) installed
2. Run `pipx install p4submodule`
3. Tada!

## LFS Repositories

If the repository you're cloning or updating uses git LFS, you'll need to run some additional commands immediately after a `create` or `update`.

1. `git lfs fetch`: Caches the LFS data on your local machine.
2. `git lfs checkout`: Replaces the contents of the files with the cached LFS data.

Note: If you do not have git LFS installed on your local machine, run `git lfs install` first.

## CLI Documentation

### p4submodule

A tool for managing git repositories inside of Perforce depots.

> Usage: p4submodule [OPTIONS] COMMAND [ARGS]...

`--p4-port TEXT`: P4 server address to use intead of inferring from `p4 set`

`--p4-user TEXT`: P4 username to use intead of inferring from `p4 set`

`--p4-client TEXT`: P4 workspace to use intead of inferring from `p4 set`


### create

Creates a new submodule.

> Usage: p4submodule create [OPTIONS] [PATH TO submodule.toml]

`--name NAME`: (defaults to the checkout directory name) A name used to refer to the submodule

`--remote URL`: The URL for the remote repository to track

`--tracking BRANCH`: The branch to track from the remote

`--path PATH`: The optional relative path from the config file to the checkout directory

`--no-sync`: Create the submodule config file, but don't clone it

`-c, --changelist CHANGELIST`: (Defaults to creating a new CL) The P4 changelist to place changes in


### update

Fetch & update submodules in config to the latest revision of their tracking branches.

This command will do it's best to preserve your local/p4 changes to directories by commiting them to the local git repository,
fetching the remote, and rebasing your change on top of the newest tracking version, but it is possible that conflicts may arise.

> Usage: p4submodule update [OPTIONS] [CONFIGS]...

`-m, --message TEXT` (Defaults to `[p4submodule] updating repo`): The commit message to use when converting local changes to the target repository type

`-c, --changelist CHANGELIST`: (Defaults to creating a new CL) The P4 changelist to place changes in


## `submodule.toml` Format

Editing this file by hand should _not_ be required, as all modifications should be covered by the above commands.

### `submodule.[NAME]` sections (optional) (NAME default: file directory name)

You may use this section to optionally define multiple submodules in the same file.
Example:
```toml
[Submodule.ModuleA]
...
[Submodule.ModuleB]
...
```

### `path` (optional) (default: file directory)

You may use this field to specify the path to the git repository checkout root.

### `remote`

The path to the git remote to checkout/clone from.

### `tracking`

The remote branch to track when updating.

### `current_ref`

The OID of the git commit currently in use by the submodule.
