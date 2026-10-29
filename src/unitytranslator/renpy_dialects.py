"""Inspect audited upstream source contracts as syntax trees, never executable code.

Function fingerprints describe the supported symbolic-source behavior family,
not game names or a version range. Provenance: official renpy/renpy tags
8.1.2.23090503 and 8.3.6.25022803; see docs/development.md.
"""

import ast
import re
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Any

from unitytranslator.filesystem import checked_path
from unitytranslator.renpy_python import PYTHON_BLOCKS_V1, PYTHON_BLOCKS_V2

FAMILY = "renpy-symbolic-source-v1"
MAX_CONTRACT_BYTES = 256 * 1024
MAX_AST_NODES = 50000
_LEGACY_VERSION = re.compile(rb"(?m)^version = ['\"]8\.1\.2\.23090503['\"]\r?$")
_DECLARED_MAJOR = re.compile(rb"(?m)^version = ['\"]([0-9]+)\.[0-9.]+['\"]\r?$")
_IMAGE_KEYWORDS_V2 = frozenset({"behind", "at", "onlayer", "with", "zorder", "transform"})
_CONTRACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "ast.py": {
        "Say.get_code": (
            "d7b314c49894356bdf6440242ad6ee40d2a4d7ff0a898ebb9ec9854dc287d6e1",
            "22bb422431ad065064005e2efc094bb3554f60a1c489f2711cbcd404671a9eaa",
        ),
    },
    "translation/__init__.py": {
        "encode_say_string": (
            "f2af9f9b1b01c7f86bf473ba7f4278fe9aa5ac7727f9438cde7f008eb9384c97",
        ),
        "Restructurer.__init__": (
            "88446318d41907458b2495006edf163a4f0b4cf98cac95ddbb083e6af48b1af1",
        ),
        "Restructurer.id_exists": (
            "c6e161d81f170e7c770fa3934b09ef8a3b927bef2577dd811d3ad1d41e117339",
        ),
        "Restructurer.unique_identifier": (
            "4e6d1abb7488452cb8144ac01cfc56ba6c155232ca97115bc2448b9c26266ef2",
        ),
        "Restructurer.create_translate": (
            "2d2a9a35b6089c040c1a787ada6277749f11d0e3e537cd735dedd02af3bef309",
        ),
        "Restructurer.callback": (
            "4b41c0887beb6fc1f657778c9ade1a8c8bde1e569f1a993bf3bb211d46a396dd",
            "cb9e90fd8ed61663793a9d09c36c6a5903b9cee2ad3b90142583a29be5e52d71",
        ),
    },
    "lexer.py": {
        "Lexer.string": (
            "afa4d86631a9316f8a213020ebe6e0a63aa6529ab11bf88bd03fe8c053718fde",
        ),
        "list_logical_lines": (
            "2c3b236eeae3b8fa929827c2ed556d7d637a32bf3c0dca3fce016805d50860c4",
            "6d58313d6364962f739c728e64bafa99461ebd11babdcde7bd0fe705b8ec2647",
        ),
        "group_logical_lines": (
            "9c52308a495cb5a89301ab069d48a53ffeb5ca0d3c6c561f21461d9dcf77c648",
        ),
        "Lexer.name": (
            "4e07d25c56ab4f3fea452af8f7030d0ef500175a2d77c782e5e25da94dfd6eba",
        ),
        "Lexer.label_name": (
            "5a55d3ef69c2c80bd44e68093607e9b158824b1743cabac8cbbe1e92395ecf87",
        ),
        "Lexer.image_name_component": (
            "56066f13e4fb0b4e658df8d9e4118c5f40816ef8d60e49be1bc0d47b888d1aa9",
            "d7fae52063aa93ed53d1723a05bbce4f94ac657a270652325e8d32f88a66c529",
        ),
        "Lexer.match": (
            "11231df4cbe4f93467848f9fc407b80282a59cc84b8d2f0e8c34be2142be22d4",
        ),
    },
    "parser.py": {
        "finish_say": (
            "928e9cb742eaa0648cbf886905809e43e64a92026c6fd928c865a538530b2190",
            "04eb14252172284b6e722b9aedb96984869e48f3c3b50037d83ab18c5cc9b361",
        ),
        "say_attributes": (
            "7f12c2f8006cb6016c22b52fbfcbcfe800d21350037104beb553639ece738431",
        ),
        "parse_menu": (
            "6f54948ec5d3f76ee76def1edb1e4aff38f3a627773d75563f5fc32220615cd4",
            "6856fd1e1211626e038a0fe8709c389ab2e043c2d4b39aff3faf30e38206b063",
        ),
        "say_statement": (
            "642a4b8b88bfd6e3bde7e2759a70b3fbed6fdc66d273f7d0967889f23c2c6d76",
        ),
        "menu_statement": (
            "1e47e093f2dd6bbbcbf51fb841cd113742c8d8587b95c8d1b1ec83e632ed0e89",
        ),
        "label_statement": (
            "26b90632d506522c2f81c2234bb4160594106b1d448c7e8be2e19a266782e32d",
        ),
        "call_statement": (
            "5b0ae94ce22757c3aa8b5ec61f78bb9e0029966ebdbeea1ee987374b777c8cac",
            "e34f570d5bd9033fadd78f40b83660e95960e150f208a49e50e70ad11e6721ad",
        ),
    },
    "script.py": {
        "Script.scan_script_files": (
            "3e77dd3fb56a2192c185efe705fb13507a5d654bb36e59cd5f621ed12677800f",
        ),
        "Script.load_script": (
            "4b64db24b218a116d581acc7dc442507f628ad54cf4100d3f7d8d6f8dae06082",
            "9de02a20580785d1caf41274c87743f3e506538091f9f524d6970ba09c4659b1",
        ),
        "Script.load_appropriate_file": (
            "bae6e72256f8cfeba5277a56ebaa6605cdd5d4eb97405b59be94984089b4bbf6",
        ),
        "Script.write_rpyc_md5": (
            "e57dafa4b8bd912e8607063b7ec9858a60d50cf409d2ea832e2461d68c570797",
        ),
    },
}
_COMBINE = "14b0b78d3164dcab1090fd14b7100787006295f9ae4f0b2d0b6f6a04adf46570"
_MODERN_CALLBACK = "cb9e90fd8ed61663793a9d09c36c6a5903b9cee2ad3b90142583a29be5e52d71"
_MODERN_ATTRIBUTES = "d7fae52063aa93ed53d1723a05bbce4f94ac657a270652325e8d32f88a66c529"
_PYTHON_CONVERSION = {
    "de810c6849a2c9cfce4ee0a9d6ff1eea5b523eacced3a49a074ed1018f9cf5e8": PYTHON_BLOCKS_V1,
    "7098116363e3a3dd8d733e4c5bca6cdcec5c32a52e811f822567e53e2ea73d61": PYTHON_BLOCKS_V2,
}


