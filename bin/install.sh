#!/usr/bin/env bash

set -euo pipefail

bindir=$(cd $(dirname "${BASH_SOURCE[0]}") && pwd)
projdir=$(dirname "$bindir")

cd "$projdir"
rm -rf "venv"

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
python setup.py install
