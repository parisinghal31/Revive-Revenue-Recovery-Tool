"""One-command, zero-key proof run.

    python demo.py            # 500 synthetic failures, seed 42
    python demo.py --n 500 --seed 42

Runs the full decision engine + guardrails over a synthetic failure batch on a
FRESH isolated database (never touches interactive state), prints the measured
outcome, and writes ../results/batch_report.json. The run is deterministic:
same n + seed => byte-identical numbers, on any machine, with no API keys.
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Windows consoles default to cp1252, which cannot encode the rupee sign this
# script prints; the docstring promises it runs on any machine, so force UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# isolated DB + force the deterministic path BEFORE importing the app
os.environ["REVIVE_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="revive-demo-")) / "demo.db")
for var in ("GROQ_API_KEY", "GEMINI_API_KEY", "TWILIO_SID", "TWILIO_TOKEN",
            "META_WA_TOKEN", "CALLMEBOT_APIKEY", "TEXTMEBOT_APIKEY",
            "VAPI_SIP_NUMBER_ID", "CUSTOMER_SIP_URI"):
    os.environ.pop(var, None)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import simulator  # noqa: E402


def rupees(paise: int) -> str:
    return f"₹{paise / 100:,.0f}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Revive reproducible batch run")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print(f"Running {args.n} synthetic failures (seed={args.seed}) through the "
          f"decision engine + guardrails…\n")
    r = simulator.run_batch(n=args.n, seed=args.seed)

    print(f"  At risk            {rupees(r['at_risk_paise'])}")
    print(f"  Recovered          {rupees(r['recovered_paise'])}  ({r['recovered_count']} payments)")
    print(f"  Recovery yield     {r['yield_pct']}%")
    print(f"  Fraud suppressed   {r['suppressed_fraud']['count']} cases "
          f"({rupees(r['suppressed_fraud']['paise'])} deliberately NOT chased)")
    print(f"  Outage handling    {r['outage_handled']['held_then_released']} "
          f"{r['outage_handled']['bank']} retries held during outage, released on recovery")
    print(f"  Honest losses      {r['honest_losses']['count']} cases "
          f"({rupees(r['honest_losses']['paise'])}) — reported, not hidden")

    out = Path(__file__).resolve().parent.parent / "results" / "batch_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(r, indent=2))
    print(f"\nReport written to {out.relative_to(out.parent.parent)}")
    print("Re-run with the same seed to verify these numbers reproduce exactly.")


if __name__ == "__main__":
    main()
