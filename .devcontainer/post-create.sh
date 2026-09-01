#!/usr/bin/env bash
# Runs once, after the container is created.
set -euo pipefail

echo "presto-deck devcontainer"
echo "  python   $(python --version 2>&1 | cut -d' ' -f2)"
echo "  mpremote $(mpremote version 2>&1 | awk '{print $NF}')"
echo "  ruff     $(ruff --version | awk '{print $2}')"
echo

# Serial access is the one thing that can't be fixed from inside a running
# container, so check it here rather than letting mpremote fail cryptically.
ports=(/dev/ttyACM* /dev/ttyUSB*)
if [[ -e ${ports[0]} ]]; then
    for port in "${ports[@]}"; do
        [[ -e $port ]] || continue
        group=$(stat -c '%G:%g' "$port")
        if [[ -r $port && -w $port ]]; then
            echo "  $port  readable (group $group)"
        else
            echo "  $port  NOT accessible - it is group $group, and this user"
            echo "         is in $(id -Gn | tr ' ' ',')."
            echo "         Set SERIAL_GID in .devcontainer/devcontainer.json to"
            echo "         ${group#*:} and rebuild the container."
        fi
    done
else
    echo "  No serial device attached. Plug the Presto in and run"
    echo "  'mpremote devs' to check it is visible."
fi

echo
echo "  Tests:  pytest"
echo "  Deploy: cd simhub-dashboard && mpremote cp device/*.py :"
