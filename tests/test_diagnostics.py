"""Structured diagnostics: reason codes, bridge failures and legacy message aliases."""

import sys
from types import SimpleNamespace

import pytest

from unitytranslator import diagnostics
from unitytranslator.diagnostics import Diagnostic, Failure, classify_message, describe
from unitytranslator.filesystem import PolicyError
from unitytranslator.providers import ProviderError
from unitytranslator.ui import i18n


@pytest.fixture
def language(monkeypatch):
    def use(code):
        monkeypatch.setattr(i18n, "active_language", lambda: code)
        i18n.diagnostic.cache_clear()

    yield use
    i18n.diagnostic.cache_clear()


def test_diagnostic_renders_english_and_keeps_template_and_params():
    error = Diagnostic("Expected {p0} records but found {p1}.", p0=3, p1="none")
    assert isinstance(error, ValueError)
    assert str(error) == "Expected 3 records but found none."
    assert error.template == "Expected {p0} records but found {p1}."
    assert error.params == {"p0": "3", "p1": "none"}
    with pytest.raises(TypeError):
        Diagnostic("Expected {p0}.", p1=1)
    # Without parameters the text is literal and may contain braces.
    assert str(Diagnostic("Invalid {json} payload.")) == "Invalid {json} payload."


def test_parameters_are_bounded():
    error = Diagnostic("Detail: {p0}", p0="x" * 10000)
    assert len(error.params["p0"]) == diagnostics.MAX_PARAMETER_CHARACTERS


def test_project_error_classes_are_diagnostics_and_still_value_errors():
    policy = PolicyError("Path {p0} is outside the project.", p0="a/b")
    assert isinstance(policy, ValueError) and policy.template.startswith("Path {p0}")
    provider = ProviderError("timeout", "The model server did not answer in {p0} s.", None, p0=30)
    assert provider.code == "timeout" and provider.params == {"p0": "30"}
    assert str(ProviderError("http_error", "Plain message.")) == "Plain message."


def test_describe_carries_code_params_token_and_project():
    failure = describe(
        Diagnostic("Expected {p0}.", p0=1), command="open", request_token="t1", project_id="p",
    )
    assert isinstance(failure, Failure) and isinstance(failure, str)
    assert failure == "Expected 1."
    assert failure.to_dict() == {
        "command": "open", "code": "Expected {p0}.", "params": {"p0": "1"},
        "message": "Expected 1.", "request_token": "t1", "project_id": "p",
    }


def test_plain_catalogued_english_messages_are_their_own_code():
    english = next(iter(sorted(diagnostics.english_catalog())))
    assert classify_message(english) == (english, {})
    assert describe(ValueError(english)).code == english
    unknown = describe(OSError("[WinError 5] Access is denied"))
    assert unknown.code is None and unknown == "[WinError 5] Access is denied"


def test_failures_localize_by_code_and_fall_back_to_english(language, monkeypatch):
    monkeypatch.setitem(i18n.catalog("en"), "Expected {p0} rows.", "Expected {p0} rows.")
    monkeypatch.setitem(i18n.catalog("de"), "Expected {p0} rows.", "{p0} Zeilen erwartet.")
    language("de")
    assert i18n.localize(describe(Diagnostic("Expected {p0} rows.", p0=4))) == "4 Zeilen erwartet."
    assert i18n.localize(describe(ValueError("Unknown detail."))) == "Unknown detail."
    # A failure whose code is not catalogued shows its English text.
    assert i18n.localize(describe(Diagnostic("Not catalogued {p0}.", p0=1))) == "Not catalogued 1."


def test_legacy_aliases_match_verbatim_and_patterned_old_messages(monkeypatch):
    monkeypatch.setattr(diagnostics, "legacy_aliases", lambda: {
        "Eski mesaj.": "New message.",
        "Eski {p0} ve {p1}.": "New {p1} and {p0}.",
    })
    diagnostics._legacy_patterns.cache_clear()
    diagnostics.classify_message.cache_clear()
    try:
        assert classify_message("Eski mesaj.") == ("New message.", {})
        expected = ("New {p1} and {p0}.", {"p0": "a b", "p1": "c"})
        assert classify_message("Eski a b ve c.") == expected
        assert classify_message("Başka bir mesaj.") == (None, {})
    finally:
        diagnostics._legacy_patterns.cache_clear()
        diagnostics.classify_message.cache_clear()


