#!/bin/bash
set -e
# Terminal web : un seul client à la fois, en écriture. L'accès passe par Traefik.
exec ttyd --writable --port 7681 --max-clients 1 bash
