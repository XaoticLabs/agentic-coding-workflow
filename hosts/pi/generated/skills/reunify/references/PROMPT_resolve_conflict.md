# Reunify Merge Conflict Resolution

You are resolving merge conflicts that arose while reunifying parallel worktree branches back onto a feature branch.

## Context

Multiple workers implemented different parts of a feature in separate branches. File-affinity assignment minimized conflicts, but shared files (configs, route registrations, type exports, index files, test setup) may have been touched by multiple workers. These conflicts are almost always **additive** -- both sides added something, and the correct resolution is to keep both additions.

## Step 1: Identify Conflicts

```bash
git diff --name-only --diff-filter=U
```

## Step 2: Resolve Each File

For each conflicted file:

1. Read the file and find all `<<<<<<<`, `=======`, `>>>>>>>` markers
2. Understand what each side added -- these are typically independent additions
3. Resolve by **combining both sides** -- keep all additions from both workers
4. If the changes genuinely conflict (two implementations of the same thing), prefer the version that is more complete and has better test coverage
5. Remove all conflict markers
6. Ensure imports, type definitions, and module references are consistent after combining

## Step 3: Verify

After resolving all conflicts:

1. Run the project's test suite
2. Run the project's linter/formatter
3. If either fails, fix the issues -- the failure is likely from the combination, not from either side individually

## Step 4: Commit

```bash
git add -A
git commit -m "fix: resolve merge conflicts from reunifying parallel branches"
```

## Rules

- **No questions.** Resolve autonomously.
- **Keep both sides.** The default resolution is additive.
- **Test after resolving.** Never commit without passing tests.
- **Exit when done.** Commit and exit.
