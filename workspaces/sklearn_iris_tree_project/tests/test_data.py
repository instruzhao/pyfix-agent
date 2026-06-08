import numpy as np

from ml_iris_tree.data import load_iris_train_test


def test_load_iris_train_test_returns_expected_shapes_and_classes():
    result = load_iris_train_test(test_size=0.3, random_state=42)

    assert len(result) == 5
    X_train, X_test, y_train, y_test, target_names = result

    assert X_train.shape[0] + X_test.shape[0] == 150
    assert X_train.shape[1] == 4
    assert len(np.unique(y_train)) == 3
    assert len(np.unique(y_test)) == 3
    assert len(target_names) == 3
    assert X_test.shape[0] == 45


def test_load_iris_train_test_is_reproducible_with_same_random_state():
    first = load_iris_train_test(test_size=0.3, random_state=7)
    second = load_iris_train_test(test_size=0.3, random_state=7)

    for first_value, second_value in zip(first[:4], second[:4]):
        assert np.array_equal(first_value, second_value)
