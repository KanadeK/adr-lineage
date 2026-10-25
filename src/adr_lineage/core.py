"""Read-only lifecycle analysis for the adr-tools Markdown convention."""

import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

FILENAME = re.compile(r"^(\d+)-.+\.md$")
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
LINK = re.compile(r"\[[^\]\n]*\]\(([^()\s]+)\)")
RELATION = re.compile(r"^(Superseded by|Supersedes)\s+(.+)$", re.I)
STATES = {"accepted", "proposed", "rejected", "deprecated", "superseded"}
MAX_FILES = 2000
MAX_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


class InputError(ValueError):
    """Input cannot be analyzed reliably."""


def visible_lines(text):
    """Preserve line numbers; ignore fenced/indented code and HTML comments."""
    fence = None
    comment = False
    for number, line in enumerate(text.splitlines(), 1):
        clean = ""
        while line:
            if comment:
                end = line.find("-->")
                if end < 0:
                    break
                line, comment = line[end + 3 :], False
            else:
                start = line.find("<!--")
                if start < 0:
                    clean += line
                    break
                clean += line[:start]
                line, comment = line[start + 4 :], True
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", clean)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                if not clean[marker.end() :].strip():
                    fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        if not clean.startswith(("    ", "\t")):
            yield number, clean


def audit(directory):
    root = Path(directory).resolve()
    if not root.is_dir():
        raise InputError("ADR directory does not exist")
    paths = sorted(p for p in root.iterdir() if FILENAME.fullmatch(p.name))
    if not paths:
        raise InputError("no numbered ADR files (NNNN-title.md) in this directory")
    if len(paths) > MAX_FILES:
        raise InputError(f"maximum {MAX_FILES} ADRs exceeded")
    findings, nodes, declarations = [], {}, []

    def issue(code, path, line, message):
        findings.append(dict(code=code, path=path, line=line, message=message))

    identifiers = {}
    total_bytes = 0
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise InputError(f"not a regular non-symlink file: {path.name}")
        with path.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise InputError(f"ADR exceeds {MAX_BYTES} bytes: {path.name}")
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_BYTES:
            raise InputError("ADR collection exceeds 32 MiB")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError as exc:
            raise InputError(f"ADR is not UTF-8: {path.name}") from exc
        identifier = int(FILENAME.fullmatch(path.name)[1])
        if identifier in identifiers:
            issue("duplicate_id", path.name, 1, f"ID also used by {identifiers[identifier]}")
        identifiers[identifier] = path.name
        status_lines, status_level, status_count = [], None, 0
        title = path.stem
        for line, content in visible_lines(text):
            heading = HEADING.match(content)
            if heading:
                level, label = len(heading[1]), heading[2].strip()
                if level == 1:
                    title = label
                if status_level is not None and level <= status_level:
                    status_level = None
                if label.casefold() == "status":
                    status_count += 1
                    status_level = level
                continue
            if status_level is not None and content.strip():
                status_lines.append((line, content.strip()))
        node = dict(id=identifier, path=path.name, title=title, status="unknown")
        nodes[path.name] = node
        if status_count != 1:
            issue("status_section", path.name, 1, "expected exactly one Markdown Status heading")
        states = set()
        for line, content in status_lines:
            relation = RELATION.fullmatch(content)
            if relation:
                kind = "forward" if relation[1].casefold() == "superseded by" else "reverse"
                if kind == "forward":
                    states.add("superseded")
                links = list(LINK.finditer(relation[2]))
                leftover = LINK.sub("", relation[2]).strip(" ,.;")
                if not links or leftover:
                    issue(
                        "relation_syntax", path.name, line, "expected inline local Markdown links"
                    )
                for link in links:
                    target = unquote(link[1])
                    if (
                        any(char in target for char in ":?#")
                        or any(ord(char) < 32 for char in target)
                        or "\\" in target
                        or target.startswith("/")
                        or "/" in target.removeprefix("./")
                    ):
                        issue(
                            "unsafe_target",
                            path.name,
                            line,
                            "target must be a filename in this directory",
                        )
                        continue
                    target = target.removeprefix("./")
                    if not FILENAME.fullmatch(target):
                        issue("target_format", path.name, line, "target must be NNNN-title.md")
                        continue
                    declarations.append((path.name, target, kind, line))
            elif content.casefold() in STATES:
                states.add(content.casefold())
            else:
                issue(
                    "status_syntax",
                    path.name,
                    line,
                    "unsupported status text; see supported grammar",
                )
        if len(states) != 1:
            issue(
                "status_value",
                path.name,
                status_lines[0][0] if status_lines else 1,
                "expected one unambiguous lifecycle status",
            )
        else:
            node["status"] = next(iter(states))

    edge_evidence = defaultdict(list)
    forward, reverse = set(), set()
    for source, target, kind, line in declarations:
        if target not in nodes:
            issue("missing_target", source, line, f"target does not exist: {target}")
            continue
        edge = (source, target) if kind == "forward" else (target, source)
        bucket = forward if kind == "forward" else reverse
        if edge in bucket:
            issue("duplicate_relation", source, line, f"repeated relationship to {target}")
        bucket.add(edge)
        edge_evidence[edge].append(dict(path=source, line=line, relation=kind))
    edges = sorted(forward | reverse)
    adjacency = {key: [] for key in nodes}
    for old, new in edges:
        evidence = edge_evidence[(old, new)][0]
        adjacency[old].append(new)
        if (old, new) not in forward or (old, new) not in reverse:
            issue(
                "missing_reciprocal",
                evidence["path"],
                evidence["line"],
                f"requires both Superseded by and Supersedes: {old} -> {new}",
            )
        if nodes[old]["status"] != "superseded":
            issue("predecessor_status", old, 1, "a replaced decision must have superseded status")
        if nodes[new]["status"] not in {"accepted", "superseded"}:
            issue("successor_status", new, 1, "replacement must be accepted or superseded")
    for path, node in nodes.items():
        if node["status"] == "superseded" and not adjacency[path]:
            issue("missing_replacement", path, 1, "superseded decision has no existing replacement")

    # Iterative DFS records a concrete directed cycle without Python recursion limits.
    colors = {}
    for origin in nodes:
        if colors.get(origin):
            continue
        stack = [(origin, iter(adjacency[origin]))]
        route, positions = [origin], {origin: 0}
        colors[origin] = 1
        while stack:
            vertex, children = stack[-1]
            child = next(children, None)
            if child is None:
                colors[vertex] = 2
                stack.pop()
                positions.pop(vertex)
                route.pop()
            elif colors.get(child) == 1:
                cycle = route[positions[child] :] + [child]
                issue("cycle", vertex, 1, " -> ".join(cycle))
            elif not colors.get(child):
                colors[child] = 1
                positions[child] = len(route)
                route.append(child)
                stack.append((child, iter(adjacency[child])))

    # A structurally invalid graph must never claim an authoritative current decision.
    current = {}
    if not findings:
        for origin in nodes:
            seen, pending, terminals = set(), [origin], set()
            while pending:
                node = pending.pop()
                if node in seen:
                    continue
                seen.add(node)
                if adjacency[node]:
                    pending.extend(adjacency[node])
                elif nodes[node]["status"] == "accepted":
                    terminals.add(node)
            current[origin] = sorted(terminals)
    return dict(
        schema_version=1,
        valid=not findings,
        nodes=list(nodes.values()),
        edges=[dict(predecessor=a, successor=b, evidence=edge_evidence[(a, b)]) for a, b in edges],
        current=current,
        findings=findings,
    )
