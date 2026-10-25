# Changelog

## 0.1.1

- Keep HTML comment markers inside fenced examples inert, so they cannot hide
  real replacement links after a code fence. Includes a regression test.

## 0.1.0

- Audit numbered adr-tools-style Markdown lifecycle graphs without changing files.
- Report reciprocal-link gaps, missing targets, conflicting states and cycle witnesses.
- Resolve accepted terminal replacements through branching chains.
- Provide text/JSON CLI output with explicit failure codes and bounded input.

Initial limitations: flat directories, documented Status grammar only, no YAML
frontmatter or general Markdown link resolution, no assessment of architectural correctness.
