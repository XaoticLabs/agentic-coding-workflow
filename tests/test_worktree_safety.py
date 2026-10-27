"""Exercise cleanup against real Git worktrees, including refusal paths."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from workflow_test_support import git, write_executable

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PRIMITIVES = PLUGIN_ROOT / "scripts/lib/parallel-primitives.sh"


def shell(
    project: Path, script: str, *arguments: str, owner: str = "test-owner"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            'set -euo pipefail\nsource "$1"\n' + script,
            "test",
            str(PRIMITIVES),
            str(project),
            *arguments,
        ],
        cwd=project,
        env={**os.environ, "WORKTREE_OWNER_TOKEN": owner},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project with spaces"
    root.mkdir()
    git(root, "init", "--quiet", "--initial-branch=main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    (root / ".gitignore").write_text(".claude/\n")
    git(root, "add", ".gitignore")
    git(root, "commit", "--quiet", "-m", "Initial")
    return root


@pytest.fixture
def worktree(project: Path) -> Path:
    path = project / ".claude/worktrees/worker"
    result = shell(
        project,
        'create_worker_worktree "$2" "$3" worker "" "" "" main',
        str(path),
    )
    assert result.returncode == 0, result.stderr
    return path


def metadata(worktree: Path) -> Path:
    return Path(git(worktree, "rev-parse", "--absolute-git-dir")) / "agentic-worktree"


@pytest.mark.parametrize(
    "condition",
    ["unowned", "active", "dirty", "untracked", "unmerged", "locked", "branch_changed"],
)
def test_cleanup_preserves_unsafe_worktrees(
    project: Path, worktree: Path, condition: str
) -> None:
    if condition == "active":
        (metadata(worktree) / "active-pid").write_text(str(os.getpid()))
    elif condition == "dirty":
        (worktree / ".gitignore").write_text("modified\n")
    elif condition == "untracked":
        (worktree / "unfinished.txt").write_text("unfinished work")
    elif condition == "unmerged":
        (worktree / "new.txt").write_text("unique work")
        git(worktree, "add", "new.txt")
        git(worktree, "commit", "--quiet", "-m", "Unmerged")
    elif condition == "locked":
        git(project, "worktree", "lock", str(worktree))
    elif condition == "branch_changed":
        git(worktree, "checkout", "--quiet", "-b", "other")

    head = git(worktree, "rev-parse", "HEAD")
    result = shell(
        project,
        'cleanup_worker_worktree "$2" "$3" worker "" main',
        str(worktree),
        owner="other-owner" if condition == "unowned" else "test-owner",
    )

    assert result.returncode != 0
    assert worktree.is_dir()
    assert git(worktree, "rev-parse", "HEAD") == head
    assert git(project, "rev-parse", "worker")


def test_successful_cleanup_archives_ignored_workflow_artifacts(
    project: Path, worktree: Path
) -> None:
    artifact = worktree / ".claude/relay/run/eval-summary.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("Review this result")
    archive = project / ".claude/saved worker"

    result = shell(
        project,
        'cleanup_worker_worktree "$2" "$3" worker "" main "$4"',
        str(worktree),
        str(archive),
    )

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    assert (
        archive / ".claude/relay/run/eval-summary.md"
    ).read_text() == "Review this result"
    assert "worker" not in git(project, "branch", "--list", "worker")


@pytest.mark.parametrize(
    "change", ["missing_archive", "archive_failure", "artifact_changed"]
)
def test_cleanup_requires_current_saved_artifacts(
    project: Path, worktree: Path, change: str
) -> None:
    archive = project / ".claude/archive"
    if change == "archive_failure":
        archive.write_text("not a directory")
        script = 'cleanup_worker_worktree "$2" "$3" worker "" main "$4"'
    elif change == "artifact_changed":
        script = (
            'preserve_worktree_artifacts "$2" "$3" "$4"\n'
            'echo new > "$3/.claude/new-artifact"\n'
            'remove_owned_worktree "$2" "$3" main'
        )
    else:
        script = 'remove_owned_worktree "$2" "$3" main'

    result = shell(project, script, str(worktree), str(archive))

    assert result.returncode != 0
    assert worktree.is_dir()
    assert git(project, "rev-parse", "worker")


def test_creation_preserves_existing_path_and_branch(
    project: Path, worktree: Path
) -> None:
    (worktree / "unfinished.txt").write_text("keep me")
    head = git(worktree, "rev-parse", "HEAD")

    result = shell(project, 'create_worker_worktree "$2" "$3" worker', str(worktree))

    assert result.returncode != 0
    assert (worktree / "unfinished.txt").read_text() == "keep me"
    assert git(worktree, "rev-parse", "HEAD") == head


def test_live_tmux_pane_prevents_cleanup(
    project: Path, worktree: Path, tmp_path: Path
) -> None:
    write_executable(tmp_path / "bin/tmux", f"printf '%s\\n' '{worktree}'\n")
    result = shell(
        project,
        'PATH="$4:$PATH"\ncleanup_worker_worktree "$2" "$3" worker "" main',
        str(worktree),
        str(tmp_path / "bin"),
    )
    assert result.returncode != 0
    assert worktree.is_dir()


@pytest.mark.skipif(not Path("/proc/self").exists(), reason="Linux process inspection")
def test_live_child_prevents_cleanup_after_launcher_exits(
    project: Path, worktree: Path
) -> None:
    process = subprocess.Popen(["sleep", "30"], cwd=worktree)
    try:
        result = shell(
            project, 'cleanup_worker_worktree "$2" "$3" worker "" main', str(worktree)
        )
        assert result.returncode != 0
        assert worktree.is_dir()
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_global_hooks_do_not_route_permissions_or_sweep_review_worktrees() -> None:
    hooks = json.loads((PLUGIN_ROOT / "hooks/hooks.json").read_text())["hooks"]
    assert not hooks.get("PermissionRequest")
    assert not hooks.get("SessionEnd")


@pytest.fixture
def review_environment(project: Path, tmp_path: Path) -> dict[str, str]:
    # Fetch real refs locally; these lifecycle tests do not use a network or model.
    git(project, "remote", "add", "origin", str(project))
    for branch in ("review-one", "review-two"):
        git(project, "branch", branch)
    tools = tmp_path / "bin"
    write_executable(tools / "gh", "exit 0\n")
    write_executable(tools / "tmux", "exit 0\n")
    write_executable(
        tools / "claude",
        "mkdir -p .claude/review\n"
        'echo "Review evidence" > .claude/review/report.md\n'
        'if [ -n "${TEST_REVIEW_SIGNAL:-}" ]; then\n'
        '  kill -s "$TEST_REVIEW_SIGNAL" "$PPID"\n'
        "fi\n"
        'exit "${TEST_REVIEW_EXIT:-0}"\n',
    )
    return {
        **os.environ,
        "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
        "WORKTREE_OWNER_TOKEN": "test-owner",
        "TMUX": "",
    }


def launch_reviews(
    project: Path, environment: dict[str, str], *branches: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(PLUGIN_ROOT / "scripts/launch-reviews.sh"), "python", *branches],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


@pytest.mark.parametrize("review_mode", ["defects", "suggestions"])
def test_review_launch_preserves_mode_and_does_not_install_dependencies(
    project: Path, review_environment: dict[str, str], tmp_path: Path, review_mode: str
) -> None:
    # Node setup must not select npm or fall back to a lockfile-changing install.
    (project / "package.json").write_text('{"packageManager": "pnpm@10.0.0"}')
    git(project, "add", "package.json")
    git(project, "commit", "--quiet", "-m", "Node project")
    git(project, "branch", "-f", "review-one")
    write_executable(tmp_path / "bin/npm", 'touch "$TEST_INSTALL_ATTEMPT"\n')
    write_executable(
        tmp_path / "bin/claude",
        'python3 -c \'import json, os, sys; from pathlib import Path; Path(os.environ["TEST_REVIEW_ARGS"]).write_text(json.dumps(sys.argv[1:]))\' "$@"\n',
    )
    arguments = tmp_path / "review-args.json"
    installation = tmp_path / "install-attempt"
    result = launch_reviews(
        project,
        {
            **review_environment,
            "REVIEW_MODE": review_mode,
            "TEST_REVIEW_ARGS": str(arguments),
            "TEST_INSTALL_ATTEMPT": str(installation),
        },
        "review-one",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    args = json.loads(arguments.read_text())
    context = args[args.index("--append-system-prompt") + 1]
    assert f"Review mode: {review_mode}" in context
    assert f"{PLUGIN_ROOT}/skills/pr-reviewer" in context
    assert not installation.exists()


@pytest.mark.parametrize(
    "exit_code, signal", [(0, ""), (7, ""), (143, "TERM"), (129, "HUP")]
)
def test_review_exit_cleans_only_its_owned_worktree_and_archives_evidence(
    project: Path, review_environment: dict[str, str], exit_code: int, signal: str
) -> None:
    unrelated = project / ".claude/worktrees/pr-review-unrelated"
    result = shell(
        project,
        'create_worker_worktree "$2" "$3" unrelated "" "" "" main',
        str(unrelated),
    )
    assert result.returncode == 0, result.stderr
    review_environment.update(
        TEST_REVIEW_EXIT=str(exit_code), TEST_REVIEW_SIGNAL=signal
    )

    result = launch_reviews(project, review_environment, "review-one")

    assert result.returncode == exit_code, result.stdout + result.stderr
    assert not (project / ".claude/worktrees/pr-review-review-one").exists()
    assert unrelated.is_dir()  # Even a clean, inactive checkout with the same owner.
    report = next(
        (project / ".claude/worktree-archives").glob("*/.claude/review/report.md")
    )
    assert report.read_text() == "Review evidence\n"


@pytest.mark.parametrize("change", ["dirty", "unmerged"])
def test_review_exit_preserves_changes(
    project: Path, review_environment: dict[str, str], tmp_path: Path, change: str
) -> None:
    code = 'echo "Unfinished review work" > .gitignore\n'
    if change == "unmerged":
        code += "git add .gitignore\ngit commit --quiet -m 'Review change'\n"
    write_executable(tmp_path / "bin/claude", code)

    result = launch_reviews(project, review_environment, "review-one")

    assert result.returncode == 0, result.stdout + result.stderr
    worktree = project / ".claude/worktrees/pr-review-review-one"
    assert (worktree / ".gitignore").read_text() == "Unfinished review work\n"
    assert f"Worktree preserved: {worktree}" in result.stdout + result.stderr


def test_partial_review_setup_cleans_created_checkout_and_preserves_existing_path(
    project: Path, review_environment: dict[str, str]
) -> None:
    existing = project / ".claude/worktrees/pr-review-review-two"
    git(project, "worktree", "add", "--detach", str(existing))
    (existing / "unfinished.txt").write_text("Existing work")

    result = launch_reviews(project, review_environment, "review-one", "review-two")

    assert result.returncode != 0
    assert not (project / ".claude/worktrees/pr-review-review-one").exists()
    assert (existing / "unfinished.txt").read_text() == "Existing work"


@pytest.mark.parametrize("failure", ["new-session", "split-window"])
def test_failed_tmux_launch_cleans_only_pending_reviews(
    project: Path, review_environment: dict[str, str], tmp_path: Path, failure: str
) -> None:
    write_executable(
        tmp_path / "bin/tmux",
        f'if [ "$1" = "{failure}" ]; then exit 5; fi\n',
    )

    result = launch_reviews(project, review_environment, "review-one", "review-two")

    assert result.returncode == 5, result.stdout + result.stderr
    first = project / ".claude/worktrees/pr-review-review-one"
    # A successful tmux handoff belongs to its review process, even before it starts.
    assert first.exists() == (failure == "split-window")
    assert not (project / ".claude/worktrees/pr-review-review-two").exists()


def test_review_process_refuses_another_owners_worktree(
    project: Path, worktree: Path, review_environment: dict[str, str]
) -> None:
    result = subprocess.run(
        [
            "bash",
            str(PLUGIN_ROOT / "scripts/review-in-worktree.sh"),
            str(project),
            str(worktree),
            "worker",
            "python",
        ],
        cwd=project,
        env={**review_environment, "WORKTREE_OWNER_TOKEN": "different-owner"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert worktree.is_dir()
    assert not (worktree / ".claude/review/report.md").exists()
