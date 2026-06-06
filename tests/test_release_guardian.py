from scripts.release_guardian import MetricSample, build_report


def test_build_report_contains_verdict_and_samples():
    report = build_report(
        samples=[
            MetricSample(
                collected_at="2026-06-06 12:00:00",
                error_rate=0.12,
                p95_latency_ms=850,
                degraded=True,
            )
        ],
        verdict="rollback",
        reason="release exceeded thresholds for consecutive samples",
        error_rate_threshold=0.05,
        p95_latency_threshold_ms=500,
    )

    assert "Verdict: `rollback`" in report
    assert "12.00%" in report
    assert "850ms" in report
    assert "degraded" in report
