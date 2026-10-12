"""Author/affiliation splitting is linear and matches the regex it replaced
(stress test, 12 October 2026: the regex took 6-7 s on 32,000 unclosed
brackets, stalling the event loop)."""
import random
import re
import time

from korea_scholarship_mcp import server as S

OLD = re.compile(r"^(.*?)\s*[(（](.*)[)）]\s*$")


def _old(raw):
    m = OLD.match(raw)
    return (m.group(1).strip(), m.group(2).strip()) if m else None


def _new(raw):
    m = S._split_affil(raw)
    return (m[0].strip(), m[1].strip()) if m else None


def test_same_answers_as_the_regex():
    rng = random.Random(1)
    for _ in range(20000):
        raw = S._norm("".join(rng.choice("ab (（)）  김이") for _ in range(rng.randint(0, 12))))
        assert _new(raw) == _old(raw), raw


def test_real_shapes():
    assert _new("홍길동(서울대학교)") == ("홍길동", "서울대학교")
    assert _new("홍길동 （서울대학교） ") == ("홍길동", "서울대학교")
    assert _new("Kim (Dept. of History (Seoul))") == ("Kim", "Dept. of History (Seoul)")
    assert _new("홍길동") is None


def test_pathological_creator_is_fast():
    t = time.perf_counter()
    S._split_affil("(" * 200_000)
    S._split_affil("(" * 200_000 + ")")
    assert time.perf_counter() - t < 0.5
