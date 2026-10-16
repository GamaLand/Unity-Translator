"""Kaynak kategorisi ve uzunluğa göre tekrar üretilebilir, sınırlı pilot seçimi."""

from unitytranslator.repository import ProjectRepository


def select_pilot(repository: ProjectRepository, limit: int = 200) -> list[str]:
    if not 1 <= limit <= 200:
        raise ValueError("Pilot en fazla 200 kayıt olmalı.")
    categories = repository.db.execute(
        "SELECT s.category,count(*) FROM text_units u "
        "JOIN source_revisions s ON s.id=u.source_revision "
        "JOIN work_items w ON w.unit_id=u.unit_id WHERE u.active=1 AND w.status!='approved' "
        "AND w.translation_revision IS NULL GROUP BY s.category ORDER BY s.category"
    ).fetchall()
    groups: list[list[str]] = []
    for category, count in categories:
        quota = min(count, max(2, (limit // max(len(categories), 1)) + 2))
        candidates = []
        for index in range(quota):
            offset = round(index * (count - 1) / max(quota - 1, 1))
            row = repository.db.execute(
                "SELECT u.unit_id FROM text_units u "
                "JOIN source_revisions s ON s.id=u.source_revision "
                "JOIN work_items w ON w.unit_id=u.unit_id "
                "WHERE u.active=1 AND w.status!='approved' "
                "AND w.translation_revision IS NULL AND s.category=? "
                "ORDER BY length(s.source_text),u.unit_id LIMIT 1 OFFSET ?",
                (category, offset),
            ).fetchone()
            if row is not None:
                candidates.append(str(row[0]))
        # Round-robin sınırı son turu kesebilir; uzun uç örnek ikinci sıradadır.
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
    return selected
