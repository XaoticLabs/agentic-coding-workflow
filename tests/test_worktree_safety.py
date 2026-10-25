"""Exercise cleanup against real Git worktrees, including refusal paths."""

import os
import subprocess
from pathlib import Path

import pytest

from test_ralph_pipeline import git, write_executable

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
    artifact = worktree / ".claude/ralph/run/eval-summary.md"
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
        archive / ".claude/ralph/run/eval-summary.md"
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


def test_hook_does_not_claim_named_but_unowned_review(project: Path) -> None:
    worktree = project / ".claude/worktrees/pr-review-other-session"
    git(project, "worktree", "add", "--detach", str(worktree))

    result = subprocess.run(
        ["bash", str(PLUGIN_ROOT / "hooks/cleanup-review-worktrees.sh")],
        cwd=project,
        input='{"session_id": "different-session"}',
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert worktree.is_dir()


def test_merge_checkout_failure_preserves_target_worktree(
    project: Path, worktree: Path
) -> None:
    result = subprocess.run(
        [
            "bash",
            str(PLUGIN_ROOT / "skills/ralph/scripts/merge-workers.sh"),
            "--target",
            "worker",
            "--branches",
            "main",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert worktree.is_dir()
    assert git(worktree, "branch", "--show-current") == "worker"
