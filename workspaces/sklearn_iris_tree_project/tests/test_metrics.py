import pytest

from ml_iris_tree.metrics import evaluate_multiclass_classification


def test_evaluate_multiclass_classification_returns_expected_metric_dict():
    y_true = [0, 0, 1, 1, 2, 2]
    y_pred = [0, 1, 1, 1, 2, 0]

    metrics = evaluate_multiclass_classification(y_true, y_pred)

    assert isinstance(metrics, dict)
    assert set(metrics) == {"accuracy", "precision_macro", "recall_macro", "f1_macro"}
    for value in metrics.values():
        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0
    assert metrics["accuracy"] == pytest.approx(4 / 6)
