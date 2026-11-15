"""One ownership scenario suite against every recipient implementation.

Covers the in-app Python DeploymentService, the current shareable patch, Ren'Py copy and
Ren'Py additive installers, and frozen synthetic packages from earlier releases (see
tests/fixtures/legacy-recipients/README.md). Synthetic data only; no game is started.

Per-implementation differences are explicit driver attributes in recipient_drivers.py
(``refusals``, ``late_destination``, ``preserved_status``, ``restored_retry_refusal``,
``interrupted_removal``), never skips or expected failures. Scenarios b2, i2 and j change
the game inside two windows: between a review run and the reviewed apply run, and while an
interactive run waits for its typed confirmation. Implementations without that prompt run
the review-run window twice. Scenario l reproduces each implementation's crash state
(see ``Driver.interrupt``); only the in-app service is interrupted in process.
"""

import os
import shutil
from contextlib import contextmanager

import pytest
from recipient_drivers import DRIVERS, WINDOWS, Driver, live_image, tree
from test_shareable import krypta_project  # noqa: F401
from test_textasset_pipeline import repo as synthetic_repo  # noqa: F401

USER_BYTES = b"User file; ownership never claimed by the installer"


@pytest.fixture(params=DRIVERS, ids=[driver.name for driver in DRIVERS])
def driver(request, tmp_path):
    instance: Driver = request.param(request, tmp_path)
    if instance.windows and os.name != "nt":
        pytest.skip("Windows PowerShell recipient installers run only on Windows")
    instance.setup()
    return instance


def require_live_images():
    if os.name != "nt" or shutil.which("powershell.exe") is None:
        pytest.skip("Live process images are checked only on Windows")


def install(driver):
    outcome = driver.install()
    assert outcome.complete, outcome.stderr
    return outcome


def unchanged(roots, before):
    return [tree(root) for root in roots] == before


def place_user_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(USER_BYTES)


def test_a_install_adds_only_planned_new_files_and_keeps_originals(driver):
    install(driver)
    assert driver.added() == driver.planned()
    # The installer's own receipt claims exactly the files the reviewed plan creates.
    assert driver.receipt_claims() == driver.planned_claims()
    assert driver.receipt_status() == "installed"
    assert driver.originals_unchanged()
    if driver.root != driver.game:
        assert tree(driver.game) == driver.originals


def test_b_existing_target_refuses_before_any_write(driver):
    conflict = driver.conflict()
    place_user_file(conflict)
    roots = driver.watched()
    before = [tree(root) for root in roots]
    outcome = driver.install()
    assert outcome.returncode != 0 and driver.refusals["b"] in outcome.stderr, outcome.stderr
    assert conflict.read_bytes() == USER_BYTES
    assert unchanged(roots, before)
    assert not driver.receipt().exists()


@pytest.mark.parametrize("window", WINDOWS)
def test_b2_destination_appearing_after_review_is_refused(driver, window):
    conflict = driver.conflict()
    roots = driver.watched()
    before = []

    @contextmanager
    def destination_appears():
        place_user_file(conflict)
        before.extend(tree(root) for root in roots)
        yield

    outcome = driver.install_across(window, destination_appears)
    refusal, partial = driver.late_destination[window]
    assert outcome.returncode != 0 and refusal in outcome.stderr, outcome.stderr
    assert conflict.read_bytes() == USER_BYTES
    assert driver.originals_unchanged()
    assert not driver.receipt().exists()
    if not partial:
        assert unchanged(roots, before)
        return
    # Recorded behaviour: the refused install leaves unreceipted partial additions that
    # its own Remove cannot claim, and a rerun refuses the existing namespace.
    left = driver.added() - {conflict.relative_to(driver.root).as_posix()}
    assert left and left <= driver.planned()
    after = tree(driver.root)
    removal = driver.remove()
    assert removal.returncode != 0 and driver.refusals["l"] in removal.stderr, removal.stderr
    assert tree(driver.root) == after
    assert driver.install().returncode != 0
    assert tree(driver.root) == after


def test_c_removal_deletes_unchanged_owned_files_only(driver):
    install(driver)
    removable = driver.removable()  # From the reviewed plan, not from the receipt.
    assert removable and removable <= driver.added()
    user = driver.user_file()
    place_user_file(user)
    kept = set(tree(driver.root)) - removable
    outcome = driver.remove()
    assert outcome.complete, outcome.stderr
    assert not any((driver.root / name).exists() for name in removable)
    assert all((driver.root / name).exists() for name in kept)
    assert user.read_bytes() == USER_BYTES
    assert driver.originals_unchanged()


def preserved_after_removal(driver, owned, expected):
    outcome = driver.remove()
    # Every implementation reports the preserved file: a failing exit, recovery status or
    # a partial-removal report, never a silent success.
    assert not outcome.complete and driver.owned() in outcome.preserved, outcome.stderr
    assert owned.read_bytes() == expected
    assert driver.originals_unchanged()


def test_d_modified_owned_file_is_preserved_and_reported(driver):
    install(driver)
    owned = driver.root / driver.owned()
    owned.write_bytes(b"User-edited owned file")
    preserved_after_removal(driver, owned, b"User-edited owned file")


def test_e_owned_file_with_new_identity_is_preserved(driver, tmp_path):
    install(driver)
    owned = driver.root / driver.owned()
    data = owned.read_bytes()
    owned.rename(tmp_path / "moved-away-owned-file")  # The old identity stays alive.
    owned.write_bytes(data)
    preserved_after_removal(driver, owned, data)


