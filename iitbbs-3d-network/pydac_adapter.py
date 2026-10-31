"""
Bridge between the website and PyDAC.

I did not know PyDAC's exact API, so this file is the ONE place to connect it.
- If a module called `pydac` is installed, edit `read_block()` below to call it.
- If not (or if it fails), the site falls back to realistic SIMULATED data so the
  3D map always works.

read_block(building) must return a dict with:
  latency_ms, loss_pct, down_mbps, up_mbps, clients, aps_online, aps_total
"""
try:
    import pydac  # noqa: F401
    HAVE_PYDAC = True
except Exception:
    HAVE_PYDAC = False


def read_block(building):
    """Return live metrics for one building, or None to use the simulator."""
    if not HAVE_PYDAC:
        return None
    # TODO: replace with your real PyDAC calls, for example:
    # data = pydac.measure(host=building["host"])
    # return {"latency_ms": data.rtt, "loss_pct": data.loss, ...}
    return None
