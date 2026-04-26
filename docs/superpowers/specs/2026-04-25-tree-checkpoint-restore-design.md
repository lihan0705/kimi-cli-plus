# `/tree` Checkpoint Restore Design

## Goal

Add a CLI-first `/tree` workflow that lets a user inspect prior conversation turns, choose a point
to continue from, and decide whether only the conversation should move back or the workspace files
should also be restored to that point.

This is the foundation for a later "memory palace" view: every important point in an agent session
can become a navigable room with the user goal, agent result, file changes, tests, and distilled
knowledge attached.

## Non-Goals

- Do not build the web memory palace UI in this first version.
- Do not replace the current `context.jsonl` format with a full append-only session tree yet.
- Do not silently restore files. File restore always requires an explicit user choice.
- Do not try to restore external state such as databases, network side effects, package caches, or
  commands run outside the workspace.

## Current State

Kimi currently stores conversation context as a linear JSONL file. `Context.checkpoint()` appends
internal `_checkpoint` records, and `Context.revert_to(checkpoint_id)` rotates the current context
file then rewrites it up to the selected checkpoint. This supports internal D-Mail context cleanup,
but it is destructive from the active session's point of view and has no user-facing tree UI.

Sessions also have a `state.json` for persisted UI/runtime state. The shell has slash commands for
`/clear`, `/new`, `/sessions`, `/export`, and `/import`, but no `/tree`, `/rewind`, or file restore
command.

## Approaches Considered

### A. Full Pi-Style Append-Only Conversation Tree

Store every context entry with `id` and `parent_id`, keep a session `leaf_id`, and build LLM context
from the active path. This is the cleanest long-term model for branching and memory palace views.

Tradeoff: it touches the core context model, import/export, compaction, web replay, ACP, and tests.
It is too large for the first slice.

### B. Hermes-Style Rollback Only

Keep conversation linear and add shadow-git checkpoints before file-changing tools. `/rollback`
would restore files and remove the latest conversation turn.

Tradeoff: this solves safety but not the desired `/tree` navigation or future memory palace model.

### C. Linear `/tree` MVP With Checkpoint Metadata

Keep the existing linear context file for now. Build a turn/checkpoint index from `context.jsonl`,
show it through a CLI picker, and implement two actions:

- `Conversation only`: rotate/rewrite context back to the selected checkpoint and append a system
  note that the user chose to continue from that point.
- `Conversation + restore files`: restore workspace files from a checkpoint snapshot, then perform
  the same conversation rewind.

This is the recommended first version. It is small enough to ship, matches the current architecture,
and introduces the metadata needed for a later append-only tree.

## Recommended Design

### User Experience

`/tree` opens an interactive list of conversation points. Each row shows:

- checkpoint id
- approximate turn title from the following real user message
- relative time when available
- file checkpoint status: none, available, or unavailable
- changed file count when known

After selecting a point, the CLI prompts:

```text
Continue from this point:
  1. Conversation only
  2. Conversation + restore files
  3. Cancel
```

`Conversation only` is always available. `Conversation + restore files` is only available when a
workspace checkpoint exists for that conversation checkpoint. If no workspace checkpoint exists, the
UI explains that only conversation rewind is possible.

Before restoring files, the CLI prints a concise restore preview:

```text
Files that may change:
  M src/...
  D ...
  A ...
```

The user must confirm before restore is applied.

### Conversation Model

For the first version, `/tree` uses existing checkpoint records. The selected point maps to a
`checkpoint_id`, and conversation rewind calls a new user-facing wrapper around
`Context.revert_to(checkpoint_id)`.

After the rewind, Kimi appends a synthetic user/system message:

```text
The user rewound the conversation to checkpoint <id> and chose <mode>. Continue from that point.
```

This prevents the next model step from being confused by a sudden truncation.

Unlike D-Mail, this message is user-facing in intent and should be visible in exported context as a
normal session event, not hidden as a private future-self instruction.

### Workspace Checkpoints

Add a workspace checkpoint layer separate from `Context`. It should be a small service owned by the
runtime/session layer, not by individual tools.

The MVP should use a shadow git repository under the session directory:

```text
<session_dir>/workspace-checkpoints/
```

It must not write to or modify the user's project `.git`.

