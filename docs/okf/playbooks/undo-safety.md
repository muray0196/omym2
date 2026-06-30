---
type: OMYM2 Execution Playbook
title: Undo safety
description: Navigation guide for undo through Run and FileEvent history.
tags: [execution, undo, safety, file-event]
authoritative: false
canonical_docs:
  - ../../execution/undo.md
  - ../../execution/model.md#fileevent-behavior
  - ../../contracts/path-identity-storage.md#absolute-external-path-exceptions
---

# Undo Safety

Undo is planned from a Run by tracing successful FileEvents in reverse order, creating an undo Plan, and applying that Plan. It does not bypass Plan-centered execution, including conflict review and external restore path handling.

## Authoritative sources

- [Undo execution](../../execution/undo.md)
- [FileEvent behavior](../../execution/model.md#fileevent-behavior)
- [Absolute external path exceptions](../../contracts/path-identity-storage.md#absolute-external-path-exceptions)

## Relationships

- [Run](../concepts/run.md) is the execution history unit undo starts from.
- [FileEvent](../concepts/file-event.md) provides the mutation history.
- [Plan-centered apply](plan-centered-apply.md) still applies the undo Plan.

## Agent notes

- Do not implement undo as direct filesystem mutation.
- Preserve the distinction between Library-relative managed paths and allowed external restore targets.
