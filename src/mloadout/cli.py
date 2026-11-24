"""The `mloadout` command: one subcommand per job."""

from __future__ import annotations

import argparse
import sys

from mloadout import __version__, bootstrap


def build_parser() -> argparse.ArgumentParser:
    """
    Build the top-level parser with every subcommand registered

    **Returns**:
        The parser for the `mloadout` command

    **Examples**:
        >>> build_parser().parse_args(["bootstrap", "--dry-run"])
        Each subcommand stores the function that runs it in `handler`, so new
        jobs (such as the ADR 0003 comparison runner) are added as new subparsers.
    """
    parser = argparse.ArgumentParser(
        prog="mloadout",
        description="Generic personal dev setup, starting with pinned Agent Skills.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subcommands = parser.add_subparsers(
        title="commands", metavar="<command>", required=True
    )

    bootstrap_parser = subcommands.add_parser(
        "bootstrap",
        help="link pinned Agent Skills into ~/.agents/skills (ADR 0002)",
        description=(
            "Fetch each skill source at its pinned commit and link the selected skills "
            "into the shared skills directory. Nothing changes unless every check passes."
        ),
    )
    bootstrap.add_arguments(parser=bootstrap_parser)
    bootstrap_parser.set_defaults(handler=bootstrap.run)
    return parser


def main(argv: list[str] | None = None) -> int:
    """
    Run the `mloadout` command

    **Args**:
        **argv** (*list[str] | None*): arguments after the program name, or None to read sys.argv

    **Returns**:
        The process exit code

    **Examples**:
        >>> main(argv=["bootstrap", "--dry-run"])
        Parses the arguments and hands them to the chosen subcommand.
    """
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
