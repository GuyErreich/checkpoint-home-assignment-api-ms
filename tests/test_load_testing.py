"""Load testing using pytest for CI/CD integration."""

import concurrent.futures
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import requests


@pytest.fixture(scope="module")
def container_url() -> Generator[str, None, None]:
    """Start a test container for load testing."""
    # Check if container is already running
    check_result = subprocess.run(
        ["docker", "ps", "--filter", "name=pytest-load-test", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )

    if "pytest-load-test" in check_result.stdout:
        yield "http://localhost:8083"
        return

    # Get project root directory dynamically
    project_root = Path(__file__).parent.parent

    # Build the image if needed
    build_result = subprocess.run(
        ["docker", "build", "-t", "checkpoint-api-test", "."],
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    if build_result.returncode != 0:
        pytest.skip(f"Failed to build image: {build_result.stderr}")

    # Start container
    run_result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-p",
            "8083:80",
            "-e",
            "AWS_DEFAULT_REGION=us-east-1",
            "-e",
            "SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
            "-e",
            "TOKEN_SSM_PARAM=/api/token",
            "--name",
            "pytest-load-test",
            "checkpoint-api-test",
        ],
        capture_output=True,
        text=True,
    )

    if run_result.returncode != 0:
        pytest.skip(f"Failed to start container: {run_result.stderr}")

    # Wait for container to be ready
    for _ in range(10):  # 10 second timeout
        try:
            response = requests.get("http://localhost:8083/", timeout=1)
            if response.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    else:
        subprocess.run(["docker", "stop", "pytest-load-test"], capture_output=True)
        subprocess.run(["docker", "rm", "pytest-load-test"], capture_output=True)
        pytest.skip("Container failed to become ready")

    yield "http://localhost:8083"

    # Cleanup
    subprocess.run(["docker", "stop", "pytest-load-test"], capture_output=True)
    subprocess.run(["docker", "rm", "pytest-load-test"], capture_output=True)


class TestLoadTesting:
    """Load testing that can be run in CI/CD pipelines."""

    def test_concurrent_health_checks_light_load(self, container_url: str) -> None:
        """Test handling of multiple concurrent health check requests (light load for CI)."""
        num_requests = 10
        concurrency = 4

        def make_request() -> dict[str, Any]:
            start_time = time.time()
            try:
                response = requests.get(f"{container_url}/", timeout=5)
                end_time = time.time()
                return {
                    "success": response.status_code == 200,
                    "response_time": end_time - start_time,
                    "status_code": response.status_code,
                }
            except Exception as e:
                end_time = time.time()
                return {
                    "success": False,
                    "response_time": end_time - start_time,
                    "error": str(e),
                }

        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(make_request) for _ in range(num_requests)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        end_time = time.time()
        total_time = end_time - start_time

        # Analyze results
        successful_requests = [r for r in results if r["success"]]
        response_times = [r["response_time"] for r in successful_requests]

        # Assertions for CI
        success_rate = len(successful_requests) / num_requests
        avg_response_time = (
            sum(response_times) / len(response_times)
            if response_times
            else float("inf")
        )
        requests_per_second = num_requests / total_time

        assert success_rate >= 0.9, f"Success rate {success_rate:.1%} is below 90%"
        assert avg_response_time < 1.0, (
            f"Average response time {avg_response_time:.3f}s is too slow"
        )
        assert requests_per_second > 5, (
            f"Throughput {requests_per_second:.1f} req/s is too low"
        )

        print("\n✅ Load test passed:")
        print(f"   Success rate: {success_rate:.1%}")
        print(f"   Avg response time: {avg_response_time:.3f}s")
        print(f"   Requests/sec: {requests_per_second:.1f}")

    def test_concurrent_requests_exceed_workers(self, container_url: str) -> None:
        """Test that requests exceeding worker count are handled properly."""
        # Use 8 concurrent requests (more than 4 Gunicorn workers)
        num_requests = 8
        concurrency = 8

        def make_request() -> bool:
            try:
                response = requests.get(f"{container_url}/", timeout=10)
                return bool(response.status_code == 200)
            except Exception:
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(make_request) for _ in range(num_requests)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        successful_requests = sum(results)
        success_rate = successful_requests / num_requests

        # Should handle all requests successfully even with more requests than workers
        assert success_rate >= 0.9, (
            f"Success rate {success_rate:.1%} with {num_requests} concurrent requests"
        )

        print(
            f"\n✅ Concurrent test passed: {successful_requests}/{num_requests} requests successful"
        )

    def test_sustained_load_performance(self, container_url: str) -> None:
        """Test performance under sustained load for CI validation."""
        num_requests = 20
        concurrency = 6

        def make_request() -> dict[str, Any]:
            start_time = time.time()
            try:
                response = requests.get(f"{container_url}/", timeout=5)
                end_time = time.time()
                return {
                    "success": response.status_code == 200,
                    "response_time": end_time - start_time,
                }
            except Exception:
                end_time = time.time()
                return {
                    "success": False,
                    "response_time": end_time - start_time,
                }

        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(make_request) for _ in range(num_requests)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        end_time = time.time()
        total_time = end_time - start_time

        # Performance metrics
        successful_requests = [r for r in results if r["success"]]
        success_rate = len(successful_requests) / num_requests
        response_times = [r["response_time"] for r in successful_requests]
        avg_response_time = (
            sum(response_times) / len(response_times)
            if response_times
            else float("inf")
        )
        requests_per_second = num_requests / total_time

        # CI-friendly assertions
        assert success_rate >= 0.95, (
            f"Success rate {success_rate:.1%} below 95% under sustained load"
        )
        assert avg_response_time < 2.0, (
            f"Average response time {avg_response_time:.3f}s too slow under load"
        )
        assert requests_per_second > 8, (
            f"Throughput {requests_per_second:.1f} req/s too low under sustained load"
        )

        print("\n✅ Sustained load test passed:")
        print(f"   {num_requests} requests with {concurrency} concurrency")
        print(f"   Success rate: {success_rate:.1%}")
        print(f"   Avg response time: {avg_response_time:.3f}s")
        print(f"   Requests/sec: {requests_per_second:.1f}")
