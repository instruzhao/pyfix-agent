DANGEROUS_TOKENS = {
    "rm",
    "sudo",
    "shutdown",
    "reboot",
    "curl",
    "wget",
    "powershell",
    "cmd",
    "del",
    "erase",
    "format",
}


def is_command_allowed(command: list[str]) -> tuple[bool, str | None]:
    if not command:
        return False, "empty command is not allowed"

    lowered = [part.lower() for part in command]
    joined = " ".join(lowered)
    if "rm -rf" in joined:
        return False, "dangerous command is not allowed: rm -rf"

    for token in lowered:
        if token in DANGEROUS_TOKENS:
            return False, f"dangerous command is not allowed: {token}"

    if lowered[0] == "pytest":
        return True, None

    if lowered[0] == "python":
        if len(lowered) == 1:
            return True, None
        if len(lowered) >= 3 and lowered[1] == "-m" and lowered[2] == "pytest":
            return True, None
        return True, None

    return False, f"command is not allowed: {command[0]}"
