#!/usr/bin/env python3
"""Minimal Docker Engine API unix-socket -> TCP bridge for Docker Desktop.

WHY THIS EXISTS
---------------
Docker Desktop for Windows cannot bind-mount the Docker Engine unix socket
into containers: the socket file is materialised as a regular file (verified
on this host - connect() returns ECONNREFUSED and stat shows a regular file).
Traefik's docker provider therefore needs the engine API over TCP.

This script forwards 127.0.0.1:LPORT -> /var/run/docker.sock. Run it inside
the WSL distro that Docker Desktop integrates with (here: Ubuntu-26.04,
which exposes the engine socket at /var/run/docker.sock). Docker containers
then reach it via http://host.docker.internal:23750 (Windows' WSL
localhost-forwarding carries the connection).

RUN
---
    wsl -d Ubuntu-26.04 -- python3 /mnt/c/<repo>/traefik/host-services/dockerd-socket-tcp-bridge.py
    # (add to a WSL [boot] command or your session start if it must
    # survive reboots; it is a single foreground process)

SECURITY
--------
* Binds to 127.0.0.1 ONLY - not reachable from the LAN.
* There is NO read-only mode for the Docker Engine API over TCP. Anything
  that can reach that port (every container on this host, host processes)
  can execute arbitrary docker engine commands: start containers, read
  other containers' logs, mount volumes, ...
* This bridge is acceptable for THIS machine's local development phase
  while Traefik's docker provider is needed. It is NOT acceptable on a
  multi-tenant or internet-reachable machine.
* Kill it when Traefik is not running:
      wsl -d Ubuntu-26.04 -- pkill -f dockerd-socket-tcp-bridge.py

SAFER ALTERNATIVES (documented for the future extraction repo)
---------------------------------------------------------------
1. Run Traefik on a host where a read-only unix socket mount works
   (plain Linux Docker daemon): mount /var/run/docker.sock:ro. Still a
   full-privilege API, but constrained to the host network and auditable.
2. Run Traefik's docker provider against a restricted API proxy (e.g. a
   thin reverse proxy that allows only GET /containers, GET /v1.x/networks,
   socket events on specific labels) - Traefik only needs container list /
   labels / events.
3. Drop the docker provider and use Traefik's FILE provider with
   host-rules on a shared network (no socket needed at all) - the least
   dynamic option (routes are static per deploy).
"""
import os
import socket
import threading

LHOST = "127.0.0.1"
LPORT = int(os.environ.get("DOCKER_BRIDGE_PORT", "23750"))
DOCKER_SOCK = "/var/run/docker.sock"


def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    try:
        dst.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LHOST, LPORT))
    srv.listen(64)
    print(f"docker API bridge: {LHOST}:{LPORT} -> unix:{DOCKER_SOCK}",
          flush=True)
    while True:
        client, _ = srv.accept()
        try:
            unix_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            unix_sock.connect(DOCKER_SOCK)
        except OSError:
            client.close()
            continue
        threading.Thread(target=pipe, args=(client, unix_sock),
                         daemon=True).start()
        threading.Thread(target=pipe, args=(unix_sock, client),
                         daemon=True).start()


if __name__ == "__main__":
    main()
