# Translation quality and review

## Pipeline

The shared pipeline pins source revisions, model/profile settings, prompt version,
glossary and style versions. It masks supported placeholders/tags before requesting
translation and restores them only after verifying the response schema and exact
record identifiers. Model output is never a command, path, executable or tool call.
Missing/extra records, duplicate JSON keys, invalid values, truncated output and
unexpected tool calls are rejected. Retries are bounded and share a durable budget.

The protected format is currently `protected-i2-v4`; multilingual review checks are
`review-multilingual-v5`. Changes to format rules require explicit versioning and
shared Python/C# fixtures. A future JSON/CSV reader must not assume that the I2 grammar
is valid for its source format.

## Current protected grammar

The I2 adapter recognizes positional/named parameters such as `{0}`, `{name}`, `{[N]}`,
and bounded numeric formatting such as `{0:F2}`. Its supported rich text includes
balanced `b`, `i`, `color` and bounded `size` tags plus the verified sprite-name form.
Line endings and protected tokens remain exact. Unknown or unbalanced syntax is
rejected rather than silently modified. The implementation and shared fixtures are
the authoritative grammar, not this illustrative list.

Known I2 plural branches are the default `Plural` branch and explicit `One`/`Zero`
markers. Branches are translated independently with exact IDs and reconstructed in
source order. Markers, placeholders and content cannot move between branches.
Unknown/duplicate/empty branches are rejected. Every plural record requires review;
retaining its source branches does not guarantee the target language's plural rules.

## Review checks

All language pairs receive unchanged-text, numeric, percentage, protected-format and
applicable glossary checks. Unambiguous numeric separators are normalized for supported
conventions; an uncertain format is not declared equivalent. Source and target glossary
matching use their own language's case rules. Context can distinguish identical source
strings; identical text never forces identical translations.

English-to-Turkish has additional narrow negation and gameplay-condition hints. Other
pairs do not inherit those language-specific heuristics. A clean automatic report is
not proof of correct meaning, tone, terminology, glyph coverage or layout.

## Approvals and drafts

A reviewed pilot permits a bulk job for its matching profile/source state; it is not
approval of every translation. Changed profiles or source state invalidate that gate.
Manual approval is tied to exact source/translation revisions. Automatic results and
imports never overwrite a currently approved translation. A changed source makes the
old approval stale.

Unsaved human edits are stored separately as editor drafts, with optimistic revision
checks. Page approval considers only reviewed, eligible records on the current page.
Whole-project approval requires scope acknowledgement and an exact count-bearing
confirmation in a second step. The preview is revalidated atomically; a changed list
cannot result in partial approval. Legacy internal confirmation data remains invariant
and must not be translated during UI cleanup.

## Jobs and verification

The independent asyncio/SQLite owner thread continues when the window is minimized.
Concurrency is user-selected from 1 to 16; server/model capacity still limits throughput.
Pause stops new claims and saves in-flight results; cancellation waits for client tasks
to close. Recovery requeues interrupted work while retaining attempts/revisions.
Bounded request timeouts can pause/fail work; this is different from window focus.

Synthetic checks validate boundaries and recovery. Human language review and targeted
in-game checks validate meaning, fonts, dynamic values and display. Do not repeatedly
request broad manual game tests for documentation or packaging-only changes.
