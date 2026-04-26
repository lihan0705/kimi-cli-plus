# Shadow Git Rewind Design

## Goal

Replace the current copy-based workspace checkpoint implementation behind `/tree`
with a shadow git backend that matches Gemini CLI's checkpoint model more closely:

- keep checkpoint storage out of the user's project `.git`
- snapshot workspace state before file-changing actions
- show per-checkpoint file change status in the rewind UI
- restore files and conversation together from a selected checkpoint

## Scope

This change is limited to rewind and workspace checkpoint behavior in:

- `src/kimi_cli/soul/workspace_checkpoint.py`
- `src/kimi_cli/ui/shell/tree.py`
- the shell tests for `/tree`
- the unit tests for workspace checkpoint preview and restore

This design does not change:

- the linear `context.jsonl` conversation format
- D-Mail checkpoint semantics
- web memory-palace work
- external side effects outside the workspace
- the general `/tree` command surface

## Current State

`/tree` already supports:

- selecting a prior checkpoint from the conversation timeline
- rewinding conversation only
- optionally restoring files when a workspace checkpoint exists

The current workspace checkpoint implementation copies the full worktree into a
session-local snapshot directory and compares file bytes directly for restore
preview. This works for a first slice, but it has several problems:

- storage grows linearly with the full workspace size
- preview cost scales with repeated full-tree scans and byte comparisons
- checkpoint metadata is weaker than a commit-oriented model
- the `/tree` picker cannot cheaply show per-checkpoint file change counts
- the implementation diverges from the Gemini CLI model the user wants

## Problem

The current rewind UX is functionally correct but too primitive:

- users only see checkpoint id and title in the picker
- file impact is hidden until after selecting restore mode
- workspace snapshots are heavy and opaque

The backend is also the wrong abstraction for long-term rewind work. A
commit-based shadow repo gives us a stable identity per checkpoint, cheap diffs,
and a cleaner foundation for later web and branching views.

## Decision

Adopt a session-local shadow git repository as the only workspace checkpoint
backend.

Each conversation checkpoint that needs file restore support maps to a git commit
in the shadow repo. The shadow repo uses:

- `GIT_DIR=<session_dir>/workspace-checkpoints/history/.git`
- `GIT_WORK_TREE=<work_dir>`

This repo is private to Kimi. It must never touch the user's project `.git`,
global git config, or git status.

The `/tree` picker will show file restore status for every checkpoint:

- `No file changes`
- `<n> file changes`
- `Files restorable` is implied by the count being available

The confirm step will still show the concrete `A/D/M path` preview before any
restore is applied.

## Design

### Storage Layout

Workspace checkpoint state stays under the session directory:

```text
<session_dir>/workspace-checkpoints/
  history/
    .git/
  index.json
```

`index.json` maps `conversation_checkpoint_id` to:

- `conversation_checkpoint_id`
- `snapshot_ref` (commit hash)
- `reason`
- `created_at`

No copied worktree snapshots are stored.

### Shadow Git Initialization

`WorkspaceCheckpointStore` initializes the shadow repo lazily on first write.

Rules:

- create the repo with `git init`
- operate with a clean env so user aliases and config do not affect behavior
- set fixed author/committer identity such as `Kimi CLI <kimi@example.invalid>`
- disable global config lookups where practical

If `git` is unavailable, checkpoint creation and restore must fail with a clear
error. Conversation-only rewind remains available.

### Checkpoint Creation

`create_once(conversation_checkpoint_id, reason=...)` becomes commit-based.

Flow:

1. If the checkpoint id already exists in `index.json`, return it.
2. Ensure the shadow repo exists.
3. Stage workspace content in the shadow repo view.
4. If there is no diff from `HEAD`, reuse the current `HEAD` commit hash.
5. If there is a diff, create a new commit with a deterministic message such as
   `checkpoint <id>: <reason>`.
6. Persist the commit hash into `index.json`.

This keeps the current "at most one workspace checkpoint per conversation
checkpoint id" rule while deduplicating identical states.

### File Inclusion Rules

The current excluded-directory behavior remains:

- `.git`
- virtualenv directories
- cache directories
- build outputs
- `node_modules`
- similar generated trees already excluded today

