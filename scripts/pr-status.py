#!/usr/bin/env python3
"""Read CI and review feedback for one exact GitHub PR revision using gh."""

import argparse
import json
import re
import subprocess
import sys
from urllib.parse import urlsplit


class StatusError(Exception):
    pass


def gh_json(arguments):
    try:
        result = subprocess.run(
            ["gh", *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise StatusError("GitHub CLI is unavailable or timed out") from error
    if result.returncode:
        raise StatusError(
            f"GitHub CLI failed (exit {result.returncode}); check authentication and repository access"
        )
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise StatusError("GitHub CLI did not return valid JSON") from error


def classify_check(check):
    if "conclusion" in check:
        state = (
            check.get("conclusion") if check.get("status") == "COMPLETED" else "PENDING"
        )
    else:
        state = check.get("state")
    if state in ("SUCCESS", "NEUTRAL", "SKIPPED"):
        bucket = "pass"
    elif state in (
        "FAILURE",
        "ERROR",
        "CANCELLED",
        "TIMED_OUT",
        "ACTION_REQUIRED",
        "STARTUP_FAILURE",
        "STALE",
    ):
        bucket = "fail"
    else:
        bucket = "pending"
    return {
        "name": check.get("name") or check.get("context"),
        "state": state,
        "bucket": bucket,
        "url": check.get("detailsUrl") or check.get("targetUrl"),
    }


def inspect_pr(url, expected_head=None):
    parsed = urlsplit(url)
    match = re.fullmatch(
        r"/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)/?", parsed.path
    )
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not match
    ):
        raise StatusError(
            "Provide an HTTPS GitHub pull request URL without credentials or query parameters"
        )
    owner, repo, number = match.groups()
    snapshot = gh_json(
        [
            "pr",
            "view",
            url,
            "--json",
            "url,headRefOid,isDraft,state,reviewDecision,statusCheckRollup,reviews,comments",
        ]
    )
    head = snapshot.get("headRefOid")
    if not head or snapshot.get("url", "").rstrip("/") != url.rstrip("/"):
        raise StatusError("GitHub returned a different PR or no HEAD revision")
    if snapshot.get("state") not in ("OPEN", "MERGED", "CLOSED"):
        raise StatusError("GitHub did not return a known PR state")
    if expected_head and head != expected_head:
        raise StatusError(
            "PR HEAD changed; refresh the diff and verification evidence before continuing"
        )
    threads = []
    limitations = []
    cursor = None
    seen_cursors = set()
    for _ in range(20):
        query = """query WorkflowReview($owner: String!, $repo: String!, $number: Int!, $after: String) {
          repository(owner: $owner, name: $repo) { pullRequest(number: $number) {
            headRefOid
            reviewThreads(first: 100, after: $after) {
              nodes { id isResolved isOutdated path line
                comments(first: 20) { nodes { author { login } body url } pageInfo { hasNextPage } }
              }
              pageInfo { hasNextPage endCursor }
            }
          } }
        }"""
        arguments = [
            "api",
            "graphql",
            "--hostname",
            parsed.hostname,
            "-f",
            "query=" + query,
            "-f",
            "owner=" + owner,
            "-f",
            "repo=" + repo,
            "-F",
            "number=" + number,
        ]
        if cursor:
            arguments.extend(["-f", "after=" + cursor])
        response = gh_json(arguments)
        if response.get("errors"):
            raise StatusError(
                "GitHub review-thread query returned errors; feedback is incomplete"
            )
        pr = ((response.get("data") or {}).get("repository") or {}).get("pullRequest")
        if not isinstance(pr, dict) or pr.get("headRefOid") != head:
            raise StatusError(
                "PR HEAD changed while fetching feedback; take a fresh snapshot"
            )
        connection = pr.get("reviewThreads")
        if not isinstance(connection, dict) or not isinstance(
            connection.get("nodes"), list
        ):
            raise StatusError("GitHub returned incomplete review-thread data")
        for thread in connection["nodes"]:
            if thread.get("isResolved") is not True:
                comments = thread.get("comments") or {}
                if comments.get("pageInfo", {}).get("hasNextPage"):
                    limitations.append("thread_comments_truncated:" + thread["id"])
                threads.append({**thread, "comments": comments.get("nodes", [])})
        page = connection.get("pageInfo")
        if not isinstance(page, dict) or "hasNextPage" not in page:
            raise StatusError("GitHub review-thread pagination data is missing")
        if not page["hasNextPage"]:
            break
        cursor = page.get("endCursor")
        if not cursor or cursor in seen_cursors:
            raise StatusError("GitHub review-thread pagination did not advance")
        seen_cursors.add(cursor)
    else:
        raise StatusError("Review-thread page budget reached; feedback is incomplete")
    checks = [
        classify_check(check) for check in snapshot.get("statusCheckRollup") or []
    ]
    feedback = {}
    for name in ("reviews", "comments"):
        items = snapshot.get(name) or []
        feedback[name] = items[-50:]
        if len(items) > 50:
            limitations.append(name + "_truncated")
    if snapshot.get("state") != "OPEN":
        status = "closed"
    elif (
        threads
        or snapshot.get("reviewDecision") == "CHANGES_REQUESTED"
        or any(c["bucket"] == "fail" for c in checks)
    ):
        status = "needs_attention"
    elif not checks or any(c["bucket"] == "pending" for c in checks):
        status = "pending_checks"
    else:
        status = "ready_for_human_review"
    return {
        "status": status,
        "url": snapshot["url"],
        "head_sha": head,
        "draft": snapshot.get("isDraft"),
        "review_decision": snapshot.get("reviewDecision"),
        "checks": checks,
        "unresolved_threads": threads,
        "feedback": feedback,
        "limitations": limitations,
        "merge_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--head", help="Require this exact PR HEAD SHA")
    args = parser.parse_args(argv)
    try:
        report = inspect_pr(args.url, args.head)
    except (StatusError, ValueError, TypeError, KeyError, AttributeError) as error:
        message = (
            str(error)
            if isinstance(error, StatusError)
            else "GitHub returned malformed PR data"
        )
        print(json.dumps({"status": "error", "error": message}))
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
