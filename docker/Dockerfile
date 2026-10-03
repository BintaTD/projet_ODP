FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    bash \
    nmap \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# ttyd : terminal dans le navigateur (binaire statique, version et empreinte SHA256 épinglées)
ARG TTYD_VERSION=1.7.7
ARG TTYD_SHA256_X86_64=8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55
ARG TTYD_SHA256_AARCH64=b38acadd89d1d396a0f5649aa52c539edbad07f4bc7348b27b4f4b7219dd4165
RUN set -e; \
    arch="$(uname -m)"; \
    case "$arch" in \
      x86_64) sha="$TTYD_SHA256_X86_64" ;; \
      aarch64) sha="$TTYD_SHA256_AARCH64" ;; \
      *) echo "Architecture non supportée : $arch"; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/ttyd "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.${arch}"; \
    echo "${sha}  /usr/local/bin/ttyd" | sha256sum -c -; \
    chmod 755 /usr/local/bin/ttyd

# Utilisateur non-root (uid fixe : utilisé par le tmpfs du home côté provisioner)
RUN useradd -m -u 1000 -s /bin/bash pentest

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER pentest
WORKDIR /home/pentest

EXPOSE 7681
ENTRYPOINT ["/entrypoint.sh"]