The exclusion rule should be applied consistently to:

- git add paths
- preview diff paths
- restore cleanup paths

This keeps restore focused on editable project files and avoids expensive churn
from generated artifacts.

### Preview Model

The store should expose two levels of preview:

1. `preview_restore(checkpoint_id)`:
   returns the detailed `A/D/M path` list versus the current workspace.
2. `preview_checkpoint(checkpoint_id)`:
   returns a lightweight summary for the picker:
   `change_count` and optionally `has_changes`.

Implementation detail:

- both previews are derived from `git diff --name-status <snapshot_ref>`
- the lightweight preview can reuse the detailed diff output, but the API should
  separate picker needs from confirm-step needs

### `/tree` UX

The checkpoint selection list changes from:

```text
#3 fix auth
```

to:

```text
#3 fix auth  2 file changes
#4 add docs  No file changes
```

Behavior:

- every checkpoint row shows file change status when a workspace checkpoint
  exists
- checkpoints without workspace metadata show no restore count and still allow
  conversation-only rewind
- selecting a checkpoint still leads to mode selection:
  `Conversation only`, `Conversation + restore files`, `Cancel`
- the restore mode remains hidden or unavailable when no workspace checkpoint
  exists for that checkpoint

The confirm restore dialog still prints the explicit changed file list before the
yes/no prompt.

### Restore Semantics

Restore remains all-or-nothing.

Flow:

1. Validate that the conversation checkpoint exists.
2. Validate that a workspace checkpoint exists.
3. Create a pre-restore safety commit or snapshot ref for the current workspace.
4. Compute and print the preview diff.
5. Ask for confirmation.
6. Restore files from the target commit into the real workspace.
7. Rewind conversation.
8. Append the continuation note.

Implementation detail:

- use git restore or checkout semantics against the target commit for tracked
  files inside the shadow repo view
- remove files that exist in the current workspace but not in the target commit
  within the allowed inclusion set

If file restore fails, conversation rewind must not happen.

### Safety Snapshot Before Restore

The existing "pre-restore snapshot" guarantee remains, but the mechanism changes
from directory copy to a shadow git commit reference.

The first implementation can keep this metadata out of `index.json` if it is
only used for emergency recovery, but it should be stored in a way that is
inspectable during debugging, for example with a commit message prefix such as:

```text
pre-restore <checkpoint_id>
```

### API Shape

`RestorePreview` should grow from:

- `conversation_checkpoint_id`
- `changed_files`

to also include:

- `change_count`

Optionally a second dataclass such as `CheckpointPreview` can represent picker
state:

- `conversation_checkpoint_id`
- `change_count | None`
- `restorable`

The shell layer should not need to understand git. It consumes typed preview
data from `WorkspaceCheckpointStore`.

### Testing

Update tests to cover:

- lazy shadow repo initialization
- checkpoint creation reuses the same commit for identical content
- preview returns correct `A/D/M` records
- preview exposes `change_count`
- restore handles modified, added, and deleted files
- excluded directories remain untouched by restore
- `/tree` picker rows include `No file changes` or `<n> file changes`
- restore mode still runs before conversation rewind

Tests should use temporary work dirs and a real local git binary. If git is
missing in the test environment, fail clearly rather than silently skipping core
behavior.

## Risks

The main risks are:

- shadow git commands behaving differently across platforms if env isolation is
  incomplete
- excluded-path behavior drifting between add, diff, and restore
- restore accidentally touching files outside the intended inclusion set

These are manageable if the store remains the single owner of:

- path filtering
- git command construction
- preview parsing
- restore cleanup

## Migration

Old sessions created with copy-based snapshots do not need automatic migration.

Pragmatic rule:

- new sessions use shadow git
- old sessions can continue conversation-only rewind
- if old session restore metadata is encountered, the store may report that file
  restore is unavailable for that checkpoint

This avoids mixed backends inside one session and keeps the implementation
small.

## Success Criteria

The change is complete when:

- `/tree` shows file change counts per checkpoint
- workspace checkpoints are backed by a shadow git repo instead of copied
  snapshots
- restore preview still shows concrete file-level changes
- restore still happens before conversation rewind
- unit and shell tests cover the new behavior
