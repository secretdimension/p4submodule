from __future__ import annotations

import os
import socket
from pathlib import Path, PurePosixPath

import P4

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

    @property
    def client_root(self) -> str:
        """The working directory of the currently set client"""

        # This is required because if you run 'p4 clients -o <whatever>' and <whatever> is a client that doesn't exist,
        # it will return you the template for a new client instead of erroring.
        existing_clients = [client['client'] for client in self.run_clients('--me')]
        if not self.client in existing_clients:
            raise Exception("Client not set, set via: --p4-client, p4 set P4CLIENT, or .p4config")

        client = self.run_client('-o', self.client)[0]

        if client['Host'] != socket.gethostname():
            raise Exception(f"Client {self.client} has a Host of {client['Host']}, but curret hostname is {socket.gethostname()}")

        return Path(client['Root'])
