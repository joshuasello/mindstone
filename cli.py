#!/usr/bin/env python3
""" commandline access point.

"""


import argparse

from mindstone import __version__, Worker


def run_worker(namespace):
    Worker().serve(port=namespace.port, connection_type=namespace.conntype)


parser = argparse.ArgumentParser(
    prog="mindstone cli",
    description="."
)
parser.version = __version__
parser.add_argument(
    "-V",
    "--version",
    action="version",
    help="Gets the current running version of mindstone."
)
subparsers = parser.add_subparsers()
# create the parser for the "worker" command
parser_run_worker = subparsers.add_parser("run_worker", help="Creates a new worker and runs it.")
parser_run_worker.add_argument("--port", action="store", type=int, help="The connection port number.", default=50000)
parser_run_worker.add_argument("--conntype", action="store", type=str, help="The type of connection used.",
                               default="tcp")
parser_run_worker.set_defaults(func=run_worker)

args = parser.parse_args()

if __name__ == '__main__':
    args.func(args)
