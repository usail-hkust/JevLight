CANONICAL_CONTROL_PHASES = ("ETWT", "NTST", "ELWL", "NLSL")


def split_phase_movements(phase_name):
    if not phase_name or len(phase_name) % 2 != 0:
        return []
    return [phase_name[i:i + 2] for i in range(0, len(phase_name), 2)]


def get_canonical_control_phase(phase_name):
    """
    Return the full four-phase family for a supported phase name.

    A phase is supported only when all of its movements belong to one of the
    canonical opposite-direction phase families. Single-movement phases such as
    ET are mapped to their full family, e.g. ETWT.
    """
    movements = split_phase_movements(phase_name)
    if not movements:
        return None

    movement_set = set(movements)
    for canonical_phase in CANONICAL_CONTROL_PHASES:
        canonical_movements = set(split_phase_movements(canonical_phase))
        if movement_set and movement_set.issubset(canonical_movements):
            return canonical_phase
    return None


def resolve_phase_to_available(phase_name, available_phases):
    """
    Map a phase name onto an executable phase from available_phases.

    Exact matches pass through. Single-movement abbreviations (e.g. 'EL')
    resolve to the available phase from the same canonical family (e.g.
    'ELWL'), mirroring how filter_supported_control_phases represents
    partial phases. Returns None when no executable phase matches.
    """
    if phase_name in available_phases:
        return phase_name

    canonical_phase = get_canonical_control_phase(phase_name)
    if canonical_phase is None:
        return None

    for available_phase in available_phases:
        if get_canonical_control_phase(available_phase) == canonical_phase:
            return available_phase

    return None


def filter_supported_control_phases(phase_names):
    """
    Keep supported phases in canonical id order while preserving the actual
    available phase name for partially supported phases.
    """
    selected = {}

    for phase_name in phase_names:
        if phase_name in CANONICAL_CONTROL_PHASES:
            selected[phase_name] = phase_name

    for phase_name in phase_names:
        if phase_name in CANONICAL_CONTROL_PHASES:
            continue

        canonical_phase = get_canonical_control_phase(phase_name)
        if canonical_phase is None or canonical_phase in selected:
            continue
        selected[canonical_phase] = phase_name

    return [
        selected[canonical_phase]
        for canonical_phase in CANONICAL_CONTROL_PHASES
        if canonical_phase in selected
    ]
