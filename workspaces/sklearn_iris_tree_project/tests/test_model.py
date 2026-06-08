from sklearn.metrics import accuracy_score
from sklearn.tree import DecisionTreeClassifier

from ml_iris_tree.data import load_iris_train_test
from ml_iris_tree.model import predict_labels, train_decision_tree


def test_train_decision_tree_returns_fitted_classifier():
    X_train, X_test, y_train, y_test, target_names = load_iris_train_test()

    model = train_decision_tree(X_train, y_train, max_depth=3, random_state=42)

    assert isinstance(model, DecisionTreeClassifier)
    assert hasattr(model, "classes_")


def test_predict_labels_returns_one_dimensional_labels_with_good_accuracy():
    X_train, X_test, y_train, y_test, target_names = load_iris_train_test()
    model = train_decision_tree(X_train, y_train, max_depth=3, random_state=42)

    y_pred = predict_labels(model, X_test)

    assert y_pred.ndim == 1
    assert len(y_pred) == X_test.shape[0]
    assert accuracy_score(y_test, y_pred) >= 0.85
