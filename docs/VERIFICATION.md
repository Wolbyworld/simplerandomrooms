# V2 verification record

Run on 2026-07-17 in the feature worktree. All checks used a disposable local
SQLite database and `http://127.0.0.1:8001`; no production room, deployment,
DNS, or remote branch was changed.

| Layer | Command or check | Result |
| --- | --- | --- |
| Static correctness | `git diff --check` | Passed |
| Python compilation | `.venv/bin/python -m compileall -q app scripts tests` | Passed |
| Unit + HTTP + WebSocket integration | `.venv/bin/python -m pytest -q` | `66 passed` |
| HTTP health | `curl --fail --silent --show-error http://127.0.0.1:8001/health` | `{"status":"healthy"}` |
| API/CLI smoke | `.venv/bin/python scripts/random_draw_smoke.py --base-url http://127.0.0.1:8001 smoke` | Passed all 12 checks |
| Database migration regression | Included in the test suite against a V1-shaped SQLite database | Passed; legacy room/log data retained |

## Browser UAT

Chrome was used against the local server. Screenshots were captured during the
run for the desktop home, desktop room/settings, mobile home, mobile completed
team result, and sharing dialog.

- Desktop: created a host-only 1–3 number room directly from the home screen.
  Its three server results were distinct, appeared in the receipt-backed
  history, and ended in an explicit completed state with Draw disabled.
- Desktop: opened Settings, confirmed host controls, receipt controls, the
  draw policy, sound/haptics, and the room-language chooser. Switched to
  Spanish and confirmed both static and dynamically generated settings labels
  were localized.
- Mobile: used a real `390 x 844` browser viewport. The homepage showed the
  two-column mode picker, horizontally scrollable preset row, 44px-class
  controls, and a thumb-reachable primary action without horizontal page
  scrolling.
- Mobile: used **Split teams**, supplied four names, and drew a persisted,
  no-replacement result. It rendered as two balanced teams, showed an explicit
  completed state at zero remaining, disabled Draw, and preserved the result
  in history after a separate visitor opened the link.
- Sharing: opened the mobile share sheet and verified the participant-safe
  link, WhatsApp action, native-share control, and first-party SVG QR source.
- Accessibility: checked focus-visible semantics via the browser accessibility
  tree; icon-only mobile presence/share controls have localized accessible
  names; a polite live announcement fires only for a newly completed draw;
  keyboard draw excludes editable controls; CSS includes reduced-motion
  handling. Invalid weighted-list input is rejected inline, associated with its
  field, and retains the draft.

## Final review result

An independent fresh-context review of the full two-commit V2 implementation
and current worktree found and resolved the valid migration, accessibility,
input-validation, bidi-safety, and participant-presence issues. The regression
coverage is included in the `66 passed` suite above; no unresolved valid review
findings remain.

The browser viewport override was reset after testing.
