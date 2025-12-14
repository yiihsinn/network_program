#!/bin/bash
# HW3 Game Store - Player Client
cd "$(dirname "${BASH_SOURCE[0]}")"
python3 client/player_client.py "$@"
