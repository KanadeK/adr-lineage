import argparse
import json
import sys

from .core import InputError, audit


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit adr-tools supersession links offline.")
    parser.add_argument("directory", help="flat directory of NNNN-title.md records")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument(
        "--resolve", type=int, metavar="ID", help="show accepted terminal replacements"
    )
    parser.add_argument("--version", action="version", version="adr-lineage 0.1.2")
    args = parser.parse_args(argv)
    try:
        report = audit(args.directory)
        if args.resolve is not None:
            matches = [n for n in report["nodes"] if n["id"] == args.resolve]
            if len(matches) != 1:
                raise InputError("--resolve ID must identify exactly one record")
            report["resolution"] = dict(
                source=matches[0]["path"],
                current=report["current"].get(matches[0]["path"]),
            )
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=True, indent=2))
        else:
            print(
                f"{len(report['nodes'])} ADRs, {len(report['edges'])} replacement edges, "
                f"{len(report['findings'])} findings"
            )
            for finding in report["findings"]:
                print(
                    f"{finding['path']}:{finding['line']}: {finding['code']}: {finding['message']}"
                )
            if "resolution" in report:
                resolution = report["resolution"]
                current = resolution["current"]
                display = ", ".join(current) if current else "no accepted terminal decision"
                if current is None:
                    display = "unavailable: graph is invalid"
                print(f"{resolution['source']} -> {display}")
        return 0 if report["valid"] else 1
    except (InputError, OSError, UnicodeError) as exc:
        if args.format == "json":
            print(json.dumps(dict(schema_version=1, error=str(exc)), ensure_ascii=True))
        else:
            print(f"adr-lineage: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
