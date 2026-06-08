from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split


def load_iris_train_test(test_size=0.3, random_state=42):
    iris = load_iris()
    X = iris.data
    y = iris.target

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=0,
    )

    target_names = ["iris"]
    return X_train, X_test, y_train, y_test, target_names
