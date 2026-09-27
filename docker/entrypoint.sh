#!/bin/bash
set -e

if [ -n "$SSH_PUBLIC_KEY" ]; then
    echo "$SSH_PUBLIC_KEY" > /home/pentest/.ssh/authorized_keys
    chmod 644 /home/pentest/.ssh/authorized_keys
fi

exec /usr/sbin/sshd -D -e
