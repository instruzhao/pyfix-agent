from sklearn.tree import DecisionTreeClassifier


def train_decision_tree(X_train, y_train, max_depth=3, random_state=42):
    model = DecisionTreeClassifier(max_depth=max_depth)
    model.fit(X_train, y_train)
    return model


def predict_labels(model, X_test):
    return model.predict_proba(X_test)
