from app.trust_mirror import score_label


def test_score_label_excellent():
    assert score_label(0.90) == "Excellent"


def test_score_label_good():
    assert score_label(0.75) == "Good"


def test_score_label_fair():
    assert score_label(0.60) == "Fair"


def test_score_label_needs_improvement():
    assert score_label(0.40) == "Needs Improvement"


def test_score_label_boundary_is_inclusive():
    assert score_label(0.85) == "Excellent"
    assert score_label(0.70) == "Good"
    assert score_label(0.55) == "Fair"