def test_bridge_failure_includes_request_token_and_project(monkeypatch):
    pytest.importorskip("PySide6")
    import asyncio

    from unitytranslator.ui.bridge import BackendBridge

    class Session:
        async def dispatch(self, command, data):
            raise Diagnostic("Expected {p0}.", p0=2)

        def current_project_id(self):
            return "project-1"

    received = []

    class Signal:
        def __init__(self, sink):
            self.sink = sink

        def emit(self, *args):
            self.sink.append(args)

    bridge = SimpleNamespace(session=Session(), completed=Signal([]), failed=Signal(received))
    asyncio.run(BackendBridge._perform(bridge, "page", {"request_token": "r9"}))
    command, failure = received[0]
    assert command == "page" and failure.code == "Expected {p0}."
    assert failure.request_token == "r9" and failure.project_id == "project-1"


# --- Source rules (AST only; nothing is imported or executed from the scanned files) ---

import ast  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

from unitytranslator.diagnostics import legacy_aliases, template_fields  # noqa: E402

SOURCE = Path(__file__).parents[1] / "src/unitytranslator"
# Turkish letters, or common Turkish words written without them.
TURKISH = re.compile(
    r"[çğıöşüÇĞİÖŞÜ]|\b(?:kabul|edilmiyor|edilemez|dosya(?:si|sı)?|kaynak|kaynagi|oyun|oyunu|"
    r"eksik|veya|ve|bir|icin|degil|yok|olmali|bulunamadi|gecersiz|okunamadi|acilamadi|"
    r"kayit|kayitlar|ceviri|onay|onayla|lutfen|bekleyin|yineleniyor|desteklenmiyor|"
    r"degisti|sinir|klasor|hedef|islem|yukleyici)\b",
    re.IGNORECASE | re.ASCII,
)
DIAGNOSTIC_CLASSES = {
    "Diagnostic", "PolicyError", "ProviderError", "OperationCancelled", "GameNotClosedError",
}
# Process exits and OS error constructors carry no interface message.
NON_MESSAGE_CLASSES = {"SystemExit", "WinError"}
# Messages taken from declared command guards; test_commands checks they are catalogued.
GUARD_MESSAGES = {
    ("application.py", "guard.identity"), ("application.py", "guard.idle[1]"),
    ("application.py", "message"),
}
# Intentional non-English data: Turkish report documents and labels, linguistic
# patterns, language names, the persisted approve-all confirmation phrase and
# synthetic Unicode fixture text of the developer UI verification.
# validation.py holds Turkish issue labels and linguistic patterns; its exception
# messages are still checked by the catalogued-code rule. glossary_match.py holds
# per-language inflection endings (Turkish, Finnish, Russian letters) and raises nothing.
LANGUAGE_EXEMPT_FILES = {
    "reports.py", "language.py", "validation.py", "glossary_match.py", "ui/verify.py",
    "ui/i18n.py",
}
LANGUAGE_EXEMPT_SCOPES = {("review_selection.py", "canonical_all_confirmation")}


def call_name(node):
    func = node.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")


def message_arg(call):
    """The message argument of an exception constructor call."""
    index = 1 if call_name(call) == "ProviderError" else 0
    return call.args[index] if len(call.args) > index else None


def source_files():
    for path in sorted(SOURCE.rglob("*.py")):
        yield path.relative_to(SOURCE).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def module_constants(tree):
    """Module-level NAME = "literal" assignments, so named messages are checked too."""
    return {
        node.targets[0].id: node.value.value for node in tree.body
        if isinstance(node, ast.Assign) and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }


def exception_calls():
    for relative, tree in source_files():
        constants = module_constants(tree)
        seen = set()
        for node in ast.walk(tree):
            call = None
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                call = node.exc
            elif isinstance(node, ast.Call) and call_name(node) in DIAGNOSTIC_CLASSES:
                call = node
            if call is not None and id(call) not in seen:
                seen.add(id(call))
                for argument in call.args:
                    if isinstance(argument, ast.Name) and argument.id in constants:
                        argument.__dict__["resolved"] = constants[argument.id]
                yield relative, call


