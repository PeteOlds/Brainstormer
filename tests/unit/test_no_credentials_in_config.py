"""Tests for the git-config credential guardrail.

Pure functions only: no real git config is read or mutated.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import check_no_credentials_in_config as guard  # noqa: E402


def test_clean_https_url_is_allowed():
    assert not guard.url_has_credentials("https://github.com/PeteOlds/Brainstormer.git")


def test_token_in_https_url_is_flagged():
    assert guard.url_has_credentials("https://ghp_example@github.com/owner/repo.git")


def test_ssh_user_is_not_a_secret():
    assert not guard.url_has_credentials("git@github.com:owner/repo.git")


def test_clean_config_has_no_findings():
    config = (
        "file:.git/config\tremote.origin.url=https://github.com/owner/repo.git\n"
        "file:/home/pete/.gitconfig\t"
        "credential.https://github.com.helper=!/usr/bin/gh auth git-credential\n"
    )
    assert guard.offending_entries(config) == []


def test_token_in_remote_url_is_flagged_without_leaking_value():
    config = (
        "file:.git/config\t"
        "remote.origin.url=https://ghp_supersecret@github.com/owner/repo.git\n"
    )
    problems = guard.offending_entries(config)
    assert problems == [("file:.git/config", "remote.origin.url")]
    assert "supersecret" not in repr(problems)


def test_token_prefix_anywhere_in_config_is_flagged():
    config = "file:/home/pete/.gitconfig\talias.release=github_pat_example\n"
    assert guard.offending_entries(config) == [
        ("file:/home/pete/.gitconfig", "alias.release")
    ]
