"""Test-only install driver for synthetic, non-experimental deployment plans.

Production installs reach ``DeploymentService._activate_checked`` only through
``install_experimental_trial`` (I2 and Krypta reviewed trials). The generic public
``activate`` had no production caller and was removed; ownership, receipt and removal
tests still drive the shared create-new path with synthetic adapters through this helper.
"""

from typing import Any

from unitytranslator.deployment import DeploymentPlan, DeploymentService

EXPERIMENTAL_ADAPTERS = frozenset(
    {"i2mono-experimental-trial", "krypta-textassets-experimental-trial"}
)


def install_synthetic_plan(service: DeploymentService, plan: DeploymentPlan) -> dict[str, Any]:
    """Install a prepared synthetic plan through the shared checked create-new path."""
    if plan.adapter in EXPERIMENTAL_ADAPTERS:
        raise AssertionError("Experimental plans must use install_experimental_trial in tests.")
    return service._activate_checked(plan)
