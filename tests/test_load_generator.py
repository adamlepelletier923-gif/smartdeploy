from scripts.load_generator import LoadResult, percentile


def test_load_result_error_rate():
    result = LoadResult(
        total_requests=10,
        successful_requests=8,
        failed_requests=2,
        p95_latency_ms=120,
    )

    assert result.error_rate == 0.2


def test_percentile_handles_empty_values():
    assert percentile([], 95) == 0.0


def test_percentile_returns_ordered_percentile():
    assert percentile([100, 20, 50, 80, 10], 95) == 100