def _without_docs(node: ast.AST) -> None:
    for child in ast.walk(node):
        if isinstance(child, ast.FunctionDef | ast.ClassDef | ast.Module) and child.body:
            first = child.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(
                first.value.value, str,
            ):
                child.body = child.body[1:]


def contract_fingerprint(tree: ast.Module, qualified: str) -> str:
    """Select only direct declarations. Duplicate or conditional definitions do not match."""
    node: ast.Module | ast.FunctionDef | ast.ClassDef = tree
    for part in qualified.split("."):
        matches = [child for child in node.body
                   if isinstance(child, ast.FunctionDef | ast.ClassDef) and child.name == part]
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous Ren'Py source contract: " + qualified)
        node = matches[0]
    return sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def inspect_source_dialect(
    game: Path, version_raw: bytes, *, cancelled: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    """Version is evidence; audited lexer/parser/ID/ordering behavior enables reading."""
    declared = _DECLARED_MAJOR.search(version_raw)
    if declared is not None and int(declared[1]) < 8:
        raise ValueError(
            "Ren'Py Python 2 source-text semantics are unverified; inspect native templates."
        )
    paths = {name: checked_path(game / "renpy" / name) for name in _CONTRACTS}
    if not any(path.exists() for path in paths.values()):
        if _LEGACY_VERSION.search(version_raw):
            return {"family": FAMILY, "evidence_kind": "legacy_pinned_source",
                    "fingerprints": {}, "contracts": {}, "reserved_attributes": [],
                    "python_source": None}
        raise ValueError(
            "Ren'Py native-ID behavior is unverified: audited source contracts are missing; "
            "the legacy pinned source profile requires 8.1.2.23090503 evidence."
        )
    fingerprints, contracts = {}, {}
    python_source = None
    for name, required in _CONTRACTS.items():
        if cancelled():
            raise ValueError("Source extraction was cancelled.")
        path = paths[name]
        if not path.is_file() or path.stat().st_size > MAX_CONTRACT_BYTES:
            raise ValueError("Missing or oversized Ren'Py native-ID source contract: " + name)
        with path.open("rb") as stream:
            raw = stream.read(MAX_CONTRACT_BYTES + 1)
        if len(raw) > MAX_CONTRACT_BYTES:
            raise ValueError("Ren'Py source contract size limit exceeded.")
        try:
            tree = ast.parse(raw.decode("utf-8-sig"))
        except (SyntaxError, UnicodeError, RecursionError) as exc:
            raise ValueError("Unverified Ren'Py source contract syntax: " + name) from exc
        if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
            raise ValueError("Ren'Py source contract AST limit exceeded.")
        _without_docs(tree)
        verified = {}
        for qualified, accepted in required.items():
            digest = contract_fingerprint(tree, qualified)
            if digest not in accepted:
                raise ValueError("Unverified Ren'Py source behavior: " + name + ":" + qualified)
            verified[qualified] = digest
        if name == "translation/__init__.py" and verified.get("Restructurer.callback") == (
            _MODERN_CALLBACK
        ):
            if contract_fingerprint(tree, "Restructurer.combine_translate") != _COMBINE:
                raise ValueError("Unverified Ren'Py TranslateSay combination behavior.")
            verified["Restructurer.combine_translate"] = _COMBINE
        if name == "lexer.py":
            try:
                conversion = contract_fingerprint(tree, "ren_py_to_rpy")
            except ValueError:
                conversion = ""
            python_source = _PYTHON_CONVERSION.get(conversion)
            if python_source:
                verified["ren_py_to_rpy"] = conversion
        fingerprints["renpy/" + name] = sha256(raw).hexdigest()
        contracts[name] = verified
    modern_attributes = contracts["lexer.py"]["Lexer.image_name_component"] == (
        _MODERN_ATTRIBUTES
    )
    return {
        "family": FAMILY, "evidence_kind": "audited_source_contracts",
        "fingerprints": fingerprints, "contracts": contracts,
        "reserved_attributes": sorted(_IMAGE_KEYWORDS_V2) if modern_attributes else [],
        "python_source": python_source,
    }
