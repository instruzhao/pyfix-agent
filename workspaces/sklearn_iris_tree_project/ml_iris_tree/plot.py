import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import confusion_matrix


def plot_confusion_matrix(y_true, y_pred, target_names, output_path):
    matrix = confusion_matrix(y_true, y_pred)

    fig, ax = plt.subplots(figsize=(6, 5))
    image = ax.imshow(matrix, interpolation="nearest", cmap="Blues")
    fig.colorbar(image, ax=ax)

    tick_marks = np.arange(len(target_names))
    ax.set_xticks(tick_marks)
    ax.set_yticks(tick_marks)
    ax.set_xticklabels(["class 0", "class 1", "class 2"])
    ax.set_yticklabels(["class 0", "class 1", "class 2"])

    ax.set_title("Iris confusion matrix")
    ax.set_xlabel("True label")
    ax.set_ylabel("Predicted label")

    fig.tight_layout()
    plt.close(fig)
    return output_path
