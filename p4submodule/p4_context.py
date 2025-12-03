# SPDX-FileCopyrightText: © 2025 Secret Dimension, Inc. <info@secretdimension.com>. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import socket
from pathlib import Path, PurePosixPath

import P4 # type: ignore

P4Path = PurePosixPath

class P4Context(P4.P4):
    """
    Wrapper for P4.P4 that gives it some extra functionality that we want
    """

    def __init__(self) -> None:
        # P4Python on Linux doesn't set cwd correctly by default, so we override it
        super().__init__(cwd=os.getcwd())

    def __enter__(self) -> P4Context:
        # We want with statements to connect to the p4 server
        return super().__enter__().connect()

    def save_change(self, change) -> int:
        """Wrapper around super().save_change that returns the CL number"""
        return int(super().__getattr__('save_change')(change)[0].split()[1])

    @property
    def client_root(self) -> Path:
        """The working directory of the currently set client"""

        # This is required because if you run 'p4 clients -o <whatever>' and <whatever> is a client that doesn't exist,
        # it will return you the template for a new client instead of erroring.
        existing_clients = [client['client'] for client in self.run_clients('--me')]
        if not self.client in existing_clients:
            raise Exception("Client not set, set via: --p4-client, p4 set P4CLIENT, or .p4config")

        client = self.run_client('-o', self.client)[0]

        if client.get('Host') not in [None, socket.gethostname()]:
            raise Exception(f"Client {self.client} has a Host of {client['Host']}, but curret hostname is {socket.gethostname()}")

        return Path(client['Root'])
