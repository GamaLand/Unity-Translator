"""Audit known preloader CIL write paths without executing the CLR."""

import argparse
import json
from pathlib import Path

import dnfile
from audit_managed_calls import audit
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBytes
from dncil.clr.token import Token

from unitytranslator.filesystem import checked_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--portable", action="store_true")
    args = parser.parse_args()
    assembly, output = map(checked_path, (args.assembly, args.output))
    root = Path(__file__).resolve().parents[1]
    if not output.is_relative_to(root):
        raise ValueError("Statik rapor çalışma alanında olmalı.")
    result = audit(
        assembly,
        [
            "Doorstop.Entrypoint.Start",
            "BepInEx.Preloader.PreloaderRunner.PreloaderPreMain",
            "BepInEx.Preloader.Preloader.Run",
            "BepInEx.Preloader.ProtectedRuntimeDiagnostics.TryWrite",
        ],
    )
    calls = result["external_calls"]
    denied = {
        "System.IO.File.WriteAllBytes",
        "System.IO.File.WriteAllText",
        "HarmonyXInterop.HarmonyInterop.Initialize",
        "HarmonyXInterop.HarmonyInterop.TryShim",
    }
    pe = dnfile.dnPE(str(assembly))
    try:
        references = [str(item.Name) for item in pe.net.mdtables.AssemblyRef.rows]
        create_modes = []
        diagnostic_opcodes = []
        for kind in pe.net.mdtables.TypeDef.rows:
            if str(kind.TypeName) != "ProtectedRuntimeDiagnostics":
                continue
            for method in kind.MethodList:
                if str(method.row.Name) != "TryWrite":
                    continue
                body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(method.row.Rva)))
                diagnostic_opcodes = [str(instruction.opcode) for instruction in body.instructions]
                for index, instruction in enumerate(body.instructions):
                    operand = instruction.operand
                    if (
                        str(instruction.opcode) != "newobj"
                        or not isinstance(operand, Token)
                        or operand.value >> 24 != 10
                    ):
                        continue
                    member = pe.net.mdtables.MemberRef.rows[(operand.value & 0xFFFFFF) - 1]
                    if str(getattr(member.Class.row, "TypeName", "")) == "FileStream":
                        create_modes.append(
                            [str(i.opcode) for i in body.instructions[index - 3 : index]]
                        )
    finally:
        pe.close()
    guarded_entry = next(
        value
        for key, value in result["methods"].items()
        if key.startswith("Doorstop.Entrypoint.Start:")
    )
    checks = {
        "known_persistent_calls_absent": not denied.intersection(calls),
        "interop_assembly_reference_absent": "HarmonyXInterop" not in references,
        "diagnostic_policy_valid": (
            diagnostic_opcodes == ["ldc.i4.0", "ret"]
            if args.portable
            else create_modes == [["ldc.i4.1", "ldc.i4.2", "ldc.i4.0"]]
        ),
        "external_runtime_entry_guard_present": any(
            item["target"].endswith("ProtectedRuntimeDiagnostics.IsExternalRuntime")
            for item in guarded_entry
        ),
        "reparse_inspection_present": "System.IO.File.GetAttributes" in calls,
    }
    report = {
        "static_checks": checks,
        "static_checks_passed": all(checks.values()),
        "application_verified": False,
        "game_executed": False,
        "assembly_sha256": result["assembly_sha256"],
        "graph": result,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "graph"}, indent=2))
    return 0 if report["static_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
