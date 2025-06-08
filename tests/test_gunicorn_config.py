"""Tests for Gunicorn-specific configuration and behavior."""

import subprocess
import time

import pytest


class TestGunicornConfiguration:
    """Test Gunicorn-specific configuration and behavior."""

    def test_gunicorn_workers_configuration(self) -> None:
        """Test that Gunicorn starts with the expected number of workers."""
        # Start container
        run_result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "-p",
                "8082:80",
                "-e",
                "AWS_DEFAULT_REGION=us-east-1",
                "-e",
                "SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
                "-e",
                "TOKEN_SSM_PARAM=/api/token",
                "--name",
                "test-gunicorn-config",
                "checkpoint-api",
            ],
            capture_output=True,
            text=True,
        )

        if run_result.returncode != 0:
            pytest.skip(f"Container start failed: {run_result.stderr}")

        try:
            # Wait for startup
            time.sleep(3)

            # Check logs for worker processes
            logs_result = subprocess.run(
                ["docker", "logs", "test-gunicorn-config"],
                capture_output=True,
                text=True,
            )

            logs = logs_result.stdout + logs_result.stderr

            # Should see exactly 4 worker processes being booted
            worker_lines = [
                line for line in logs.split("\n") if "Booting worker with pid" in line
            ]
            assert len(worker_lines) == 4, (
                f"Expected 4 workers, found {len(worker_lines)}"
            )

            # Should see Gunicorn version and configuration
            assert "Starting gunicorn" in logs
            assert "Listening at: http://0.0.0.0:80" in logs
            assert "Using worker: sync" in logs

        finally:
            # Cleanup
            subprocess.run(
                ["docker", "stop", "test-gunicorn-config"], capture_output=True
            )
            subprocess.run(
                ["docker", "rm", "test-gunicorn-config"], capture_output=True
            )

    def test_application_factory_pattern(self) -> None:
        """Test that the application factory pattern works correctly with Gunicorn."""
        # This test ensures that create_app() can be called multiple times
        # (which Gunicorn workers might do)
        import os
        from unittest.mock import patch

        with (
            patch.dict(
                os.environ,
                {
                    "AWS_DEFAULT_REGION": "us-east-1",
                    "SQS_QUEUE_URL": "https://dummy-url",
                    "TOKEN_SSM_PARAM": "/api/token",
                },
            ),
            patch("boto3.client"),
        ):
            from api.app import create_app

            # Should be able to create multiple app instances
            app1 = create_app()
            app2 = create_app()

            # Apps should be independent instances
            assert app1 is not app2

            # Both should have the same routes
            assert app1.url_map.iter_rules()
            assert len(list(app1.url_map.iter_rules())) == len(
                list(app2.url_map.iter_rules())
            )

    def test_wsgi_application_interface(self) -> None:
        """Test that the app exposes the correct WSGI interface for Gunicorn."""
        import os
        from unittest.mock import patch

        with (
            patch.dict(
                os.environ,
                {
                    "AWS_DEFAULT_REGION": "us-east-1",
                    "SQS_QUEUE_URL": "https://dummy-url",
                    "TOKEN_SSM_PARAM": "/api/token",
                },
            ),
            patch("boto3.client"),
        ):
            from api.app import app

            # Should be callable (WSGI interface)
            assert callable(app)

            # Should have wsgi_app method (Flask's WSGI interface)
            assert hasattr(app, "wsgi_app")
            assert callable(app.wsgi_app)
