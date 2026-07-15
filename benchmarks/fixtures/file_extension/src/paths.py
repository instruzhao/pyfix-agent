def replace_extension(filename, extension):
    stem = filename.split(".")[0]
    return f"{stem}.{extension}"
