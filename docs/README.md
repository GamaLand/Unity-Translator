# Documentation

Current checkout: 0.6.0. Unity installation remains fingerprint-bound. Initial
Ren'Py templates, audited original-source behavior, `_ren.py`, large disjoint source
sets, shared review and sharded native staging are implemented in source. The
experimental installation ZIP adds approved text and helpers without copying the
game, retaining its pinned runtime gate. See Compatibility for evidence and limits;
legacy translated-copy packages remain supported.

## Start here

1. [Development](development.md): current architecture, shared review rules, Ren'Py
   backend/UI design, ordered acceptance gates and deferred Unity/Unreal work.
   The next milestone is [broader Ren'Py support](development.md#broader-renpy-support-planned),
   including remaining syntax, overlapping sources and wider runtime families.
2. [Compatibility](compatibility.md): implemented support, limitations and historical
   release evidence. A roadmap is not a compatibility claim.
3. [Installation](installation.md): original-file protection, project-managed and
   shareable Unity patches, ownership and recovery.

## Reference documents

| Document | Purpose |
| --- | --- |
| [User guides](../guide/en.md) | Everyday use in eight languages; Windows quick start is [README-WINDOWS.md](README-WINDOWS.md) |
| [Runtime components](runtime-components.md) | Unity/I2 and Krypta runtime contracts, fixed hooks and build/source chain |
| [Windows packaging](windows-package.md) | Build, verify and distribute new Windows candidates |
| [Dependencies](dependencies.md) | Recorded dependency versions and purposes |
| [Native notices](NATIVE-NOTICES.md) | Native redistribution notices |
| [Source access](SOURCE-ACCESS.md) | Matching application/component/dependency sources for binary releases |
| [Loader audit](loader-component-audit.md) | Versioned upstream component provenance |
| [Protected source trace](protected-source-trace.md) | Modified preloader source/binary correspondence |

Architecture, roadmap and quality notes are consolidated in Development; release
evidence in Compatibility; shareable patches in Installation; the Krypta design in
Runtime components. Maintain those documents rather than parallel plans or diaries.
Localized guides, original licenses and detailed source/provenance records remain
separate because users and distribution tooling need them.
