"""Uniform drivers for the shared recipient ownership scenarios.

Every driver installs synthetic packages into synthetic game folders under the test's
temporary directory. Frozen legacy packages come from tests/fixtures/legacy-recipients.
No game is started; the only process a scenario starts is a copied Windows cmd.exe that
stands in for a running game image and is stopped before the scenario ends.

Each install and removal is split into a review phase and an apply phase so scenarios can
change the game between them. Where an implementation has no review phase (removal in the
Python service and in every patch.ps1; install in the 0.1.0 release-candidate patch.ps1,
which reports ``has_review = False``) the review step is a no-op and every check happens
in the single apply run.
"""

import json
import os
import shutil
import subprocess
import threading
import zipfile
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from deployment_helpers import install_synthetic_plan

from unitytranslator.filesystem import ProjectPaths, hash_file

LEGACY = Path(__file__).resolve().parent / "fixtures" / "legacy-recipients"
HELPER_IMAGE = "Helper/unitytranslator-test-helper.exe"
CLOSE_GAME = "Close the game"
# Locale-independent PowerShell error identifiers (message texts follow the OS language).
MISSING_RECEIPT = "PathNotFound"
CREATE_NEW_FAILED = "IOException"
# Windows in which the game changes after a successful review.
REVIEW_RUN = "review-run"  # Between a -ReviewOnly run and the -ReviewedPlanSha256 run.
CONFIRMATION = "confirmation-prompt"  # While an interactive run waits for INSTALL/REMOVE.
WINDOWS = (REVIEW_RUN, CONFIRMATION)
Change = Callable[[], AbstractContextManager[Any]]


def tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {p.relative_to(root).as_posix(): hash_file(p) for p in root.rglob("*") if p.is_file()}


def identity(path: Path) -> str:
    """Volume serial and file index in the recipients' receipt identity format."""
    info = path.stat()
    return f"{info.st_dev:08X}:{info.st_ino:016X}"


def require_windows() -> str:
    powershell = shutil.which("powershell.exe")
    if os.name != "nt" or powershell is None:
        pytest.skip("Windows PowerShell recipient installers run only on Windows")
    return powershell


def truncate_in_place(path: Path) -> None:
    """Empty a file through its existing handle so its identity stays the same."""
    with path.open("r+b") as stream:
        stream.truncate(0)


def rewrite_in_place(path: Path, data: bytes) -> None:
    with path.open("r+b") as stream:
        stream.truncate(0)
        stream.write(data)


@dataclass(frozen=True)
class Outcome:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    preserved: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return self.returncode == 0 and not self.preserved

    def json(self) -> Any:
        return json.loads(self.stdout)


REVIEWED = Outcome(0)


class SimulatedCrash(BaseException):
    """Stops an in-process install like a power loss: no ``except Exception`` handler runs."""


