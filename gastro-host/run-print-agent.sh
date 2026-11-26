#!/usr/bin/env bash
# Bondruck-Agent auf dem Stations-Terminal (Ubuntu).
# Drucker muss in CUPS als Standard (am besten Raw) eingerichtet sein.
cd "$(dirname "$0")"
export GASTRO_PRINT_PORT="${GASTRO_PRINT_PORT:-9109}"
export GASTRO_PRINT_BIND="${GASTRO_PRINT_BIND:-0.0.0.0}"
# optional: export GASTRO_PRINTER_NAME="HP_A798"
exec python3 print_agent.py
