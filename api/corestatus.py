"""Which ``core`` functions are implemented and which are still stubs.

The backend is written against the signatures of ``core``; some functions may
still ``raise NotImplementedError``. ``GET /api/health`` reports them so the UI
can say exactly what is missing instead of failing mysteriously.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from core import context, tree
from core.models import Branch, BranchStatus, Message, Role

_T = datetime(2026, 1, 1, tzinfo=timezone.utc)
_USER = Message(1, 1, None, None, Role.USER, "question", _T)
_ANSWER = Message(2, 1, None, 1, Role.ASSISTANT, "answer", _T)
_BRANCH = Branch(1, 1, 2, 0, 6, "answer", BranchStatus.OPEN, None, _T)
_MESSAGES = [_USER, _ANSWER]

# One harmless call per function. Looked up through the module at call time.
_PROBES: dict[str, Callable[[], object]] = {
    "core.tree.pending_branches": lambda: tree.pending_branches([_BRANCH]),
    "core.tree.check_invariants": lambda: tree.check_invariants(_MESSAGES, [_BRANCH], []),
    "core.context.render_merge_block": lambda: context.render_merge_block("answer", []),
    "core.context.render_anchor_note": lambda: context.render_anchor_note("answer"),
    "core.context.build_main_context": lambda: context.build_main_context(_MESSAGES, [_BRANCH], []),
    "core.context.build_branch_context": lambda: context.build_branch_context(
        _BRANCH, _MESSAGES, [_BRANCH], []
    ),
}


def core_status() -> dict[str, bool]:
    """``{"core.tree.pending_branches": True, ...}``: False = still raises NotImplementedError."""
    status = {}
    for name, probe in _PROBES.items():
        try:
            probe()
        except NotImplementedError:
            status[name] = False
        except Exception:  # noqa: BLE001 - any other outcome means there is real code behind it
            status[name] = True
        else:
            status[name] = True
    return status
