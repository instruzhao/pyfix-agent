import matplotlib.pyplot as plt

from ml_iris_tree.data import load_iris_train_test
from ml_iris_tree.model import predict_labels, train_decision_tree
from ml_iris_tree.plot import plot_confusion_matrix


def test_plot_confusion_matrix_saves_file_and_closes_figure(tmp_path):
    X_train, X_test, y_train, y_test, target_names = load_iris_train_test()
    model = train_decision_tree(X_train, y_train, max_depth=3, random_state=42)
    y_pred = predict_labels(model, X_test)
    output_path = tmp_path / "confusion_matrix.png"

    returned_path = plot_confusion_matrix(y_test, y_pred, target_names, output_path)

    assert returned_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert plt.get_fignums() == []
