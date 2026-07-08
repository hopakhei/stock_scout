"""M0 acceptance test: the full pipeline runs end-to-end on fixture data."""

from pathlib import Path

from stock_scout.config import Settings
from stock_scout.db.repo import FakeRepo
from stock_scout.pipeline import run_pipeline

CONFIG_DIR = Path(__file__).parents[1] / "config"


def test_dry_run_end_to_end(capsys):
    settings = Settings.load(CONFIG_DIR)
    repo = FakeRepo()

    stats = run_pipeline(settings, repo, dry_run=True, slot="premarket")

    assert stats["posts"] > 0
    assert stats["symbols_mentioned"] >= 2

    # ABCD: 3 unique authors across 2 leading subreddits -> novelty alert
    alert_symbols = {a["symbol"] for a in repo.alerts}
    assert "ABCD" in alert_symbols

    # GME is mainstream (fixture apewisdom top) -> must not alert
    assert "GME" not in alert_symbols

    # blacklist trap: bare ALL / IT never became mentions
    assert all(m["symbol"] not in {"ALL", "IT"} for m in repo.mentions)

    # digest printed with the candidate and the disclaimer
    out = capsys.readouterr().out
    assert "ABCD" in out
    assert "非投資建議" in out

    # run bookkeeping
    assert repo.runs[0]["status"] == "ok"


def test_second_run_same_day_is_idempotent():
    settings = Settings.load(CONFIG_DIR)
    repo = FakeRepo()
    run_pipeline(settings, repo, dry_run=True, slot="premarket")
    n_posts = len(repo.posts)
    n_alerts = len(repo.alerts)

    run_pipeline(settings, repo, dry_run=True, slot="postclose")
    assert len(repo.posts) == n_posts       # posts deduped
    assert len(repo.alerts) == n_alerts     # no duplicate alerts for the same day