def test_f_hard_linked_owned_file_is_preserved(driver, tmp_path):
    install(driver)
    owned = driver.root / driver.owned()
    data = owned.read_bytes()
    alias = tmp_path / "user-hard-link"
    try:
        os.link(owned, alias)
    except OSError:
        pytest.skip("Hard links are unavailable on this file system")
    preserved_after_removal(driver, owned, data)
    assert alias.read_bytes() == data


def test_g_tampered_receipt_claiming_unowned_file_deletes_nothing(driver):
    install(driver)
    driver.tamper_receipt()
    receipt = driver.receipt()
    before = tree(driver.root)
    outcome = driver.remove()
    assert outcome.returncode != 0 and driver.refusals["g"] in outcome.stderr, outcome.stderr
    after = tree(driver.root)
    assert all(
        after.get(name) == digest for name, digest in before.items()
        if driver.root / name != receipt
    )  # fmt: skip
    assert receipt.exists()
    assert driver.originals_unchanged()


def test_h_receipt_of_a_different_game_location_is_refused(driver):
    install(driver)
    installed = tree(driver.root)
    relocated = driver.relocate()
    copied = tree(relocated)
    outcome = driver.remove(relocated)
    assert outcome.returncode != 0 and driver.refusals["h"] in outcome.stderr, outcome.stderr
    assert tree(relocated) == copied
    assert tree(driver.root) == installed


def test_i_process_image_under_game_root_blocks_install(driver):
    require_live_images()
    # Current installers refuse any image under the game root, so a helper path is used.
    # The frozen 0.1.0-rc/0.5.0/1e1dfc3 installers match only the manifest game_executable
    # image; their synthetic stand-in at that path is replaced by the copied cmd.exe.
    with live_image(driver.game / driver.process_image()):
        driver.snapshot()
        roots = driver.watched()
        before = [tree(root) for root in roots]
        outcome = driver.install()
        assert driver.refused_by_process(outcome), outcome.stderr
        assert unchanged(roots, before)
        assert not driver.receipt().exists()


def game_starts(driver, image, roots, before):
    """Start the stand-in at ``image`` and record the watched trees while it runs."""

    @contextmanager
    def change():
        with live_image(image):
            driver.snapshot()  # Frozen installers' stand-in replaces the original EXE.
            before.extend(tree(root) for root in roots)
            yield

    return change


@pytest.mark.parametrize("window", WINDOWS)
def test_i2_process_starting_after_review_blocks_install(driver, window):
    require_live_images()
    roots = driver.watched()
    before = []
    change = game_starts(driver, driver.game / driver.process_image(), roots, before)
    outcome = driver.install_across(window, change)
    assert driver.refused_by_process(outcome), outcome.stderr
    assert unchanged(roots, before)
    assert not driver.receipt().exists()


@pytest.mark.parametrize("window", ["before-review", *WINDOWS])
def test_j_removal_while_game_runs_deletes_nothing(driver, window):
    require_live_images()
    install(driver)
    receipt = driver.receipt().read_bytes()
    # The removal checks the folder it removes from: the game, or the translated copy.
    roots = [*driver.watched(), driver.root]
    before = []
    change = game_starts(driver, driver.root / driver.process_image(), roots, before)
    if window == "before-review":
        with change():
            outcome = driver.remove()
    else:
        outcome = driver.remove_across(window, change)
    assert driver.refused_by_process(outcome), outcome.stderr
    assert unchanged(roots, before)
    assert driver.receipt().read_bytes() == receipt


def test_k_restored_owned_file_completes_a_second_removal(driver):
    install(driver)
    removable = driver.removable()
    owned = driver.root / driver.owned()
    data = owned.read_bytes()
    owned.write_bytes(b"User-edited owned file")  # Same file identity, new bytes.
    first = driver.remove()
    assert not first.complete and driver.owned() in first.preserved, first.stderr
    assert driver.receipt_status() == driver.preserved_status
    owned.write_bytes(data)
    after_first = tree(driver.root)
    second = driver.remove()
    assert driver.originals_unchanged()
    if driver.restored_retry_refusal:
        refused = second.returncode != 0 and driver.restored_retry_refusal in second.stderr
        assert refused, second.stderr
        assert tree(driver.root) == after_first
        return
    assert second.complete, second.stderr
    assert not any((driver.root / name).exists() for name in removable)


def test_l_interrupted_install_is_never_overwritten_and_removal_is_bounded(driver):
    partial = driver.interrupt()
    roots = [*driver.watched(), driver.root]
    before = [tree(root) for root in roots]
    # A rerun never writes over an interrupted installation.
    rerun = driver.install()
    assert rerun.returncode != 0, rerun.stdout
    assert unchanged(roots, before)
    claimed = driver.receipt_claims() if driver.receipt().exists() else set()
    outcome = driver.remove()
    if driver.interrupted_removal == "refused":
        # No receipt was written yet, so the installer's Remove claims nothing.
        assert partial is None and not claimed
        assert outcome.returncode != 0 and driver.refusals["l"] in outcome.stderr
        assert unchanged(roots, before)
        return
    # Unchanged claimed files are removed; the partially written claim is preserved.
    assert partial in claimed
    assert not outcome.complete and outcome.preserved == (partial,), outcome.stderr
    assert (driver.root / partial).exists()
    assert not any((driver.root / name).exists() for name in claimed - {partial})
    assert driver.receipt_status() == "recovery_required"
    assert driver.originals_unchanged()
    # After the user deletes the partial file, removal completes.
    (driver.root / partial).unlink()
    again = driver.remove()
    assert again.complete, again.stderr
    assert driver.originals_unchanged()
