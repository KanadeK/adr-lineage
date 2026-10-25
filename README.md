# adr-lineage

Find the current architecture decision behind an old ADR, and catch broken replacement
chains before a teammate relies on them. A small, offline, read-only CLI for the
numbered Markdown convention used by [adr-tools](https://github.com/npryce/adr-tools).

## Install and try

Requires Python 3.11+. There are no runtime dependencies and no network requests.

```sh
git clone https://github.com/KanadeK/adr-lineage.git
cd adr-lineage
python -m venv .venv
# POSIX: source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
adr-lineage examples/decisions --resolve 1
adr-lineage examples/decisions --format json
```

Expected first result: 3 ADRs, 2 replacement edges, 0 findings, and
`0001-local-cache.md -> 0003-managed-cache.md`. The sample files are synthetic.
Try removing the `Supersedes` line from ADR 3: the checker exits 1 and names the
missing reciprocal edge. Restore the example before rerunning.

Uninstall with `python -m pip uninstall adr-lineage`; delete the virtual environment
when no longer needed. The tool creates no cache or state files.

## Supported input

Pass one flat directory. Only files named `NNNN-title.md` are read (any length of
decimal ID is accepted); README files and subdirectories are ignored. IDs must be
unique. Every record needs exactly one ATX Markdown `Status` heading. Status content
ends at the next heading of the same or higher level.

```markdown
## Status

Superseded by [3. Managed cache](0003-managed-cache.md)
Supersedes [1. Local cache](0001-local-cache.md)
```

The terminal replacement instead has `Accepted` plus its `Supersedes` line.
Supported standalone states: `Proposed`, `Accepted`, `Rejected`, `Deprecated`,
`Superseded` (case insensitive). `Superseded by` implies the superseded state.
Multiple links on a relation line may be separated by commas; multiple relation
lines are also supported. Links must be inline links to local numbered filenames;
`./` and percent-encoded filename characters are allowed. No URL, fragment, query,
subdirectory or parent traversal is accepted.

Fenced/indented code, HTML comments and relations outside Status are ignored.
Unsupported status prose or reference-style links are findings, never silently
treated as a valid chain. This intentionally supports a small documented grammar,
not arbitrary CommonMark or YAML frontmatter. Convert other ADR conventions before
using it. It does not edit any records.

## What is checked

- Missing or duplicate IDs/Status sections; ambiguous or unknown lifecycle state.
- Missing targets, duplicate edges and missing reciprocal links.
- A replaced record must be superseded; its successor must be accepted or superseded.
- Superseded records need a replacement; cycles include a concrete path witness.
- Valid chains resolve to **all** accepted terminal successors, preserving branching.
  Deprecated, rejected and proposed terminal records have no accepted resolution.

Any finding invalidates resolution for the entire directory. Fix the reported
graph before treating the `current` map as authoritative. This does not decide
whether the architectural reasoning or implementation is correct.

## Automation

```sh
adr-lineage doc/adr --format json > lineage.json
```

Exit codes: **0** valid graph, **1** lifecycle/relationship findings, **2** input or
environment error (including absent/ambiguous `--resolve` IDs). JSON schema version
1 includes `nodes`, `edges` with source-line evidence, `current`, and `findings`.
Input errors contain an `error` string. Argparse usage errors go to stderr.

Maximum 2,000 records, 1 MiB per record, 32 MiB in total. UTF-8 (optional BOM) is required.
Symlink records are rejected. Runtime is bounded by graph size; resolving every
record can take quadratic time on long chains. Output contains supplied titles and
filenames; inspect it before sharing. No GitHub token is needed.

## Why a separate tool?

adr-tools and [adrs](https://github.com/joshrotenberg/adrs) are broader authoring tools.
adr-lineage is a focused integrity gate and handover lookup for existing files,
with machine-readable witnesses and no changes to a team's authoring workflow.
No code or templates from those projects are bundled. See [CONTRIBUTING](CONTRIBUTING.md)
for tests and [SECURITY](SECURITY.md) for reporting. MIT license.

## 中文说明

离线检查 adr-tools 风格的架构决策替代关系，发现缺失目标、单向链接、错误状态和循环，
并从旧 ADR 找到所有当前有效的后继决策。只读、不联网、无需 Token。
支持范围是单层目录中的编号 Markdown 和 Status 段；不支持任意 YAML 前置信息。
发现任何结构问题时不会给出有效决策结论。安装、示例和退出码见上文。
