"""Write the audit report to an HTML file the user can open, save or send.

    python -m scripts.export_report                       # -> reports/compliance-audit-report.html
    python -m scripts.export_report path/to/report.html
"""
import sys
from pathlib import Path

from seam.client import SeamClient

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "compliance-audit-report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(SeamClient().report(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
