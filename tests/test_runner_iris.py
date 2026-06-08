import json
import subprocess

from patch_eval.runner import evaluate_agent_output
from patch_eval.types import CORRUPT_PATCH, GIT_APPLY_CHECK_FAILED


def init_iris_repo(tmp_path):
    repo = tmp_path / "iris_repo"
    package = repo / "ml_iris_tree"
    package.mkdir(parents=True)
    (package / "data.py").write_text(
        "from sklearn.datasets import load_iris\n"
        "from sklearn.model_selection import train_test_split\n\n\n"
        "def load_iris_train_test(test_size=0.3, random_state=42):\n"
        "    iris = load_iris()\n"
        "    X = iris.data\n"
        "    y = iris.target\n\n"
        "    X_train, X_test, y_train, y_test = train_test_split(\n"
        "        X,\n"
        "        y,\n"
        "        test_size=test_size,\n"
        "        random_state=0,\n"
        "    )\n\n"
        "    target_names = [\"iris\"]\n"
        "    return X_train, X_test, y_train, y_test, target_names\n",
        encoding="utf-8",
    )
    (package / "model.py").write_text(
        "from sklearn.tree import DecisionTreeClassifier\n\n\n"
        "def train_decision_tree(X_train, y_train, max_depth=3, random_state=42):\n"
        "    model = DecisionTreeClassifier(max_depth=max_depth)\n"
        "    model.fit(X_train, y_train)\n"
        "    return model\n\n\n"
        "def predict_labels(model, X_test):\n"
        "    return model.predict_proba(X_test)\n",
        encoding="utf-8",
    )
    (package / "plot.py").write_text(
        "import matplotlib\n\n"
        "matplotlib.use(\"Agg\")\n\n"
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        "from sklearn.metrics import confusion_matrix\n\n\n"
        "def plot_confusion_matrix(y_true, y_pred, target_names, output_path):\n"
        "    matrix = confusion_matrix(y_true, y_pred)\n\n"
        "    fig, ax = plt.subplots(figsize=(6, 5))\n"
        "    image = ax.imshow(matrix, interpolation=\"nearest\", cmap=\"Blues\")\n"
        "    fig.colorbar(image, ax=ax)\n\n"
        "    tick_marks = np.arange(len(target_names))\n"
        "    ax.set_xticks(tick_marks)\n"
        "    ax.set_yticks(tick_marks)\n"
        "    ax.set_xticklabels([\"class 0\", \"class 1\", \"class 2\"])\n"
        "    ax.set_yticklabels([\"class 0\", \"class 1\", \"class 2\"])\n\n"
        "    ax.set_title(\"Iris confusion matrix\")\n"
        "    ax.set_xlabel(\"True label\")\n"
        "    ax.set_ylabel(\"Predicted label\")\n\n"
        "    fig.tight_layout()\n"
        "    plt.close(fig)\n"
        "    return output_path\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    return repo


def iris_patch() -> str:
    return """diff --git a/ml_iris_tree/data.py b/ml_iris_tree/data.py
--- a/ml_iris_tree/data.py
+++ b/ml_iris_tree/data.py
@@ -11,8 +11,8 @@ def load_iris_train_test(test_size=0.3, random_state=42):
         X,
         y,
         test_size=test_size,
-        random_state=0,
+        random_state=random_state,
     )
 
-    target_names = ["iris"]
+    target_names = list(iris.target_names)
     return X_train, X_test, y_train, y_test, target_names
diff --git a/ml_iris_tree/model.py b/ml_iris_tree/model.py
--- a/ml_iris_tree/model.py
+++ b/ml_iris_tree/model.py
@@ -2,10 +2,10 @@ from sklearn.tree import DecisionTreeClassifier
 
 
 def train_decision_tree(X_train, y_train, max_depth=3, random_state=42):
-    model = DecisionTreeClassifier(max_depth=max_depth)
+    model = DecisionTreeClassifier(max_depth=max_depth, random_state=random_state)
     model.fit(X_train, y_train)
     return model
 
 
 def predict_labels(model, X_test):
-    return model.predict_proba(X_test)
+    return model.predict(X_test)
diff --git a/ml_iris_tree/plot.py b/ml_iris_tree/plot.py
--- a/ml_iris_tree/plot.py
+++ b/ml_iris_tree/plot.py
@@ -17,13 +17,14 @@ def plot_confusion_matrix(y_true, y_pred, target_names, output_path):
     tick_marks = np.arange(len(target_names))
     ax.set_xticks(tick_marks)
     ax.set_yticks(tick_marks)
-    ax.set_xticklabels(["class 0", "class 1", "class 2"])
-    ax.set_yticklabels(["class 0", "class 1", "class 2"])
+    ax.set_xticklabels(target_names)
+    ax.set_yticklabels(target_names)
 
     ax.set_title("Iris confusion matrix")
     ax.set_xlabel("True label")
     ax.set_ylabel("Predicted label")
 
     fig.tight_layout()
+    fig.savefig(output_path)
     plt.close(fig)
     return output_path
"""


def test_runner_accepts_complete_iris_patch(tmp_path):
    repo = init_iris_repo(tmp_path)
    raw = json.dumps({"patch": iris_patch()})

    result = evaluate_agent_output(repo, raw)

    assert result.ok
    assert result.cleaned_patch is not None
    assert result.normalized_patch is not None
    assert result.git_apply_stderr == ""
    assert result.git_apply_command == "git apply --check -"


def test_runner_rejects_iris_patch_with_bad_hunk_header(tmp_path):
    repo = init_iris_repo(tmp_path)
    bad_patch = iris_patch().replace("@@ -17,13 +17,14 @@", "@@ -17,1 +17,1 @@")

    result = evaluate_agent_output(repo, json.dumps({"patch": bad_patch}))

    assert not result.ok
    assert result.error_type in {CORRUPT_PATCH, GIT_APPLY_CHECK_FAILED}
    assert result.git_apply_stderr
