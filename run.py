"""Ponto de entrada usado pelo PyInstaller (e por quem quiser rodar `python run.py`)."""

import sys

from baixador.gui.app import run

if __name__ == "__main__":
    sys.exit(run())
