# Experimental loader component audit

On 14 October 2026 the cached BepInEx 5.4.23.5 x64 archive was inspected without running
the game or loader. Its official release digest matched the previous measurement.
The [component inventory](../adapters/i2mono/loader-components.json) records hashes of 13
DLLs, source commits, NuGet comparisons and the hash/source relationships of nine complete
license texts. It contains no game data.

| Component | Source / license notice | Evidence |
| --- | --- | --- |
| BepInEx, Preloader | BepInEx 5.4.23.5 / MIT | Official archive bytes and static assembly version |
| BepInEx.Harmony, HarmonyXInterop, 0Harmony20 | Pinned subproject commit / MIT | Release gitlink and project/assembly mapping |
| 0Harmony | HarmonyX 2.9.0 / two MIT copyright notices | Byte match with official NuGet net35 DLL |
| Mono.Cecil, Mdb, Rocks | Cecil 0.10.4 / MIT | Byte match with official NuGet net35 DLL |
| Mono.Cecil.Pdb | Cecil MIT and Microsoft CCI MS-PL | NuGet byte match and CCI namespace in DLL |
| MonoMod.RuntimeDetour, Utils | 22.1.29.1 and Common subcommit / MIT notices | NuGet net35 byte match and source gitlink |
| winhttp.dll | Doorstop 4.5.0 / LGPL-2.1 text | Byte match with official Doorstop x64 release |

Version selection was checked against the [BepInEx project](https://github.com/BepInEx/BepInEx/blob/v5.4.23.5/BepInEx/BepInEx.csproj)
and [build.cake](https://github.com/BepInEx/BepInEx/blob/v5.4.23.5/build.cake).
Here 0Harmony20 is the [HarmonyX2Interop](https://github.com/BepInEx/BepInEx.Harmony/blob/d4cdcb4cdeac14a0b77012165f5f5a9f5032a9fa/HarmonyX2Interop/HarmonyX2Interop.csproj)
output. The Cecil PDB [CCI source license](https://github.com/jbevain/cecil/blob/0.10.4/symbols/pdb/Microsoft.Cci.Pdb/LICENSE)
and HarmonyX's [original Harmony notice](https://github.com/BepInEx/HarmonyX/blob/v2.9.0/LICENSE.Harmony)
are retained separately. Copying only a root MIT file would omit these notices.

Seven commit-pinned source archives were cached, including the MonoMod.Common and
BepInEx.Harmony subprojects. At that audit stage these archives and DLLs were not added
to source control, CI or the desktop package. License texts preserve the exact bytes from
their upstream sources. UnityTranslator's MIT license does not relicense dependencies.

This audit prepares version/source and notice evidence. A final installable distribution
must separately verify component notice/source availability, package scope and
[Doorstop license conditions](https://github.com/NeighTools/UnityDoorstop/blob/v4.5.0/LICENSE).
It does not prove rebuilding every library reproduces the release DLL hashes. The historical
`redistribution_package_verified=false` and `application_verified=false` flags concern this
audit stage. A concrete file plan, human-approved text, scene/font/hash checks and explicit
game-trial authorization remain separate requirements. See the current source-access and
runtime-kit manifests for later delivery evidence.
