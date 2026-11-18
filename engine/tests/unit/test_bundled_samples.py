"""The FDA label samples ship with the code (repo and wheel), so the demo documents never
depend on openFDA being reachable at build time."""

from __future__ import annotations

from wittgenstein.live import store


def test_samples_load_without_any_fetched_corpora(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(store, "LIVE_CORPORA", tmp_path / "live_corpora")  # nothing fetched
    s = store.CorpusStore()
    s.load_defaults()
    ids = {r.corpus_id for r in s.list()}
    assert {"asteria", "fda-labels", "fda-labels-heldout"} <= ids
    fda = s.get("fda-labels")
    assert fda is not None and fda.title.startswith("FDA drug labels")


def test_a_local_folder_replaces_the_bundled_copy(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    local = tmp_path / "live_corpora" / "fda-labels"
    local.mkdir(parents=True)
    (local / "metformin.md").write_text("A refreshed metformin label with enough words to read.")
    monkeypatch.setattr(store, "LIVE_CORPORA", tmp_path / "live_corpora")
    s = store.CorpusStore()
    s.load_defaults()
    assert [r.corpus_id for r in s.list()].count("fda-labels") == 1
