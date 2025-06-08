"""Container integration tests for Gunicorn deployment."""

import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import requests


class TestContainerIntegration:
    """Test the containerized application with Gunicorn."""

    @pytest.fixture(scope="class")
    def container_url(self) -> Generator[str, None, None]:
        """Start container and return URL."""
        # Get project root directory dynamically
        project_root = Path(__file__).parent.parent

        # Build the container
        build_result = subprocess.run(
            ["docker", "build", "-t", "checkpoint-api-test", "."],
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
        assert build_result.returncode == 0, f"Build failed: {build_result.stderr}"

        # Start the container
        run_result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "-p",
                "8081:80",
                "-e",
                "AWS_DEFAULT_REGION=us-east-1",
                "-e",
                "SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
                "-e",
                "TOKEN_SSM_PARAM=/api/token",
                "--name",
                "test-container",
                "checkpoint-api-test",
            ],
            capture_output=True,
            text=True,
        )
        assert run_result.returncode == 0, (
            f"Container start failed: {run_result.stderr}"
        )

        # Wait for container to be ready
        time.sleep(3)

        yield "http://localhost:8081"

        # Cleanup
        subprocess.run(["docker", "stop", "test-container"], capture_output=True)
        subprocess.run(["docker", "rm", "test-container"], capture_output=True)

    def test_health_check_in_container(self, container_url: str) -> None:
        """Test health check endpoint in containerized environment."""
        response = requests.get(f"{container_url}/", timeout=10)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "checkpoint-home-assignment-api-ms"

    def test_gunicorn_workers_handling_concurrent_requests(
        self, container_url: str
    ) -> None:
        """Test that multiple requests can be handled concurrently."""
        import concurrent.futures
        import threading

        results = []

        def make_request() -> dict[str, Any]:
            response = requests.get(f"{container_url}/", timeout=10)
            return {
                "status_code": response.status_code,
                "thread_id": threading.current_thread().ident,
                "response_time": response.elapsed.total_seconds(),
            }

        # Make 8 concurrent requests (more than 4 workers)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(make_request) for _ in range(8)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # All requests should succeed
        assert len(results) == 8
        assert all(result["status_code"] == 200 for result in results)

        # Should complete in reasonable time (less than 5 seconds total)
        max_response_time = max(result["response_time"] for result in results)
        assert max_response_time < 5.0

    def test_container_logs_show_gunicorn(self, container_url: str) -> None:
        """Verify that Gunicorn is actually running, not Flask dev server."""
        logs_result = subprocess.run(
            ["docker", "logs", "test-container"],
            capture_output=True,
            text=True,
        )

        logs = logs_result.stdout + logs_result.stderr

        # Should see Gunicorn startup messages
        assert "Starting gunicorn" in logs
        assert "Booting worker with pid" in logs

        # Should NOT see Flask development server warnings
        assert "WARNING: This is a development server" not in logs
        assert "Do not use it in a production deployment" not in logs
