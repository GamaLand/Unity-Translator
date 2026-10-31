"""Deterministic bounded pilot selection by source category and length."""

from unitytranslator.repository import ProjectRepository


def select_pilot(repository: ProjectRepository, limit: int = 200) -> list[str]:
    if not 1 <= limit <= 200:
        raise ValueError("Pilot en fazla 200 kayıt olmalı.")
    # Read and order the eligible inventory once. Repeating a full join/sort for
    # every sampled offset makes large projects appear stuck before the first job.
    rows = repository.db.execute(
        "SELECT s.category,u.unit_id FROM text_units u "
        "JOIN source_revisions s ON s.id=u.source_revision "
        "JOIN work_items w ON w.unit_id=u.unit_id WHERE u.active=1 AND w.status!='approved' "
        "AND w.translation_revision IS NULL "
        "ORDER BY s.category,length(s.source_text),u.unit_id"
    )
    inventory: dict[str, list[str]] = {}
    for index, row in enumerate(rows):
        if index % 1024 == 0:
            repository.check_cancelled()
        inventory.setdefault(str(row[0]), []).append(str(row[1]))
    groups: list[list[str]] = []
    for units in inventory.values():
        count = len(units)
        quota = min(count, max(2, (limit // max(len(inventory), 1)) + 2))
        candidates = []
        for index in range(quota):
            offset = round(index * (count - 1) / max(quota - 1, 1))
            candidates.append(units[offset])
        # The last round may be truncated; put the long-edge example second.
        if len(candidates) > 2:
            candidates = [candidates[0], candidates[-1], *candidates[1:-1]]
        groups.append(candidates)
    selected: list[str] = []
    while any(groups) and len(selected) < limit:
        for group in groups:
            if group and len(selected) < limit:
                item = group.pop(0)
                if item not in selected:
                    selected.append(item)
    if len(selected) < limit:
        # A small category may not fill its quota. Fill the remaining sample from
        # eligible records so that a sufficient corpus can meet the bulk gate.
        seen = set(selected)
        for units in inventory.values():
            for unit in units:
                if unit not in seen:
                    selected.append(unit)
                    seen.add(unit)
                if len(selected) == limit:
                    break
            if len(selected) == limit:
                break
    repository.check_cancelled()
    return selected
