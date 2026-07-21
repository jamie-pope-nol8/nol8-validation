#!/usr/bin/env python3
"""Decompose per-request latency to isolate raw engine processing time.

The end-to-end benchmark number (~7 ms/chunk) is mostly NOT the engine: the
adapter opens a fresh TLS connection per call, so each call pays a TLS handshake
plus a network round-trip. This tool measures the path in layers from the field
client box and subtracts everything that isn't the engine, bounding the raw
server-side processing time.

Run on EC2 (reaches the data planes):
    set -a; source .env; set +a
    python3 demos/benchmark/latency-decompose.py            # text
    python3 demos/benchmark/latency-decompose.py out.json   # + JSON summary

Layers (over N iterations; ITERS env overrides N):
  tcp_rtt  socket connect = one network round-trip (the network floor)
  warm     request on a REUSED keep-alive TLS connection = 1 RTT + processing
  cold     request on a NEW connection each time = TLS handshake + 1 RTT + proc
           (this is exactly what the current adapter does)
Derived:
  tls_setup  = cold - warm     per-call TLS+TCP handshake tax (removable by pooling)
  processing = warm - tcp_rtt  server-side work, network-adjusted (an upper bound;
               clamped at 0 - it lands in the network jitter, i.e. sub-millisecond)
"""
import http.client, ssl, socket, time, json, os, statistics, sys

HOST = "tenant001-v1demo.nol8.net"
N = int(os.environ.get("ITERS", "100"))
BIG = {"message": ("Escalate Red Flag Logistics for the Redwood Identity "
                   "workflow from 203.0.113.45 card 4111 1111 1111 1111 " * 8)}


def med(xs):
    return round(statistics.median(xs), 3)


def _post_loop(mk_conn, port, token, reuse):
    ctx = ssl.create_default_context()
    body = json.dumps(BIG).encode()
    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    out = []
    c = mk_conn(ctx, port) if reuse else None
    if reuse:
        c.request("POST", "/v1/process", body, hdr); c.getresponse().read()  # prime
    for _ in range(N):
        t0 = time.perf_counter()
        conn = c if reuse else mk_conn(ctx, port)
        conn.request("POST", "/v1/process", body, hdr)
        conn.getresponse().read()
        out.append((time.perf_counter() - t0) * 1000)
        if not reuse:
            conn.close()
    if reuse:
        c.close()
    return out


def measure(name, port, token):
    mk = lambda ctx, p: http.client.HTTPSConnection(HOST, p, context=ctx, timeout=10)
    tcp = []
    for _ in range(N):
        t0 = time.perf_counter()
        s = socket.create_connection((HOST, port), timeout=10)
        tcp.append((time.perf_counter() - t0) * 1000); s.close()
    warm = _post_loop(mk, port, token, reuse=True)
    cold = _post_loop(mk, port, token, reuse=False)
    m_tcp, m_warm, m_cold = med(tcp), med(warm), med(cold)
    tls = round(max(0.0, m_cold - m_warm), 3)
    proc = round(max(0.0, m_warm - m_tcp), 3)
    return {
        "engine": name, "port": port, "iters": N,
        "network_rtt_ms": m_tcp, "warm_ms": m_warm, "cold_ms": m_cold,
        "tls_setup_ms": tls, "processing_ms": proc,
        "processing_pct_of_cold": round(proc / m_cold * 100, 1) if m_cold else 0.0,
    }


def show(r):
    print(f"\n=== {r['engine']} (port {r['port']}, N={r['iters']}) ===")
    print(f"  network RTT (floor)      : {r['network_rtt_ms']:.3f} ms")
    print(f"  warm  (pooled TLS)       : {r['warm_ms']:.3f} ms   = 1 RTT + processing")
    print(f"  cold  (TLS/call)         : {r['cold_ms']:.3f} ms   <- adapter does this")
    print(f"  --------------------------------------------")
    print(f"  TLS/conn setup tax       : {r['tls_setup_ms']:.3f} ms/call  (removable by pooling)")
    print(f"  ENGINE processing        : <= {r['processing_ms']:.3f} ms  "
          f"({r['processing_pct_of_cold']:.1f}% of cold; rest is transport)")


if __name__ == "__main__":
    results = [
        measure("THEMIS (FPGA)", 443, os.environ["THEMIS_TOKEN"]),
        measure("AERGIA", 444, os.environ["AERGIA_TOKEN"]),
    ]
    for r in results:
        show(r)
    if len(sys.argv) >= 2:
        with open(sys.argv[1], "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nwrote {sys.argv[1]}")
