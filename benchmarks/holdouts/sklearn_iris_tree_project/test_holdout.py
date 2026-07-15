import numpy as np

from ml_iris_tree.data import load_iris_train_test
from ml_iris_tree.model import predict_labels, train_decision_tree


def test_target_names_and_predictions_are_real_multiclass_values():
    X_train, X_test, y_train, y_test, target_names = load_iris_train_test(random_state=7)
    model = train_decision_tree(X_train, y_train, max_depth=4, random_state=7)
    predicted = predict_labels(model, X_test)

    assert list(target_names) == ["setosa", "versicolor", "virginica"]
    assert predicted.shape == y_test.shape
    assert set(np.unique(predicted)).issubset({0, 1, 2})
    assert (predicted == y_test).mean() >= 0.85
