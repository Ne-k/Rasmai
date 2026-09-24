import ast
import importlib
import subprocess
import sys

from tools.checks import ROOT, check, python_files


@check("no undefined names, shadowed definitions or repeated keys")
def _pyflakes():
    # this is what catches a name that only fails when the line runs, which no import test reaches
    result = subprocess.run([sys.executable, "-m", "pyflakes", "rasmai", "tools", "dev.py"],
                            cwd=str(ROOT), capture_output=True, text=True)
    if "No module named" in result.stderr:
        return ["pyflakes is not installed: pip install pyflakes"]
    ignore = ("imported but unused", "unable to detect undefined names", "'from .* import \\*' used")
    return [line for line in result.stdout.splitlines() if line.strip() and not any(skip in line for skip in ignore)]


@check("every module imports")
def _imports():
    problems = []
    for path in sorted((ROOT / "rasmai").rglob("*.py")):
        if path.name in ("__init__.py", "__main__.py"):
            continue
        module = str(path.relative_to(ROOT).with_suffix("")).replace("\\", ".").replace("/", ".")
        try:
            importlib.import_module(module)
        except Exception as error:
            problems.append(f"{module}: {type(error).__name__}: {error}")
    return problems


@check("starting the bot fills the command tree")
def _commands():
    # An empty tree once told Discord to delete every command, because the import that registers
    # them read as unused and was removed. This runs the real start-up path in a clean interpreter
    # and never imports the commands itself, so it fails if setup_hook stops filling the tree.
    script = """
import asyncio, sys
sys.path.insert(0, %r)
from rasmai.bot import core
async def _skip_sync():
    pass
core.sync_commands_if_changed = _skip_sync
asyncio.run(core.setup_hook())
print("NAMES:" + ",".join(sorted(c.name for c in core.bot.tree.get_commands())))
"""
    result = subprocess.run([sys.executable, "-c", script % str(ROOT)], cwd=str(ROOT),
                            capture_output=True, text=True)
    line = next((l for l in result.stdout.splitlines() if l.startswith("NAMES:")), None)
    if line is None:
        return [f"start-up did not reach the command tree: {result.stderr.strip().splitlines()[-1:] or result.stdout}"]
    names = [n for n in line[len("NAMES:"):].split(",") if n]
    problems = []
    if not names:
        return ["start-up left the command tree empty: syncing that would delete every registered command"]
    if len(names) < 20:
        problems.append(f"only {len(names)} commands registered, expected the full set")
    for wanted in ("analyze", "plan", "session", "new", "chart", "charts", "recent", "area", "refresh", "login"):
        if wanted not in names:
            problems.append(f"/{wanted} is missing from the tree")
    # folded into other commands: a stray registration means an old module came back
    for gone in ("song", "level", "lastplay", "traits"):
        if gone in names:
            problems.append(f"/{gone} is registered again; it was folded into /chart, /charts, /recent and the results view")
    from rasmai.bot.builders.results import ResultsView
    if "traits" not in {key for key, _label in ResultsView.MODES}:
        problems.append("the results view has no Traits mode, so traits are unreachable")
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        problems.append(f"the same name is registered twice: {sorted(duplicates)}")
    return problems


@check("no component sends more defaults than Discord allows")
def _components():
    # a select may pre-select at most max_values options; sending two is a 400 that only shows at runtime
    import discord
    from rasmai.bot.builders.results import ResultsView, NEW_LEVELS
    problems = []
    for mode in ("analyze", "plan", "session", "new", "profile", "traits"):
        for difficulty in (None, "master"):
            for level in [None] + list(NEW_LEVELS)[:3]:
                for focus in (None, "weak", "strong"):
                    view = ResultsView(1, mode, difficulty=difficulty, level=level, focus=focus)
                    for item in view.children:
                        if isinstance(item, discord.ui.Select):
                            chosen = [option for option in item.options if option.default]
                            if len(chosen) > item.max_values:
                                problems.append(
                                    f"{mode} difficulty={difficulty} level={level} focus={focus}: "
                                    f"{len(chosen)} defaults but max_values={item.max_values}")
                            if len(item.options) > 25:
                                problems.append(f"{mode}: a select holds {len(item.options)} options, the cap is 25")
    return problems[:5]


@check("no annotation names something defined further down its own file")
def _forward_refs():
    """Python 3.12 evaluates annotations when a def is executed; 3.14 defers them.

    A signature that names a class defined later in the same file therefore runs here and fails on
    the version CI uses, so the local sweep has to reproduce the older reading rather than trust it.
    """
    problems = []
    for path in python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue                      # the compile check reports these on its own
        defined_at = {}
        for index, node in enumerate(tree.body):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_at.setdefault(node.name, index)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined_at.setdefault(target.id, index)
        for index, node in enumerate(tree.body):
            for inner in ast.walk(node):
                if not isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                pieces = [arg.annotation for arg in inner.args.args + inner.args.kwonlyargs if arg.annotation]
                if inner.returns is not None:
                    pieces.append(inner.returns)
                for piece in pieces:
                    for name in {n.id for n in ast.walk(piece) if isinstance(n, ast.Name)}:
                        later = defined_at.get(name)
                        if later is not None and later > index:
                            problems.append(f"{path}: {inner.name}() is annotated with {name}, which this file only defines further down")
    return sorted(set(problems))
