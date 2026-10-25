# 1. Keep a local cache

## Status

Superseded by [2. Shared cache](0002-shared-cache.md)

## Context

The demo service initially ran as one process.

## Decision

Use process-local memory for disposable cached results.

## Consequences

Each process has a separate view.
