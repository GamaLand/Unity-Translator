"""Geliştirme aracı: CLR yüklemeden CIL çağrı grafiği; dinamik davranış kanıtı değildir."""

import argparse
from pathlib import Path

import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBytes
from dncil.clr.token import Token

from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file
from unitytranslator.json_boundary import strict_json


def audit(path: Path, names: list[str]) -> dict:
    path = checked_path(path)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Assembly boyut sınırı aşıldı.")
    before = hash_file(path)
    pe = dnfile.dnPE(str(path))
    try:
        owners = {}
        methods = {}
        for kind in pe.net.mdtables.TypeDef.rows:
            owner = str(kind.TypeNamespace) + "." + str(kind.TypeName)
            for method in kind.MethodList:
                token = 0x06000000 | method.row_index
                owners[token] = owner + "." + str(method.row.Name)
                methods[token] = method.row
        queue = [token for token, name in owners.items() if name in names]
        if {owners[token] for token in queue} != set(names):
            raise ValueError("İstenen metotların tamamı bulunamadı.")
        roots = list(queue)
        graph = {}
        unresolved = []
        external = set()

        def resolve(value):
            table, index = value >> 24, (value & 0xFFFFFF) - 1
            if table == 6:
                return owners[value], value
            if table == 0x2B:
                reference = pe.net.mdtables.MethodSpec.rows[index].Method
                nested = (reference.table.number << 24) | reference.row_index
                return resolve(nested)
            if table == 10:
                row = pe.net.mdtables.MemberRef.rows[index]
                kind = row.Class.row
                owner = (
                    str(getattr(kind, "TypeNamespace", "<generic>"))
                    + "."
                    + str(getattr(kind, "TypeName", "<generic>"))
                )
                return owner + "." + str(row.Name), None
            return "unresolved:" + hex(value), None

        while queue:
            token = queue.pop()
            if token in graph:
                continue
            if len(graph) >= 5000:
                raise ValueError("Çağrı grafiği sınırı aşıldı.")
            row = methods[token]
            calls = []
            graph[token] = calls
            if not row.Rva or not row.ImplFlags.miIL:
                unresolved.append(owners[token])
                continue
            body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(row.Rva)))
            for instruction in body.instructions:
                opcode = str(instruction.opcode)
                if opcode == "calli":
                    unresolved.append(owners[token] + ":calli")
                if opcode not in ("call", "callvirt", "newobj", "ldftn", "ldvirtftn"):
                    continue
                if not isinstance(instruction.operand, Token):
                    unresolved.append(owners[token] + ":" + opcode)
                    continue
                name, destination = resolve(instruction.operand.value)
                calls.append(
                    {"opcode": opcode, "target": name, "token": hex(instruction.operand.value)}
                )
                if destination is None:
                    external.add(name)
                else:
                    queue.append(destination)
        return {
            "assembly_sha256": before,
            "roots": [owners[token] for token in roots],
            "methods": {owners[token] + ":" + hex(token): calls for token, calls in graph.items()},
            "external_calls": sorted(external),
            "unresolved": unresolved,
            "limitations": "Dış assembly, native, örtük type initializer, virtual/indirect "
            "ve reflection davranışı "
            "bu grafikte çözümlenmez; kod çalıştırılmadı.",
        }
    finally:
        pe.close()
        if hash_file(path) != before:
            raise ValueError("Assembly analiz sırasında değişti.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", required=True, type=Path)
    parser.add_argument("--method", action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = checked_path(args.output)
    if not output.is_relative_to(root):
        raise ValueError("Analiz raporu çalışma alanında olmalı.")
    result = audit(args.assembly, args.method)
    paths = ProjectPaths(checked_path(args.assembly).parent, output.parent)
    paths.write_json(output.name, result)
    # Ham IL veya oyun metni standart teknik çıktıya basılmaz.
    read_back = strict_json(output.read_bytes())
    print(
        f"{len(read_back['methods'])} metot, {len(read_back['external_calls'])} dış çağrı; {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
