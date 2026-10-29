"""V2 lifecycle transition matrix (PRD_V2 §5.2, Design §2).

Admin-only moves, no gates, UI confirms every change. Archive is reversible:
restore returns an idea to the stage it left (see Idea.archived_from).
"""

from app.models.enums import IdeaStatus

S = IdeaStatus

ALLOWED_TRANSITIONS: dict[IdeaStatus, frozenset] = {
    # Archive is reversible (2026-10-26 decision, amends C5): any live
    # stage can archive, and restore returns the idea to the stage it left.
    S.SPARK: frozenset({S.SCOPE, S.MAP, S.DROP, S.FREEZE, S.ARCHIVE}),
    S.SCOPE: frozenset({S.MAP, S.SHIP, S.DROP, S.FREEZE, S.ARCHIVE}),
    S.MAP: frozenset({S.SCOPE, S.SHIP, S.DROP, S.FREEZE, S.ARCHIVE}),
    S.SHIP: frozenset({S.SCOPE, S.MAP, S.SCALE, S.DROP, S.FREEZE, S.ARCHIVE}),
    S.SCALE: frozenset({S.SCOPE, S.MAP, S.SHIP, S.DROP, S.FREEZE, S.ARCHIVE}),
    S.DROP: frozenset({S.SCOPE, S.MAP, S.SHIP, S.SCALE, S.FREEZE, S.ARCHIVE}),
    S.FREEZE: frozenset({S.SCOPE, S.MAP, S.SHIP, S.SCALE, S.DROP, S.ARCHIVE}),
    S.ARCHIVE: frozenset({S.SPARK, S.SCOPE, S.MAP, S.SHIP, S.SCALE, S.DROP, S.FREEZE}),
}

# Secondary-action gates per stage (PRD_V2 §5.4). Doc actions unlock as
# the idea matures; dropped/archived ideas are read-only history.
ACTIONS_BLOCKED_STATES = frozenset({S.DROP, S.ARCHIVE})
PRD_MIN_STATES = frozenset({S.SCOPE, S.MAP, S.SHIP, S.SCALE, S.FREEZE})
DESIGN_DOC_STATES = frozenset({S.MAP, S.SHIP, S.SCALE, S.FREEZE})
BUILD_MIN_STATES = frozenset({S.SHIP, S.SCALE})


def can_transition(frm: IdeaStatus, to: IdeaStatus) -> bool:
    """Same-state moves are no-ops the caller handles; anything else must be listed."""
    if frm == to:
        return True
    return to in ALLOWED_TRANSITIONS.get(frm, frozenset())


def allowed_from(frm: IdeaStatus) -> list[str]:
    return sorted(s.value for s in ALLOWED_TRANSITIONS.get(frm, frozenset()))
