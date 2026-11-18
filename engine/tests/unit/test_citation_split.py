"""Each answer sentence keeps its own citations, not the next sentence's."""

from wittgenstein.live.verify import split_answer


def test_full_stop_after_marker_stays_with_its_sentence() -> None:
    got = split_answer("A has 130 learners [1]. As a scribe they interpret [2]. Letters praise them [3].")
    assert got == [
        ("A has 130 learners.", [1]),
        ("As a scribe they interpret.", [2]),
        ("Letters praise them.", [3]),
    ]


def test_marker_after_full_stop_still_splits() -> None:
    assert split_answer("He went home. [1] To complete it, sign [2]") == [
        ("He went home.", [1]),
        ("To complete it, sign", [2]),
    ]
