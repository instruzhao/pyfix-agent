from pyfixagent.sandbox.local_sandbox import CommandResult, LocalSandbox


def run_pytest(sandbox: LocalSandbox) -> CommandResult:
    return sandbox.run(["python", "-m", "pytest", "-p", "no:cacheprovider"])
