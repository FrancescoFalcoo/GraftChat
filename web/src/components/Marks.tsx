/** Small drawings in the app's own visual language: trunk, lane, nodes. */

/** The fork used on chips and buttons: a trunk with one lane leaving it. */
export function ForkIcon() {
  return (
    <svg className="fork" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M4 1.5v13" />
      <path d="M4 4.5c0 3.5 8 2.5 8 6.5v3.5" />
    </svg>
  );
}

/** The mark: a trunk with one lane leaving it and rejoining it. */
export function GraftMark() {
  return (
    <svg className="mark" viewBox="0 0 20 20" width="20" height="20" aria-hidden="true" focusable="false">
      <path className="mark-trunk" d="M6 1.5v17" />
      <path className="mark-lane" d="M6 4c0 3 7.5 2 7.5 6S6 13 6 16" />
    </svg>
  );
}

/**
 * First-screen diagram: an answer on the trunk, a lane leaving it at a passage, and
 * the lane coming back as two points. It draws itself once (see .diagram in thread.css).
 */
export function GraftDiagram() {
  return (
    <svg className="diagram" viewBox="0 0 260 170" aria-hidden="true" focusable="false">
      <path className="d-trunk d-draw" pathLength={1} d="M14 8V164" />
      {/* the question */}
      <circle className="d-ring" cx="14" cy="16" r="4.5" />
      <rect className="d-user" x="32" y="11" width="92" height="10" rx="2" />
      {/* the answer, one passage taped */}
      <circle className="d-dot" cx="14" cy="42" r="4.5" />
      <rect className="d-line" x="32" y="38" width="196" height="7" rx="1" />
      <rect className="d-tint" x="30" y="49" width="104" height="11" rx="2" />
      <rect className="d-line" x="32" y="51" width="100" height="7" rx="1" />
      <path className="d-under" d="M30 61.5H134" />
      <rect className="d-line" x="140" y="51" width="70" height="7" rx="1" />
      <rect className="d-line" x="32" y="64" width="150" height="7" rx="1" />
      {/* the lane leaves the trunk and comes back */}
      <path
        className="d-lane d-draw d-late"
        pathLength={1}
        d="M14 72C14 86 40 80 40 94V108C40 122 14 116 14 130"
      />
      <circle className="d-merge" cx="14" cy="134" r="7" />
      <circle className="d-point d-fade" cx="34" cy="134" r="3" />
      <rect className="d-soft d-fade" x="44" y="131" width="86" height="6" rx="1" />
      <circle className="d-point d-fade" cx="34" cy="152" r="3" />
      <rect className="d-soft d-fade" x="44" y="149" width="62" height="6" rx="1" />
    </svg>
  );
}
