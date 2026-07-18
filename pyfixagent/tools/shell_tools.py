from pyfixagent.sandbox.base import CommandResult, Sandbox


def run_pytest(sandbox: Sandbox) -> CommandResult:
    return sandbox.run(["python", "-m", "pytest", "-p", "no:cacheprovider"])
