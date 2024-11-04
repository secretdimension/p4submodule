<!---
DO NOTE EDIT README.MD! Edit README.md.in instead.
-->

# p4submodule

A tool for managing git repositories inside of Perforce depots.


## CLI Documentation


### p4submodule

A tool for managing git repositories inside of Perforce depots.

> Usage: p4submodule [OPTIONS] COMMAND [ARGS]...




`--p4-port TEXT`: P4 server address to use intead of inferring from `p4 set`




`--p4-user TEXT`: P4 username to use intead of inferring from `p4 set`




`--p4-client TEXT`: P4 workspace to use intead of inferring from `p4 set`





### create

Creates a new submodule.

> Usage: p4submodule create [OPTIONS] [CONFIG]







`--name TEXT`: (defaults to the checkout directory name) A name used to refer to the submodule




`--remote TEXT`: The URL for the remote repository to track




`--tracking TEXT`: The branch to track from the remote




`--path PATH`: The optional relative path from the config file to the checkout directory




`--no-sync`: Create the submodule config file, but don't clone it





### update

Fetch & update submodules in config to the latest revision of their tracking branches.

> Usage: p4submodule update [OPTIONS] [CONFIG]







`-m, --message TEXT`: The commit message to use when converting local changes to the target repository type



