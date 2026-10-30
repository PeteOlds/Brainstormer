"""Unit tests for github_tasks.py - GitHub push task for releases."""

from unittest.mock import MagicMock, patch

import pytest


class FakeRelease:
    def __init__(self, release_id, name, instance_id="inst1", status="done"):
        self.id = release_id
        self.name = name
        self.instance_id = instance_id
        self.parent_idea_id = "p1"
        self.status = status
        self.github_sha = None
        self.github_pushed_at = None


class FakeConfig:
    def __init__(self):
        self.pat = "ghp_token"
        self.repo = "owner/repo"
        self.branch = "main"


class FakeBuildTarget:
    def __init__(self):
        self.id = "t1"
        self.instance_id = "inst1"
        self.name = "myrepo"
        self.path = "/tmp/build"


class TestPushReleaseToGithub:
    def test_release_already_pushed_returns_early(self, app):
        """When release already has github_sha, task returns without pushing."""
        from app.tasks.github_tasks import push_release_to_github

        release = FakeRelease("123e4567-e89b-12d3-a456-426614174000", "R1")
        release.github_sha = "abc123def456"

        with app.app_context():
            with patch("app.tasks.github_tasks.db") as mock_db:
                mock_db.session.get.return_value = release

                result = push_release_to_github(str(release.id))

        assert result is None

    def test_release_not_found_returns_early(self, app):
        """When release doesn't exist, task returns without error."""
        from app.tasks.github_tasks import push_release_to_github

        with app.app_context():
            with patch("app.tasks.github_tasks.db") as mock_db:
                mock_db.session.get.return_value = None

                result = push_release_to_github("123e4567-e89b-12d3-a456-426614174000")

        assert result is None

    def test_no_github_config_returns_early(self, app):
        """When instance has no GitHub config, task returns without pushing."""
        from app.tasks.github_tasks import push_release_to_github

        release = FakeRelease("123e4567-e89b-12d3-a456-426614174000", "R1")

        with app.app_context():
            with patch("app.tasks.github_tasks.db") as mock_db:
                mock_db.session.get.return_value = release
                with patch("app.models.InstanceGitHubConfig") as mock_cls:
                    mock_cls.query.filter_by.return_value.first.return_value = None

                    result = push_release_to_github(str(release.id))

        assert result is None

    def test_no_build_target_returns_early(self, app):
        """When no build target exists, task returns without pushing."""
        from app.tasks.github_tasks import push_release_to_github

        release = FakeRelease("123e4567-e89b-12d3-a456-426614174000", "R1")
        config = FakeConfig()

        with app.app_context():
            with patch("app.tasks.github_tasks.db") as mock_db:
                mock_db.session.get.return_value = release
                with patch("app.models.InstanceGitHubConfig") as mock_cls:
                    mock_cls.query.filter_by.return_value.first.return_value = config
                    with patch("app.models.InstanceBuildTarget") as mock_tgt:
                        mock_tgt.query.filter_by.return_value.all.return_value = []

                        result = push_release_to_github(str(release.id))

        assert result is None

    def test_successful_push(self, app):
        """Successful push records SHA and timestamp on release."""
        from app.tasks.github_tasks import push_release_to_github
        from app.models import Idea

        release = FakeRelease("123e4567-e89b-12d3-a456-426614174000", "R1")
        config = FakeConfig()
        target = FakeBuildTarget()

        with app.app_context():
            with patch("app.tasks.github_tasks.db") as mock_db:
                def _get(model, id):
                    if model is Idea:
                        return None
                    return release
                mock_db.session.get.side_effect = _get
                with patch("app.models.InstanceGitHubConfig") as mock_cls:
                    mock_cls.query.filter_by.return_value.first.return_value = config
                    with patch("app.models.InstanceBuildTarget") as mock_tgt:
                        mock_tgt.query.filter_by.return_value.all.return_value = [target]
                        with patch("app.tasks.github_tasks.os.path.isdir", return_value=True):
                            with patch("app.tasks.github_tasks._run_git") as mock_git:
                                mock_git.return_value = "abc123def456"
                                with patch("app.tasks.github_tasks._now") as mock_now:
                                    mock_now.return_value = "2026-10-17T12:00:00Z"

                                    result = push_release_to_github(str(release.id))

        assert result is None
        assert release.github_sha == "abc123def456"
        assert release.github_pushed_at == "2026-10-17T12:00:00Z"
        mock_db.session.commit.assert_called_once()


class TestPatHandling:
    """The GitHub PAT must never reach argv, error text, or .git/config."""

    def test_run_git_keeps_the_pat_out_of_argv(self, app):
        from unittest.mock import MagicMock, patch

        from app.tasks.github_tasks import _run_git

        with app.app_context():
            with patch("app.tasks.github_tasks.subprocess.run") as run:
                run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                _run_git(
                    ["clone", "https://github.com/owner/repo.git", "repo"],
                    cwd="/tmp",
                    pat="ghp_supersecret",
                )

        argv = " ".join(run.call_args[0][0])
        assert "ghp_supersecret" not in argv
        # The credential travels in the environment instead.
        env = run.call_args[1]["env"]
        assert env.get("GIT_CONFIG_KEY_0", "").endswith("extraheader")
        assert "ghp_supersecret" not in env.get("GIT_CONFIG_VALUE_0", "")
        assert env["GIT_CONFIG_VALUE_0"].lower().startswith("authorization: basic ")

    def test_run_git_scrubs_the_pat_from_errors(self, app):
        from unittest.mock import MagicMock, patch

        from app.tasks.github_tasks import _run_git

        with app.app_context():
            with patch("app.tasks.github_tasks.subprocess.run") as run:
                run.return_value = MagicMock(
                    returncode=128,
                    stdout="",
                    stderr=(
                        "fatal: unable to access "
                        "'https://x-access-token:ghp_supersecret@github.com/o/r.git'"
                    ),
                )
                with pytest.raises(RuntimeError) as excinfo:
                    _run_git(["fetch"], cwd="/tmp", pat="ghp_supersecret")

        assert "ghp_supersecret" not in str(excinfo.value)
        assert "***" in str(excinfo.value)

    def test_clone_url_passed_to_git_has_no_credentials(self, app):
        from unittest.mock import MagicMock, patch

        from app.models import Idea
        from app.tasks.github_tasks import push_release_to_github

        release = FakeRelease("123e4567-e89b-12d3-a456-426614174000", "R1")
        config = FakeConfig()
        target = FakeBuildTarget()

        with app.app_context():
            with patch("app.tasks.github_tasks.db") as mock_db:
                mock_db.session.get.side_effect = (
                    lambda model, ident: None if model is Idea else release
                )
                with patch("app.models.InstanceGitHubConfig") as mock_cls:
                    mock_cls.query.filter_by.return_value.first.return_value = config
                    with patch("app.models.InstanceBuildTarget") as mock_tgt:
                        mock_tgt.query.filter_by.return_value.all.return_value = [
                            target
                        ]
                        with patch(
                            "app.tasks.github_tasks.os.path.isdir",
                            return_value=True,
                        ):
                            with patch(
                                "app.tasks.github_tasks._run_git"
                            ) as mock_git:
                                mock_git.return_value = "abc123"
                                push_release_to_github(str(release.id))

        clone_call = mock_git.call_args_list[0]
        argv = " ".join(clone_call[0][0])
        assert "ghp_token" not in argv
        assert clone_call[1].get("pat") == "ghp_token"