Each checkpoint records:

- `conversation_checkpoint_id`
- `snapshot_ref`
- `created_at`
- `work_dir`
- changed file summary
- restore capability status

For Git workspaces, the implementation can snapshot the worktree content into the shadow repo. For
non-Git workspaces, the same shadow repo approach can still work by copying tracked snapshot content
from the workspace into the shadow index. Large ignored directories must be excluded using the same
directory ignore rules as file search where practical.

The first implementation may limit restore to regular files under the primary work directory and
document that generated caches and ignored build outputs are excluded.

### Checkpoint Timing

The safest first rule is:

- create a conversation checkpoint as Kimi already does before user turns and agent steps;
- create a workspace checkpoint before tools that can modify files or run risky commands.

File-changing tools include:

- `WriteFile`
- `StrReplaceFile`

Shell checkpointing should start conservative:

- create a workspace checkpoint before any `Shell` command that is not obviously read-only;
- later refine with command classification from `soul/security.py`.

To avoid excessive snapshots, checkpoint at most once per conversation checkpoint id. If a turn runs
several file writes, all writes after the first share the same pre-change snapshot.

### Restore Semantics

Restore should be all-or-nothing for the MVP.

Before applying restore:

1. Create a pre-restore checkpoint of the current workspace so the restore can be undone later.
2. Show the files that will change when feasible.
3. Ask for confirmation.
4. Restore files from the selected snapshot.
5. Rewind conversation to the selected checkpoint.
6. Append the synthetic continuation note.

If file restore fails, conversation rewind must not happen. This keeps the agent's context aligned
with the actual workspace.

If conversation rewind fails after file restore succeeds, the command must report the mismatch and
point to the pre-restore checkpoint. The implementation should make this path rare by validating the
conversation checkpoint before applying file restore.

### CLI Commands

Add a shell-level command:

```text
/tree
```

Optional non-interactive forms can be added once the core works:

```text
/tree list
/tree rewind <checkpoint-id>
/tree restore <checkpoint-id>
```

For the MVP, interactive `/tree` is enough.

### Data Boundaries

Proposed modules:

- `src/kimi_cli/soul/timeline.py`
  Builds a checkpoint/turn index from `Context.history` plus raw context JSONL metadata.

- `src/kimi_cli/soul/workspace_checkpoint.py`
  Creates, lists, diffs, and restores workspace snapshots.

- `src/kimi_cli/ui/shell/tree.py`
  CLI rendering, selection, confirmation, and command orchestration.

The existing `Context` should get minimal additions only:

- list checkpoint records with enough metadata for UI display;
- expose a user-facing rewind method or keep `revert_to()` and wrap it outside.

### Safety Rules

- Never restore files without explicit confirmation.
- Never modify the user's `.git` directory for checkpoint storage.
- Never delete untracked user files unless the preview shows them and the user confirms.
- Do not run restore while the session is busy.
- Treat restore as a high-risk action under approval semantics if invoked outside the shell UI.

### Testing

Unit tests:

- parse context JSONL into a checkpoint timeline;
- map checkpoints to following user turns;
- reject missing checkpoint ids;
- workspace checkpoint create/list/restore with modified, added, and deleted files;
- restore failure does not rewind conversation;
- conversation-only rewind appends the continuation note.

Shell command tests:

- `/tree` empty session displays a useful message;
- selecting conversation-only rewinds context;
- file restore option is hidden or disabled when no workspace checkpoint exists;
- cancelled restore changes nothing.

Integration tests should use temporary directories and avoid touching real project `.git`.

## Migration Path

Existing sessions continue to work. Old sessions without workspace checkpoint metadata support
conversation-only `/tree` entries. New sessions gradually accumulate checkpoint metadata.

The later append-only tree migration can consume the same checkpoint timeline and workspace
checkpoint records. At that point, conversation-only selection can become true branching instead of
linear rewind.

## Open Follow-Up Work

- Web memory palace view over the same timeline/checkpoint data.
- Append-only conversation tree with active `leaf_id`.
- Bookmarking important nodes as named rooms.
- Distilling selected branches into the wiki/knowledge store.
- Per-file restore from a checkpoint.
- Rich diff preview in shell and web.
