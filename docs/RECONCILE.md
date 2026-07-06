# RECONCILE — merging with existing Claude settings

The target machine may already have Claude Code configuration. These rules govern every write,
during both setup and migration.

## Principles

1. **Backup first.** `apply.py backup` before anything. Tell Leo where the backup is.
2. **Ownership.** leos-claude owns exactly what's recorded (with content hashes / value
   snapshots) in `~/.claude/leos-claude.json`. `apply.py` enforces this mechanically: it
   overwrites/removes ONLY content matching an owned snapshot or listed in the manifest as ours
   and absent/identical. Everything else is Leo's — merge around it.
3. **settings.json is merged, never replaced.** Our fragment's keys are added; arrays
   (deny/allow) are union-deduped; keys we don't ship are untouched.
4. **Conflicts → ASK, with specifics.** A conflict = same key different value (settings), an
   existing file with unowned content at one of our destinations, an existing hook on the same
   event with a different command, or an existing council-like/review system. Present Leo both
   sides and concrete options (keep theirs / take ours / merge). Apply his choice via
   `--force-dest` only after explicit approval.
5. **Existing hooks on the same events are fine** — hook arrays are additive; multiple entries
   coexist. Only flag genuinely duplicated *functionality* (e.g. another rm-guard or another
   Stop-gate review system) and ask whether to keep both.
6. **Never delete non-owned files or settings keys**, even ones that look obsolete. List them
   in your report instead and let Leo decide.
7. **Uncertainty rule (Leo's own words): when unsure, ASK.** Machine-specific vs universal is
   his call, not yours.
