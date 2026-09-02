"""Punct de intrare: fara argumente porneste interfata grafica, cu argumente CLI-ul."""

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from .cli import main as cli_main
        return cli_main()
    from .gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
