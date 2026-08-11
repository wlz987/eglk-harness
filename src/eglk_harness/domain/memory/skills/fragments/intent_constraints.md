## Intent alignment & set completeness (harness core)

- `custom_attestation` / Summary-level obligations: `satisfied` requires **independent observation** — never Maker `coverage` / `process_coverage` self-report alone.
- Multi-value `retrieved_data` / list deliverables: cross-check DOM/HAR/table rows; if observation still shows matching items not listed → `unsatisfied` with concrete gap strings.
- Summary cue words (filter / sort / pagination / all / every / how many / total number) must appear in observation — do not invent answers for Maker.
- Scout MCP (`*scout*` on allowlist) before shell parsing giant HAR; shell is fallback only.
- `process_coverage.json` / `coverage_note.json`: validate structure only at boundary; truth of `enumeration_exhausted` is Checker cross-observation.

### Semantic qualifier checklist (no answers)

Before binding list/array fields, scan Summary for constraint words and verify matching UI filter/sort was applied:

| Cue in Summary | Verify on page |
|---|---|
| status / state / pending / complete / closed | Status/state column filter matches intent |
| exact count / number of / how many | Full pagination/enumeration scan, not first page only |
| most recent / latest / newest | Sort order = date descending (not default) |
| oldest / earliest | Sort order = date ascending |
| top / highest / best / ranked | Ranking metric matches (votes, rating, sales) |
| tie / equal / same | Tie-break rule applied consistently |
| filter / only / excluding | Filter inputs match entity names from Summary |

If a cue is present but observed filter/sort/pagination does not reflect it → gap before claiming `satisfied`.

### Maker second-pass (advisory)

For enumeration/list goals: independent re-scan before writing `retrieved_data`. `process_coverage` sidecars are process narrative — not exhaustive proof.