def powershell(script: Path, *args: object, stdin: str = "CANCEL\n") -> Outcome:
    completed = subprocess.run(
        [
            require_windows(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *map(str, args),
        ],
        capture_output=True,
        input=stdin.encode("ascii"),
        timeout=180,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return Outcome(
        completed.returncode,
        completed.stdout.decode("utf-8-sig", errors="replace"),
        completed.stderr.decode("utf-8", errors="replace"),
    )


def prompted(script: Path, args: tuple[object, ...], word: str, change: Change) -> Outcome:
    """Run an installer interactively and apply ``change`` while it waits for ``word``.

    Every installer prints its plan only after its pre-checks, then blocks in Read-Host,
    so the first stdout line marks the confirmation window a user spends reading the plan.
    """
    process = subprocess.Popen(
        [require_windows(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         *map(str, args)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )  # fmt: skip
    assert process.stdin is not None and process.stdout is not None
    shown = threading.Event()
    output: list[bytes] = []
    errors: list[bytes] = []

    def pump_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            output.append(line)
            shown.set()
        shown.set()

    def pump_errors() -> None:
        assert process.stderr is not None
        errors.append(process.stderr.read())

    readers = [threading.Thread(target=pump, daemon=True) for pump in (pump_output, pump_errors)]
    for reader in readers:
        reader.start()
    try:
        assert shown.wait(180), "The installer never showed its plan."
        assert output, "The installer stopped before its confirmation prompt."
        with change():
            process.stdin.write(word.encode("ascii") + b"\n")
            process.stdin.close()
            process.wait(timeout=180)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=30)
        for reader in readers:
            reader.join(timeout=30)
    return Outcome(
        process.returncode,
        b"".join(output).decode("utf-8-sig", errors="replace"),
        b"".join(errors).decode("utf-8", errors="replace"),
    )


def legacy_fixture(name: str, tmp: Path) -> tuple[Path, Path, dict[str, Any]]:
    """Extract a frozen synthetic legacy package and its matching synthetic game."""
    index = json.loads((LEGACY / "index.json").read_bytes())
    entry = next(item for item in index["fixtures"] if item["name"] == name)
    folders = {"package": tmp / "legacy package", "game": tmp / "legacy game"}
    for key, target in folders.items():
        archive_path = LEGACY / entry[key]
        assert sha256(archive_path.read_bytes()).hexdigest() == entry[key + "_sha256"]
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.namelist():
                assert not member.startswith(("/", "\\")) and ".." not in member.split("/")
            archive.extractall(target)  # Our own frozen synthetic fixture only.
    return folders["package"], folders["game"], entry


@contextmanager
def live_image(path: Path) -> Iterator[subprocess.Popen[bytes]]:
    """Run a copied cmd.exe at ``path`` so a process image lies under a synthetic game."""
    require_windows()
    source = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()  # A synthetic stand-in extracted by this test only.
    shutil.copyfile(source, path)
    process = subprocess.Popen(
        [str(path), "/d", "/q"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        assert process.poll() is None
        yield process
    finally:
        process.kill()
        process.wait(timeout=30)


class Driver:
    """One installer implementation behind the shared scenario vocabulary."""

    name = ""
    legacy = False
    windows = True
    has_review = True
    # Interactive confirmation words; empty when the implementation has no prompt, in which
    # case the confirmation window falls back to the review-run window.
    install_prompt = ""
    removal_prompt = ""
    # Expected refusal text for (b) existing target, (g) tampered receipt, (h) other game
    # and (l) removal of an interrupted installation that has no receipt yet.
    refusals: dict[str, str] = {}
    # (b2) a destination that appears after a successful review, per window: the refusal
    # text and whether the refused install leaves unreceipted partial additions behind.
    late_destination: dict[str, tuple[str, bool]] = {}
    # (k): receipt status left by a removal that preserved a modified owned file, and the
    # refusal of the retried removal after the file was restored ("" = it completes).
    preserved_status = "recovery_required"
    restored_retry_refusal = ""
    # (l): "partial" removes unchanged owned files and preserves the partial one;
    # "refused" deletes nothing because no ownership receipt was written yet.
    interrupted_removal = "partial"

    def __init__(self, request: pytest.FixtureRequest, tmp: Path):
        self.request = request
        self.tmp = tmp
        self.game: Path = tmp
        self.root: Path = tmp
        self.originals: dict[str, str] = {}
        self.plan: dict[str, Any] = {}

    # Setup and actions -------------------------------------------------------------------
    def setup(self) -> None:
        raise NotImplementedError

    def snapshot(self) -> None:
        self.originals = tree(self.game)

    def review(self) -> Outcome:
        """Review the install plan; nothing is written to the game."""
        raise NotImplementedError

    def apply(self) -> Outcome:
        """Apply the plan accepted by the last successful review."""
        raise NotImplementedError

    def install(self) -> Outcome:
        review = self.review()
        if review.returncode:
            return review
        return self.apply()

    def review_removal(self, root: Path | None = None) -> Outcome:
        return REVIEWED

    def apply_removal(self, root: Path | None = None) -> Outcome:
        raise NotImplementedError

    def remove(self, root: Path | None = None) -> Outcome:
        review = self.review_removal(root)
        if review.returncode:
            return review
        return self.apply_removal(root)

    def script(self) -> Path:
        raise NotImplementedError

    def interactive_install_arguments(self) -> tuple[object, ...]:
        raise NotImplementedError

    def interactive_removal_arguments(self) -> tuple[object, ...]:
        raise NotImplementedError

    def install_across(self, window: str, change: Change) -> Outcome:
        """Review, apply ``change`` inside ``window``, then let the install continue."""
        review = self.review()  # Also records the plan for the scenario's expectations.
        assert review.complete, review.stderr
        if window == CONFIRMATION and self.install_prompt:
            arguments = self.interactive_install_arguments()
            return prompted(self.script(), arguments, self.install_prompt, change)
        with change():
            return self.apply()

    def remove_across(self, window: str, change: Change) -> Outcome:
        """Review a removal, apply ``change`` inside ``window``, then let it continue."""
        if window == CONFIRMATION and self.removal_prompt:
            arguments = self.interactive_removal_arguments()
            return prompted(self.script(), arguments, self.removal_prompt, change)
        review = self.review_removal()
        assert review.complete, review.stderr
        with change():
            return self.apply_removal()

    def interrupt(self) -> str | None:
        """Leave the state of an install interrupted mid-copy; return its partial file."""
        raise NotImplementedError

    # Scenario vocabulary -----------------------------------------------------------------
    def added(self) -> set[str]:
        """Files the installation added under the additions root."""
        return set(tree(self.root)) - (set(self.originals) if self.root == self.game else set())

    def planned(self) -> set[str]:
        """Every file the reviewed plan creates, including generated metadata."""
        raise NotImplementedError

    def planned_claims(self) -> set[str]:
        """Files the receipt must claim, derived from the reviewed plan alone."""
        raise NotImplementedError

    def removable(self) -> set[str]:
        """Files a complete removal deletes, derived from the reviewed plan alone."""
        raise NotImplementedError

    def receipt_document(self) -> dict[str, Any]:
        value: dict[str, Any] = json.loads(self.receipt().read_bytes())
        return value

    def receipt_claims(self) -> set[str]:
        """Files the installer's own receipt claims."""
        return {entry["path"] for entry in self.receipt_document()["files"]}

    def receipt_status(self) -> str | None:
        if not self.receipt().exists():
            return None
        return str(self.receipt_document()["status"])

    def owned(self) -> str:
        raise NotImplementedError

    def conflict(self) -> Path:
        raise NotImplementedError

    def receipt(self) -> Path:
        raise NotImplementedError

    def user_file(self) -> Path:
        raise NotImplementedError

    def watched(self) -> list[Path]:
        return [self.game]

    def tamper_receipt(self) -> None:
        raise NotImplementedError

    def relocate(self) -> Path:
        target = self.tmp / "relocated game"
        shutil.copytree(self.game, target)
        return target

    def process_image(self) -> str:
        return HELPER_IMAGE

    def refused_by_process(self, outcome: Outcome) -> bool:
        return outcome.returncode != 0 and CLOSE_GAME in outcome.stderr

    def originals_unchanged(self) -> bool:
        current = tree(self.game)
        return all(current.get(name) == digest for name, digest in self.originals.items())


# Python DeploymentService --------------------------------------------------------------------
def _python_activate(service: Any, plan: Any) -> dict[str, Any]:
    """The single generic in-app install call through the shared test helper."""
    return install_synthetic_plan(service, plan)


class PythonDeployment(Driver):
    name = "python-deployment"
    windows = False
    refusals = {
        "b": "conflicts with original or excluded user data",
        "g": "cannot claim an original file",
        "h": "linked game folder does not match",
    }
    # A new game file changes the inventory fingerprint before any target check. There is
    # no interactive prompt: the window is between plan preparation and the install call.
    late_destination = {
        REVIEW_RUN: ("The game changed after preparation.", False),
        CONFIRMATION: ("The game changed after preparation.", False),
    }
    targets = ("mod/a.txt", "mod/b.txt")

    def setup(self) -> None:
        from unitytranslator.deployment import DeploymentService
        from unitytranslator.game_process import GameProcessStatus
        from unitytranslator.repository import ProjectRepository

        self.game = self.root = self.tmp / "game"
        self.game.mkdir()
        (self.game / "original.bin").write_bytes(b"synthetic original")
        (self.game / "Synthetic.exe").write_bytes(b"Synthetic EXE stand-in; never executed")
        self.project = self.tmp / "project"
        self.stack = ExitStack()
        self.request.addfinalizer(self.stack.close)
        self.repo = self.stack.enter_context(
            ProjectRepository(ProjectPaths(self.game, self.project))
        )
        self.repo.paths.write_text("artifacts/payload/a.txt", "synthetic plugin")
        self.repo.paths.write_text("artifacts/payload/b.txt", "synthetic translation")
        if os.name == "nt":
            self.service = DeploymentService(self.repo)  # Real read-only process inspection.
        else:
            self.service = DeploymentService(
                self.repo, process_probe=lambda _: GameProcessStatus("closed")
            )
        self.snapshot()

    @staticmethod
    def refusal(error: ValueError) -> Outcome:
        return Outcome(1, stderr=type(error).__name__ + ": " + str(error))

    def review(self) -> Outcome:
        try:
            self.pending = self.service.prepare(
                "synthetic-test-only",
                "1",
                [
                    ("artifacts/payload/a.txt", self.targets[0]),
                    ("artifacts/payload/b.txt", self.targets[1]),
                ],
            )
        except ValueError as error:
            return self.refusal(error)
        self.plan = {"files": [{"path": file.target} for file in self.pending.files]}
        return REVIEWED

    def apply(self) -> Outcome:
        try:
            result = _python_activate(self.service, self.pending)
        except ValueError as error:
            return self.refusal(error)
        return Outcome(0 if result["status"] == "installed" else 2, json.dumps(result))

    def apply_removal(self, root: Path | None = None) -> Outcome:
        from unitytranslator.deployment import DeploymentService
        from unitytranslator.repository import ProjectRepository

        try:
            if root is None:
                result = self.service.uninstall(user_action=True)
            else:
                # The project-local receipt is bound to one game path; open it for the copy.
                self.stack.close()
                with ProjectRepository(ProjectPaths(root, self.project)) as repo:
                    result = DeploymentService(repo).uninstall(user_action=True)
        except ValueError as error:
            return self.refusal(error)
        return Outcome(
            0 if result["status"] == "removed" else 2,
            json.dumps(result),
            preserved=tuple(result["preserved"]),
        )

    def interrupt(self) -> str | None:
        # Crash after the second file's ownership was recorded and before its bytes were
        # written: the rollback handler (``except Exception``) never runs.
        assert self.review().complete
        save = self.service.save_manifest

        def crash_after_claim(manifest: dict[str, Any]) -> None:
            save(manifest)
            if manifest["files"][1]["state"] == "created":
                raise SimulatedCrash

        self.service.save_manifest = crash_after_claim  # type: ignore[method-assign]
        try:
            with pytest.raises(SimulatedCrash):
                self.apply()
        finally:
            del self.service.save_manifest
        assert self.receipt_status() == "installing"
        return self.targets[1]

    def planned(self) -> set[str]:
        return {entry["path"] for entry in self.plan["files"]}

    def planned_claims(self) -> set[str]:
        return self.planned()

    def removable(self) -> set[str]:
        return self.planned()

    def receipt_claims(self) -> set[str]:
        return {entry["target"] for entry in self.receipt_document()["files"]}

    def owned(self) -> str:
        return self.targets[1]

    def conflict(self) -> Path:
        return self.game / self.targets[1]

    def receipt(self) -> Path:
        return self.repo.paths.output("artifacts/deployment.json")

    def user_file(self) -> Path:
        return self.game / "mod/user-notes.txt"

    def tamper_receipt(self) -> None:
        manifest = self.service.read_manifest()
        assert manifest is not None
        original = self.game / "Synthetic.exe"
        info = original.stat()
        claim = {"target": "Synthetic.exe", "sha256": hash_file(original)}
        manifest["files"][0].update(claim, device=info.st_dev, inode=info.st_ino)
        self.service.save_manifest(manifest)
        # Tamper the project-local plan too so only the original-claim refusal remains.
        plan_path = self.repo.paths.output(f"artifacts/plans/{manifest['plan_id']}.json")
        plan = json.loads(plan_path.read_bytes())
        plan["files"][0].update(claim)
        self.repo.paths.write_json(f"artifacts/plans/{manifest['plan_id']}.json", plan)

    def refused_by_process(self, outcome: Outcome) -> bool:
        return outcome.returncode != 0 and outcome.stderr.startswith("GameNotClosedError")


# Shareable Unity patch (patch.ps1) ---------------------------------------------------------
class ShareablePatch(Driver):
    name = "unity-shareable-current"
    refusals = {
        "b": "Existing mod/patch found",
        "g": "Receipt file set changed.",
        "h": "Receipt belongs to a different package/game path.",
    }
    install_prompt = "INSTALL"
    # The apply run repeats the existence check before its plan hash; after the typed
    # confirmation every destination is checked again before the first write.
    late_destination = {
        REVIEW_RUN: ("Existing mod/patch found", False),
        CONFIRMATION: ("A destination appeared after review", False),
    }
    receipt_name = "UnityTranslatorPatch/install-receipt.json"
    owned_name = "UnityTranslatorPatch/BepInEx/plugins/UnityTranslator/translation.json"

    def setup(self) -> None:
        from unitytranslator.shareable import export_shareable_patch

        require_windows()
        repo = self.request.getfixturevalue("krypta_project")[0]
        result = export_shareable_patch(repo)
        self.package = self.tmp / "patch package"
        with zipfile.ZipFile(result["path"]) as archive:
            archive.extractall(self.package)  # Fixed exporter-generated synthetic ZIP.
        self.game = self.root = repo.paths.game
        self.snapshot()

    def manifest(self) -> dict[str, Any]:
        value: dict[str, Any] = json.loads((self.package / "package.json").read_bytes())
        return value

    def script(self) -> Path:
        return self.package / "patch.ps1"

    def run(self, *args: object) -> Outcome:
        return powershell(self.script(), *args)

    def interactive_install_arguments(self) -> tuple[object, ...]:
        return ("-Action", "Install", "-GameFolder", self.game)

    def review(self) -> Outcome:
        review = self.run("-Action", "Install", "-GameFolder", self.game, "-ReviewOnly")
        if review.returncode == 0:
            self.plan = review.json()
        return review

    def apply(self) -> Outcome:
        return self.run(
            "-Action", "Install", "-GameFolder", self.game,
            "-ReviewedPlanSha256", self.plan["sha256"],
        )  # fmt: skip

    def apply_removal(self, root: Path | None = None) -> Outcome:
        removed = self.run("-Action", "Remove", "-GameFolder", root or self.game)
        marker = "Changed files preserved: "
        found = [
            line.split(marker, 1)[1].strip()
            for line in removed.stderr.splitlines()
            if marker in line
        ]
        if not found:
            return removed
        return Outcome(
            removed.returncode, removed.stdout, removed.stderr, tuple(found[0].split(", "))
        )

    def interrupt(self) -> str | None:
        # Every patch.ps1 revision appends a file to the receipt and saves it before writing
        # that file's bytes. Reproduce a crash in the second copy from a complete install:
        # receipt status "installing", two claims, the second file still empty and no later
        # file created yet.
        outcome = self.install()
        assert outcome.complete, outcome.stderr
        receipt = self.receipt_document()
        claims = receipt["files"][:2]
        for entry in receipt["files"][2:]:
            (self.game / entry["path"]).unlink()
        truncate_in_place(self.game / claims[1]["path"])
        receipt.update(status="installing", files=claims)
        rewrite_in_place(self.receipt(), json.dumps(receipt).encode("utf-8"))
        return str(claims[1]["path"])

    def planned(self) -> set[str]:
        return self.planned_claims() | {self.receipt_name}

    def planned_claims(self) -> set[str]:
        return {entry["path"] for entry in self.plan["files"]}

    def removable(self) -> set[str]:
        return self.planned()

    def owned(self) -> str:
        return self.owned_name

    def conflict(self) -> Path:
        return self.game / "winhttp.dll"

    def receipt(self) -> Path:
        return self.game / self.receipt_name

    def user_file(self) -> Path:
        return self.game / "UnityTranslatorPatch/user-notes.txt"

    def tamper_receipt(self) -> None:
        receipt = self.receipt_document()
        original = self.game / self.manifest()["game_executable"]
        receipt["files"][0] = {
            "path": original.name,
            "sha256": hash_file(original),
            "identity": identity(original),
        }
        self.receipt().write_text(json.dumps(receipt), encoding="utf-8")


class LegacyShareablePatch(ShareablePatch):
    name = "unity-shareable-556bf5e"
    legacy = True
    # Recorded legacy behaviour: after the typed confirmation only the game files and
    # process are checked again, so the create-new copy of the appeared loader file fails
    # and the installer rolls its additions back.
    late_destination = {
        REVIEW_RUN: ("Existing mod/patch found", False),
        CONFIRMATION: (CREATE_NEW_FAILED, False),
    }

    def setup(self) -> None:
        self.package, self.game, _ = legacy_fixture(self.name, self.tmp)
        self.root = self.game
        self.snapshot()

    def process_image(self) -> str:
        return str(self.manifest()["game_executable"])


class ReleaseCandidatePatch(LegacyShareablePatch):
    """0.1.0-rc.6/rc.7 patch.ps1: no review phase; one run checks, installs and rolls back."""

    has_review = False
    install_prompt = ""
    late_destination = {
        REVIEW_RUN: ("Existing mod/patch found", False),
        CONFIRMATION: ("Existing mod/patch found", False),
    }

    def review(self) -> Outcome:
        # The plan the old installer applies: package files plus the generated loader INI.
        files = [*self.manifest()["files"], {"path": "doorstop_config.ini"}]
        self.plan = {"files": files}
        return REVIEWED

    def apply(self) -> Outcome:
        return self.run("-Action", "Install", "-GameFolder", self.game)


class ReleaseCandidate6Patch(ReleaseCandidatePatch):
    name = "unity-shareable-9ba9495"


class ReleaseCandidate7Patch(ReleaseCandidatePatch):
    name = "unity-shareable-0b83e59"


# Ren'Py translated copy (renpy-copy.ps1, formats 1/2) -------------------------------------
class RenpyCopy(Driver):
    name = "renpy-copy-current"
    refusals = {
        "b": "A new independent copy directory is required",
        "g": "Receipt contains an unowned or changed file claim.",
        "h": "Receipt game/package identity mismatch.",
        "l": MISSING_RECEIPT,
    }
    install_prompt = "INSTALL"
    removal_prompt = "REMOVE"
    # The apply run repeats the pre-review target check; after the typed confirmation the
    # installer checks the copy target once more before creating it.
    late_destination = {
        REVIEW_RUN: ("A new independent copy directory is required", False),
        CONFIRMATION: ("Copy target appeared after review", False),
    }
    # The copy receipt is written once and never updated; each removal adds an audit report.
    preserved_status = "installed"
    # The first removal deletes the copied game EXE; the retry still knows the package's
    # executable name, so it completes.
    restored_retry_refusal = ""
    interrupted_removal = "refused"
    metadata = ".unitytranslator/renpy-copy"
    generated = (
        "install-start.json",
        "reviewed-plan.json",
        "install-journal.jsonl",
        "receipt.json",
    )

    def setup(self) -> None:
        from test_renpy_scripts import approve, fixture

        from unitytranslator.discovery import extract_to_project
        from unitytranslator.renpy_package import export_copy_package
        from unitytranslator.repository import ProjectRepository

        require_windows()
        monkeypatch = self.request.getfixturevalue("monkeypatch")
        paths, _ = fixture(self.tmp, 'label start:\n    e "One."\n    e "Two."\n')
        (paths.game / "Synthetic.exe").write_bytes(b"Synthetic EXE stand-in; never executed")
        extract_to_project(paths, "game/script.rpy")
        monkeypatch.setattr("unitytranslator.renpy_export.SHARD_RECORDS", 1)
        with ProjectRepository(paths) as repo:
            approve(repo, "One.", "Bir.")
            approve(repo, "Two.", "Iki.")
            result = export_copy_package(repo, "turkish")
        self.package = self.tmp / "copy package"
        with zipfile.ZipFile(result["path"]) as archive:
            archive.extractall(self.package)  # Fixed exporter-generated synthetic ZIP.
        assert self.manifest()["format_version"] == 2
        self.game = paths.game
        self.finish_setup()

    def finish_setup(self) -> None:
        self.output = self.tmp / "copy output"
        self.output.mkdir()
        self.root = self.output / self.manifest()["copy_folder"]
        self.snapshot()

    def manifest(self) -> dict[str, Any]:
        value: dict[str, Any] = json.loads((self.package / "package.json").read_bytes())
        return value

    def script(self) -> Path:
        return self.package / "renpy-copy.ps1"

    def run(self, *args: object) -> Outcome:
        return powershell(self.script(), *args)

    def interactive_install_arguments(self) -> tuple[object, ...]:
        return self.install_arguments()

    def interactive_removal_arguments(self) -> tuple[object, ...]:
        return self.removal_arguments(None)

    def install_arguments(self) -> tuple[object, ...]:
        return ("-GameFolder", self.game, "-OutputParent", self.output)

    def review(self) -> Outcome:
        review = self.run(*self.install_arguments(), "-ReviewOnly")
        if review.returncode == 0:
            self.plan = review.json()["plan"]
            self.plan_sha256 = review.json()["sha256"]
        return review

    def apply(self) -> Outcome:
        return self.run(*self.install_arguments(), "-ReviewedPlanSha256", self.plan_sha256)

    def removal_arguments(self, root: Path | None) -> tuple[object, ...]:
        return ("-Action", "Remove", "-InstallFolder", root or self.root)

    def review_removal(self, root: Path | None = None) -> Outcome:
        review = self.run(*self.removal_arguments(root), "-ReviewOnly")
        if review.returncode == 0:
            self.removal_sha256 = review.json()["sha256"]
        return review

    def apply_removal(self, root: Path | None = None) -> Outcome:
        arguments = (*self.removal_arguments(root), "-ReviewedPlanSha256", self.removal_sha256)
        removed = self.run(*arguments)
        if removed.returncode not in (0, 2):
            return removed
        report = removed.json()
        return Outcome(
            removed.returncode,
            removed.stdout,
            removed.stderr,
            tuple(report["changed_files_preserved"]),
        )

    def interrupt(self) -> str | None:
        # The copy receipt is written only after the last file. Reproduce a crash just
        # before that write from a complete install: journal and start marker, no receipt.
        outcome = self.install()
        assert outcome.complete, outcome.stderr
        self.receipt().unlink()
        return None

    def added(self) -> set[str]:
        return set(tree(self.root))

    def proofs(self) -> set[str]:
        """Generated start marker and reviewed plan that the receipt claims."""
        return {self.metadata + "/install-start.json", self.metadata + "/reviewed-plan.json"}

    def planned(self) -> set[str]:
        return {entry["path"] for entry in self.plan["files"]} | {
            self.metadata + "/" + name for name in self.generated
        }

    def planned_claims(self) -> set[str]:
        return {entry["path"] for entry in self.plan["files"]} | self.proofs()

    def removable(self) -> set[str]:
        return self.planned_claims()

    def owned(self) -> str:
        return str(self.manifest()["payloads"][0]["path"])

    def conflict(self) -> Path:
        return self.root / "user.txt"

    def receipt(self) -> Path:
        return self.root / self.metadata / "receipt.json"

    def user_file(self) -> Path:
        return self.root / "game/user-notes.txt"

    def watched(self) -> list[Path]:
        return [self.game, self.output]

    def tamper_receipt(self) -> None:
        unowned = self.root / "user-notes.txt"
        unowned.write_bytes(b"User file the receipt never owned")
        receipt = self.receipt_document()
        receipt["files"][0].update(
            path=unowned.name, sha256=hash_file(unowned), identity=identity(unowned)
        )
        self.receipt().write_text(json.dumps(receipt), encoding="utf-8")

    def relocate(self) -> Path:
        target = self.tmp / "relocated output" / self.root.name
        shutil.copytree(self.root, target)
        return target


class LegacyRenpyCopy(RenpyCopy):
    legacy = True
    # 0.5.0 matches only the copy's game_executable image, so a retry completes.
    restored_retry_refusal = ""

    def setup(self) -> None:
        self.package, self.game, entry = legacy_fixture(self.name, self.tmp)
        assert self.manifest()["format_version"] == entry["format_version"]
        self.finish_setup()

    def process_image(self) -> str:
        return str(self.manifest()["game_executable"])


class LegacyRenpyCopyFormat1(LegacyRenpyCopy):
    name = "renpy-copy-format1-556bf5e"


class LegacyRenpyCopyFormat2(LegacyRenpyCopy):
    name = "renpy-copy-format2-556bf5e"


# Ren'Py additive (renpy-copy.ps1 dispatching renpy-additive.ps1, format 3) ----------------
class RenpyAdditive(RenpyCopy):
    name = "renpy-additive-current"
    refusals = {
        "b": "A patch destination exists",
        "g": "Receipt claims an unowned file.",
        "h": "Installation game identity mismatch.",
        "l": MISSING_RECEIPT,
    }
    restored_retry_refusal = ""  # The original game EXE stays, so the retry completes.
    # The apply run repeats every destination check before its plan hash; after the typed
    # confirmation every planned destination is checked again before the first write.
    late_destination = {
        REVIEW_RUN: ("A patch destination exists", False),
        CONFIRMATION: ("A destination appeared after review", False),
    }

    def setup(self) -> None:
        from test_renpy_scripts import approve, fixture

        from unitytranslator.discovery import extract_to_project
        from unitytranslator.renpy_package import export_install_package
        from unitytranslator.repository import ProjectRepository

        require_windows()
        paths, _ = fixture(self.tmp)
        (paths.game / "Synthetic.exe").write_bytes(b"Synthetic EXE stand-in; never executed")
        extract_to_project(paths, "game/script.rpy")
        with ProjectRepository(paths) as repo:
            approve(repo, "Display", "Ekran")
            result = export_install_package(repo, "turkish")
        self.package = self.tmp / "additive package"
        with zipfile.ZipFile(result["path"]) as archive:
            archive.extractall(self.package)  # Fixed exporter-generated synthetic ZIP.
        self.game = self.root = paths.game
        self.snapshot()

    def install_arguments(self) -> tuple[object, ...]:
        return ("-GameFolder", self.game)

    def removal_arguments(self, root: Path | None) -> tuple[object, ...]:
        return ("-Action", "Remove", "-InstallFolder", root or self.game)

    def added(self) -> set[str]:
        return Driver.added(self)

    def proofs(self) -> set[str]:
        return {
            name
            for name in self.plan["generated_files"]
            if name.endswith(("/install-start.json", "/reviewed-plan.json"))
        }

    def planned(self) -> set[str]:
        return {entry["path"] for entry in self.plan["files"]} | set(self.plan["generated_files"])

    def removable(self) -> set[str]:
        # Removal keeps the audit metadata folder named by the reviewed plan.
        metadata = self.plan["retained_metadata"] + "/"
        return {
            entry["path"] for entry in self.plan["files"] if not entry["path"].startswith(metadata)
        }

    def conflict(self) -> Path:
        return self.game / "Play-Translated.cmd"

    def receipt(self) -> Path:
        return self.game / self.manifest()["metadata_folder"] / "receipt.json"

    def user_file(self) -> Path:
        return self.game / "game/tl" / self.manifest()["language"] / "user-notes.txt"

    def watched(self) -> list[Path]:
        return [self.game]

    def tamper_receipt(self) -> None:
        original = self.game / "game/script.rpy"
        receipt = self.receipt_document()
        receipt["files"][0].update(
            path="game/script.rpy", sha256=hash_file(original), identity=identity(original)
        )
        self.receipt().write_text(json.dumps(receipt), encoding="utf-8")

    def relocate(self) -> Path:
        return Driver.relocate(self)


class LegacyRenpyAdditive(RenpyAdditive):
    name = "renpy-additive-1e1dfc3"
    legacy = True
    # Recorded legacy behaviour: after the typed confirmation only the metadata and language
    # namespaces are checked again, so the launcher's create-new write fails mid-install
    # and leaves unreceipted additions.
    late_destination = {
        REVIEW_RUN: ("A patch destination exists", False),
        CONFIRMATION: (CREATE_NEW_FAILED, True),
    }

    def setup(self) -> None:
        self.package, self.game, _ = legacy_fixture(self.name, self.tmp)
        self.root = self.game
        self.snapshot()

    def process_image(self) -> str:
        return str(self.manifest()["game_executable"])


DRIVERS: tuple[type[Driver], ...] = (
    PythonDeployment,
    ShareablePatch,
    LegacyShareablePatch,
    ReleaseCandidate7Patch,
    ReleaseCandidate6Patch,
    RenpyCopy,
    LegacyRenpyCopyFormat1,
    LegacyRenpyCopyFormat2,
    RenpyAdditive,
    LegacyRenpyAdditive,
)
