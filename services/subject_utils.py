from sqlalchemy import false, func, or_


_ALIASES = {
    'General Studies': {'general study', 'general studies'},
}


def normalize_subject(value):
    """Return a stable subject label for storage and comparisons."""
    subject = (value or '').strip()
    aliases = {
        'general study': 'General Studies',
        'general studies': 'General Studies',
    }
    return aliases.get(subject.casefold(), subject)


def subjects_match(left, right):
    """Compare two subject labels ignoring case and surrounding whitespace."""
    return normalize_subject(left).casefold() == normalize_subject(right).casefold()


def subject_match_clause(column, subject):
    """Build a case-insensitive, trimmed SQLAlchemy filter for subject columns."""
    normalized = normalize_subject(subject)
    if not normalized:
        return false()
    candidates = {normalized.casefold()}
    candidates.update(_ALIASES.get(normalized, set()))
    return or_(*[func.lower(func.trim(column)) == candidate for candidate in candidates])


def any_subject_match_clause(column, subjects):
    """Match a column against any subject in a list, honoring aliases."""
    clauses = [subject_match_clause(column, subject) for subject in (subjects or [])]
    if not clauses:
        return false()
    return or_(*clauses)
