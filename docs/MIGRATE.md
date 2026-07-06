# MIGRATE — upgrading an existing install

Trigger: Leo says something like "Leo's Claude has been upgraded, here is the repo, please
upgrade."

1. `git pull` (or fresh clone). Read `VERSION` and `CHANGELOG.md`.
2. Read installed state: `~/.claude/leos-claude.json` (version, ownership, recorded answers).
   - No profile file → this machine was never set up → docs/SETUP.md instead.
   - Installed ≥ repo version → run `python3 tools/apply.py verify --repo .` first: green →
     report "already current", stop; red → repair the drift before stopping.
3. For each CHANGELOG entry NEWER than the installed version, **in ascending order**, read its
   **Migration actions** and execute them. These are imperative and complete — you never need
   to read git diffs. Removals are explicit (use `apply.py remove` / the manifest `removed`
   list — it refuses unowned content; ask Leo on refusal). Removal applies to copy-strategy
   files ONLY: settings keys are retired by the new version's shrunken fragment, never by
   deleting settings.json.
4. `python3 tools/apply.py plan --repo .` → review states; resolve any conflicts with Leo per
   docs/RECONCILE.md. Then `backup`, `apply`, `verify` (same as setup step 9).
5. If a new version adds interview questions (a Migration action will say so): ask ONLY the new
   questions — re-use recorded answers for everything else.
6. Re-run all three test batteries. ALL PASS required.
7. `python3 tools/apply.py record --repo <path> --version <new> --tag v<new>` (answers file only
   if new answers were collected).
8. Report to Leo: versions traversed (e.g. v2 → v4), what changed on this machine, what was
   removed, any refusals/deferrals, test results.

Rules that always apply: backup before writes; ownership-gated overwrites only; conflicts and
uncertainty → ASK Leo; never remove anything `apply.py` reports as unowned without his explicit
approval.
