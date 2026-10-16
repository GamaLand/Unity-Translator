# Experimental preloader source traceability

`tools/stage_protected_source.py` verifies the official BepInEx source archive's catalog
hash and the protected build evidence. It compares every archived file with the build
source tree. Three registered modifications are accepted only when their upstream and
post-change hashes match the evidence. Added sources are limited to the diagnostics helper
and bounded version information. Extra files, missing licenses, unregistered changes or a
different binary are rejected. The registered Windows CRLF and LF version files are both
accepted; other content is not. Source copies retain their original line endings.

The package contains the complete modified source tree, matching preloader binary, both
MIT notices, protection notes, the build tool and sanitized build evidence. Run the tool
inside a UnityTranslator checkout; the source package alone is not a standalone build
environment. References record filenames/SHA-256 only, and the compiler records SHA-256
only. No game DLLs, user translations, models or machine-specific paths are included.
Failed copies retain a `failed` manifest inside the project, without writing into the game.

```powershell
python tools/stage_protected_source.py --game <game> --project <separate-project> --build <protected-build> --archive <official-source.zip>
```

Historical evidence, 14 October 2026: a protected build using legacy Mono references was
prepared without changing the eight reference hashes. Five static protection checks passed
without executing the game/loader CLR. A local source package contained 108 files and a
manifest; all 109 ZIP entries, CRCs and content hashes were verified. Its binary hash matched
the preloader used in the corresponding five-record project-local trial.

That evidence does not establish identical-hash reproducible builds, every loader side
effect, final redistribution compliance or general in-game compatibility. BepInEx and
UnityTranslator MIT notices retain their respective owners. Other loader dependencies
have separate sources/licenses in the loader support package. Historical flags such as
`installation_authorized=false`, `application_verified=false` and
`redistribution_package_verified=false` describe that preparation stage, not a later
installation approval. The portable variant is separately cataloged and traced.
