"""Verify CI/review handoffs stay bound to the published PR revision."""

import importlib.util

import pytest

from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "workflow_pr_status", Path(__file__).resolve().parents[1] / "scripts/pr-status.py"
)
status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(status)
URL = "https://github.com/acme/repo/pull/17"
HEAD = "a" * 40


def snapshot(**changes):
    return {
        "url": URL,
        "headRefOid": HEAD,
        "isDraft": True,
        "state": "OPEN",
        "statusCheckRollup": [
            {"name": "tests", "status": "COMPLETED", "conclusion": "SUCCESS"}
        ],
        **changes,
    }


def review_page(nodes=None, head=HEAD, next_page=False, cursor=None):
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": head,
                    "reviewThreads": {
                        "nodes": nodes or [],
                        "pageInfo": {"hasNextPage": next_page, "endCursor": cursor},
                    },
                }
            }
        }
    }


def serve(monkeypatch, *responses):
    calls = []
    sequence = iter(responses)

    def gh(arguments):
        calls.append(arguments)
        return next(sequence)

    monkeypatch.setattr(status, "gh_json", gh)
    return calls


def test_passing_checks_produce_a_review_handoff_not_merge_authorization(monkeypatch):
    serve(monkeypatch, snapshot(), review_page())
    report = status.inspect_pr(URL, HEAD)
    assert report["status"] == "ready_for_human_review"
    assert report["draft"] is True
    assert report["merge_authorized"] is False
    assert report["head_sha"] == HEAD


@pytest.mark.parametrize(
    "checks",
    [
        None,
        [],
        [{"context": "CI", "state": "PENDING"}],
        [{"name": "CI", "status": "IN_PROGRESS", "conclusion": None}],
    ],
)
def test_missing_or_running_checks_never_produce_a_ready_handoff(monkeypatch, checks):
    serve(monkeypatch, snapshot(statusCheckRollup=checks), review_page())
    assert status.inspect_pr(URL)["status"] == "pending_checks"


def test_neutral_bugbot_check_does_not_hide_unresolved_findings(monkeypatch):
    serve(
        monkeypatch,
        snapshot(
            statusCheckRollup=[
                {"name": "Bugbot", "status": "COMPLETED", "conclusion": "NEUTRAL"}
            ]
        ),
        review_page(
            [
                {
                    "id": "thread-1",
                    "isResolved": False,
                    "isOutdated": True,
                    "path": "handler.go",
                    "line": 18,
                    "comments": {
                        "nodes": [
                            {
                                "body": "Cancellation does not propagate",
                                "url": URL + "#discussion1",
                            }
                        ],
                        "pageInfo": {"hasNextPage": False},
                    },
                }
            ]
        ),
    )
    report = status.inspect_pr(URL)
    assert report["status"] == "needs_attention"
    assert report["unresolved_threads"][0]["isOutdated"] is True


def test_review_threads_paginate_and_preserve_only_unresolved_feedback(monkeypatch):
    calls = serve(
        monkeypatch,
        snapshot(),
        review_page(
            [{"id": "resolved", "isResolved": True}], next_page=True, cursor="page-2"
        ),
        review_page(
            [
                {
                    "id": "open",
                    "isResolved": False,
                    "comments": {"nodes": [], "pageInfo": {"hasNextPage": True}},
                }
            ]
        ),
    )
    report = status.inspect_pr(URL)
    assert [thread["id"] for thread in report["unresolved_threads"]] == ["open"]
    assert "after=page-2" in calls[2]
    assert report["limitations"] == ["thread_comments_truncated:open"]


def test_stale_published_head_stops_before_review_or_repairs(monkeypatch):
    calls = serve(monkeypatch, snapshot(headRefOid="b" * 40))
    with pytest.raises(status.StatusError, match="HEAD changed"):
        status.inspect_pr(URL, HEAD)
    assert len(calls) == 1


def test_head_changes_during_feedback_fetch_invalidate_the_snapshot(monkeypatch):
    serve(monkeypatch, snapshot(), review_page(head="b" * 40))
    with pytest.raises(status.StatusError, match="HEAD changed"):
        status.inspect_pr(URL)


@pytest.mark.parametrize(
    "response",
    [
        {"errors": [{"message": "failure"}]},
        {"data": {"repository": None}},
        {
            "data": {
                "repository": {
                    "pullRequest": {"headRefOid": HEAD, "reviewThreads": {"nodes": []}}
                }
            }
        },
    ],
)
def test_incomplete_feedback_cannot_be_treated_as_a_clean_review(monkeypatch, response):
    serve(monkeypatch, snapshot(), response)
    with pytest.raises(status.StatusError):
        status.inspect_pr(URL)


def test_repeated_pagination_cursor_stops_instead_of_looping(monkeypatch):
    serve(
        monkeypatch,
        snapshot(),
        review_page(next_page=True, cursor="same"),
        review_page(next_page=True, cursor="same"),
    )
    with pytest.raises(status.StatusError, match="did not advance"):
        status.inspect_pr(URL)


def test_failed_checks_and_requested_changes_are_attention_items(monkeypatch):
    serve(monkeypatch, snapshot(reviewDecision="CHANGES_REQUESTED"), review_page())
    assert status.inspect_pr(URL)["status"] == "needs_attention"
    serve(
        monkeypatch,
        snapshot(statusCheckRollup=[{"context": "CI", "state": "FAILURE"}]),
        review_page(),
    )
    assert status.inspect_pr(URL)["status"] == "needs_attention"


def test_closed_pr_does_not_trigger_followup_work(monkeypatch):
    serve(monkeypatch, snapshot(state="MERGED"), review_page())
    assert status.inspect_pr(URL)["status"] == "closed"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/acme/repo/pull/17",
        "https://token@github.com/acme/repo/pull/17",
        "https://github.com/acme/repo/issues/17",
        URL + "?token=secret",
    ],
)
def test_invalid_urls_fail_before_invoking_gh(monkeypatch, url):
    calls = serve(monkeypatch)
    with pytest.raises(status.StatusError):
        status.inspect_pr(url)
    assert not calls
