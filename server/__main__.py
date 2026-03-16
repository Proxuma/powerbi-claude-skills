"""CLI entry point for deanonymization.

Usage:
    python -m server.deanonymizer report.html -o report-final.html
    python -m server.deanonymizer report.html --mapping path/to/mapping.json -o out.html
"""

import argparse
import sys
from pathlib import Path

from server.deanonymizer import deanonymize_file


def main():
    parser = argparse.ArgumentParser(description="Deanonymize a Power BI report")
    parser.add_argument("input", type=Path, help="Input HTML file (anonymized)")
    parser.add_argument(
        "-o", "--output", type=Path, required=True,
        help="Output HTML file (deanonymized)",
    )
    parser.add_argument(
        "--mapping", type=Path, default=None,
        help="Path to mapping.json (default: ~/.powerbi-mcp/sessions/latest/mapping.json)",
    )
    args = parser.parse_args()

    mapping_path = args.mapping
    if mapping_path is None:
        mapping_path = Path.home() / ".powerbi-mcp" / "sessions" / "latest" / "mapping.json"

    if not mapping_path.exists():
        print(f"Error: mapping file not found: {mapping_path}", file=sys.stderr)
        sys.exit(1)

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    deanonymize_file(args.input, mapping_path, args.output)
    print(f"Deanonymized report saved to {args.output}")


if __name__ == "__main__":
    main()
