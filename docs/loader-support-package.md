# Offline loader support package

`stage_loader_support` verifies selected local loader files, cached sources and the
developer catalog by hash. It creates a unique `artifacts/loader-support-<id>` folder
inside the project. It does not write game files, execute a loader/DLL, start a model/game
or access the network.

The package includes loader DLLs, license notices, commit-pinned source ZIPs, the component
catalog, instructions and a support manifest. Every file has a hash, size and kind. Sources
are copied; original game files and assemblies are excluded. Relative paths are confined
to their source roots. Path escapes, reparse points, duplicate targets, missing licenses,
oversized files and hash mismatches stop the operation. This is not an activation manifest.

A failed preflight creates no output. A copy failure leaves a `failed` package rather than
reporting it ready. Existing packages are not overwritten. No source or game file is
rewritten or deleted.

```powershell
python tools/stage_loader_support.py --game <game> --project <separate-project> --loader <local-loader> --source-cache <local-source-cache>
```

Historical evidence, 14 October 2026: a 31-file package was prepared from the verified
development cache: 13 DLLs, nine licenses, seven source ZIPs, a catalog and instructions.
All manifest hashes and source archive CRCs were checked again. Synthetic tests cover
copy integrity, source preservation, path traversal, missing notices, changed hashes and
partial copy failures. That audit did not publish the package or put DLL/source archives
into the source repository or CI.

This support package does not include a plugin, translation, Doorstop/BepInEx runtime
configuration or activation plan. It is not an installable game patch and must not be
copied into a game folder. Its preparation-stage `application_verified`,
`installation_authorized` and `redistribution_package_verified` flags remain false.
A final mod distribution needs its own source-access/notices review, fingerprint/conflict
plan and game validation. Installing any actual trial requires explicitly approved
translations and a separately approved file plan.
