# Seat driver: native-only (no external council)

The supported "no external lineage" mode. `seats.json` is written with an empty list:

```json
{ "seats": [] }
```

What still works — the entire council discipline minus lineage diversity:
- Deterministic risk gate (`council.py risk`) and the Stop-hook nudge/override/ledger flow.
- Reviews run as **independent native Claude subagents** (Sonnet via the Agent tool), blind
  and parallel: low=1, elevated=2, high=3, critical=3 + human sign-off.
- Reviewer-assigned severity, evidence-based rejection, re-review cap, reject-audit — unchanged.

What is lost: cross-lineage blind-spot coverage (a Claude-family model reviewing a
Claude-family author shares its training-correlated failure modes). The SKILL requires the
orchestrator to state this caveat in every native-only council report.

No install, no auth, no smoke test needed. This mode is also the automatic fallback whenever
all external seats fail at runtime.
