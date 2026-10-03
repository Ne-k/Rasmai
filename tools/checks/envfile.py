from tools.checks import check


@check("an env file is read with quotes, an export prefix and comments, never overrides a set variable, and may be missing")
def _envfile():
    import os
    import pathlib
    import tempfile
    from rasmai.config import load_env
    problems = []
    folder = pathlib.Path(tempfile.mkdtemp())
    lines = ["# ENVCHECK_COMMENTED=no", "", "ENVCHECK_PLAIN=plain", "export ENVCHECK_EXPORTED=exported",
             'ENVCHECK_DOUBLE="two words"', "ENVCHECK_SINGLE='keeps # this'", "ENVCHECK_INLINE=value # not this",
             "ENVCHECK_HASH=a#b", "ENVCHECK_EQUALS=a=b", "ENVCHECK_SET=from the file", "no equals sign here"]
    (folder / ".env").write_bytes("\r\n".join(lines).encode())
    os.environ["ENVCHECK_SET"] = "already"
    want = {"ENVCHECK_COMMENTED": None, "ENVCHECK_PLAIN": "plain", "ENVCHECK_EXPORTED": "exported", "ENVCHECK_DOUBLE": "two words",
            "ENVCHECK_SINGLE": "keeps # this", "ENVCHECK_INLINE": "value", "ENVCHECK_HASH": "a#b", "ENVCHECK_EQUALS": "a=b",
            "ENVCHECK_SET": "already"}
    try:
        load_env(folder / ".env")
        load_env(folder / "missing.env")
        for name, value in want.items():
            if os.environ.get(name) != value:
                problems.append(f"{name} came out as {os.environ.get(name)!r}, not {value!r}")
    finally:
        for name in want:
            os.environ.pop(name, None)
    return problems
