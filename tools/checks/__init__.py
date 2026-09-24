from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAILURES = []

# song titles, charter names and pattern tags are mostly Japanese, and a Windows console defaults to
# a codepage that cannot print them: without this the sweep dies on the first check that names one
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# The order the sweep reads in. Each of these runs its checks as it is imported, so this list is
# what decides the order they are reported in, and a new file only counts once it is named here.
TOPICS = ["wiring", "rating", "session", "lookup", "habits", "traits", "simai", "web", "laya"]


def check(name):
    """Mark a step and record whatever it reports.

    :param name: What the step is called in the output.
    :type name: str
    :returns: A decorator that runs the step and collects its complaints.
    :rtype: Callable
    """
    def wrap(fn):
        try:
            problems = fn() or []
        except Exception as error:
            problems = [f"the check itself failed: {type(error).__name__}: {error}"]
        # printed after the step runs, so a library logging on import cannot split the line
        print(f"  {'FAIL' if problems else 'ok  '}  {name}", flush=True)
        for problem in problems:
            print(f"          {problem}")
        if problems:
            FAILURES.append(name)
        return fn
    return wrap


def python_files():
    """Every Python file the project owns.

    :rtype: List[Path]
    """
    return sorted(list((ROOT / "rasmai").rglob("*.py")) + list((ROOT / "tools").rglob("*.py")) + [ROOT / "dev.py"])


def run() -> None:
    """Read every topic, which runs its checks, then exit non-zero if any of them complained."""
    import importlib
    print("Rasmai verification sweep")
    for topic in TOPICS:
        importlib.import_module(f"tools.checks.{topic}")
    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed: {', '.join(FAILURES)}")
        sys.exit(1)
    print("\nEverything passed.")