def scoped_constants(tree):
    """String constants with the name of their enclosing function, class or assignment."""
    docstrings = {
        id(node.body[0].value) for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }

    def visit(node, scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
            node.targets[0], ast.Name
        ):
            scope = node.targets[0].id
        elif isinstance(node, ast.Call) and call_name(node) in ("compile", "search", "sub"):
            scope = "<pattern>"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                yield scope, node
        for child in ast.iter_child_nodes(node):
            yield from visit(child, scope)

    yield from visit(tree, "<module>")


def language_problems():
    found = []
    for relative, tree in source_files():
        if relative in LANGUAGE_EXEMPT_FILES:
            continue
        for scope, node in scoped_constants(tree):
            if (relative, scope) in LANGUAGE_EXEMPT_SCOPES:
                continue
            if TURKISH.search(node.value):
                found.append(f"{relative}:{node.lineno}: {node.value[:60]}")
    return found


def test_no_source_text_is_written_in_another_language():
    assert language_problems() == []


def code_problems():
    english = diagnostics.english_catalog()
    problems = []
    for relative, call in exception_calls():
        name = call_name(call)
        argument = message_arg(call)
        where = f"{relative}:{call.lineno}"
        if name in NON_MESSAGE_CLASSES or argument is None:
            continue
        if any(keyword.arg is None for keyword in call.keywords):
            problems.append(f"{where}: ** parameters hide the template fields")
            continue
        if isinstance(argument, ast.Call) and call_name(argument) == "tr":
            continue  # Interface code raising an already localized catalog message.
        if isinstance(argument, ast.Subscript) and isinstance(argument.value, ast.Dict):
            values = argument.value.values  # A fixed table of messages selected by key.
        else:
            values = [argument]
        if (relative, ast.unparse(argument)) in GUARD_MESSAGES:
            continue
        values = [
            ast.Constant(value.__dict__["resolved"], lineno=value.lineno)
            if "resolved" in value.__dict__ else value
            for value in values
        ]
        for value in values:
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                problems.append(f"{where}: dynamic message {ast.unparse(value)[:60]}")
            elif value.value not in english:
                problems.append(f"{where}: uncatalogued {value.value[:60]!r}")
            else:
                params = sorted(k.arg for k in call.keywords if k.arg and k.arg[1:].isdigit())
                fields = template_fields(value.value) if params else []
                if params and sorted(set(fields)) != params:
                    problems.append(f"{where}: fields differ from parameters")
    return problems


def test_every_exception_message_carries_a_catalogued_code():
    assert code_problems() == []


def test_source_rules_reject_known_bypasses(tmp_path, monkeypatch):
    """The rules above must catch these shapes; guard against weakening them."""
    module = tmp_path / "module.py"
    module.write_text(
        "def f(x):\n"
        "    raise ValueError('Proje acilamadi; kayitlar okunamadi.')\n"
        "def g(x):\n"
        "    message = 'Dosya bulunamadı.'\n"
        "    raise ValueError(message)\n"
        "def h(x):\n"
        "    raise Diagnostic('Uncatalogued {p0}.', **{'p0': x})\n"
        "def i(x):\n"
        "    raise ValueError('Missing {0}.'.format(x))\n"
        "def j():\n"
        "    return {'message': 'Kurulum hazır değil.'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "SOURCE", tmp_path)
    language = " | ".join(language_problems())
    for line in (2, 4, 11):
        assert f"module.py:{line}:" in language
    codes = " | ".join(code_problems())
    for line in (2, 5, 7, 9):
        assert f"module.py:{line}:" in codes


def test_legacy_aliases_point_to_catalogued_templates_and_match_old_messages():
    aliases = legacy_aliases()
    assert len(aliases) >= 300
    english = diagnostics.english_catalog()
    for old, target in aliases.items():
        assert target in english, target
        assert sorted(set(template_fields(old))) == sorted(set(template_fields(target))), old
        rendered = old.format(**{name: f"<{name}>" for name in template_fields(old)})
        code, params = classify_message(rendered)
        assert code == target, old
        assert all(params[name] == f"<{name}>" for name in template_fields(old))


@pytest.mark.parametrize("code", sorted(i18n.LANGUAGES))
def test_old_turkish_messages_localize_in_every_interface_language(language, code):
    language(code)
    for old, target in list(legacy_aliases().items())[:400]:
        values = {name: "X" for name in template_fields(old)}
        rendered = old.format(**values) if values else old
        expected = i18n.tr(target, **values) if values else i18n.tr(target)
        assert i18n.diagnostic(rendered) == expected, old
