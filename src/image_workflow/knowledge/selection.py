"""Pure, conservative method candidates; no facts, final design or model adoption.

The caller supplies per-output conditions after applying its existing business
permissions. Evidence references are opaque citations: never opened, interpreted
as filenames, or certified here. Unknown is distinct from explicit false.
"""

from dataclasses import dataclass, replace

from .registry import METHOD_IDS, KnowledgeRegistry


# First condition is an explicit relevance trigger, the rest are prerequisites.
METHOD_CONDITIONS = {
    'K01': ('visible_component', 'product_detail_view', 'component_description'),
    'K02': ('multiple_states_supported', 'state_materials'),
    'K03': ('usage_scene_supported', 'usage_limits_known'),
    'K04': ('abstract_claim_supported', 'truthful_visual_basis'),
    'K05': ('multiple_information_items', 'required_content_known'),
    'K06': ('readability_target', 'copy_and_size_available'),
}
CONDITION_SOURCES = {
    'visible_component': ('PRODUCT_MATERIAL',),
    'product_detail_view': ('PRODUCT_MATERIAL',),
    'component_description': ('PERMITTED_CLAIM',),
    'multiple_states_supported': ('PERMITTED_CLAIM',),
    'state_materials': ('PRODUCT_MATERIAL', 'PERMITTED_CLAIM'),
    'usage_scene_supported': ('PERMITTED_CLAIM',),
    'usage_limits_known': ('PERMITTED_CLAIM', 'OPERATOR_INPUT'),
    'abstract_claim_supported': ('PERMITTED_CLAIM',),
    'truthful_visual_basis': ('PRODUCT_MATERIAL', 'PERMITTED_CLAIM'),
    'multiple_information_items': ('PERMITTED_CLAIM', 'OPERATOR_INPUT'),
    'required_content_known': ('OPERATOR_INPUT',),
    'readability_target': ('OUTPUT_SPEC', 'OPERATOR_INPUT'),
    'copy_and_size_available': ('OUTPUT_SPEC',),
}
SLOT_PRIORITIES = {
    'main': ('K05', 'K06', 'K01', 'K02', 'K03', 'K04'),
    'dimensions': ('K05', 'K06', 'K01', 'K04', 'K02', 'K03'),
    'comparison': ('K05', 'K02', 'K01', 'K06', 'K04', 'K03'),
    'selling_point': ('K01', 'K02', 'K04', 'K05', 'K06', 'K03'),
    'scene': ('K03', 'K04', 'K05', 'K06', 'K01', 'K02'),
}


def _references(values):
    if (not isinstance(values, tuple) or any(not isinstance(item, str) or not item.strip() for item in values)
            or len(values) != len(set(values))):
        raise ValueError('Evidence references must be a tuple of unique nonempty citations.')


@dataclass(frozen=True)
class ConditionEvidence:
    condition: str
    value: bool | None
    basis_kind: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.condition, str) or self.condition not in CONDITION_SOURCES:
            raise ValueError('Unknown method condition.')
        if self.value is not None and type(self.value) is not bool:
            raise ValueError('Condition value must be True, False or None.')
        _references(self.evidence_refs)
        if self.value is not None and not self.evidence_refs:
            raise ValueError('A known condition needs an explicit evidence reference.')
        if self.basis_kind is not None and self.basis_kind not in CONDITION_SOURCES[self.condition]:
            raise ValueError('Evidence source role is not appropriate for this condition.')
        if self.value is not None and self.basis_kind is None:
            raise ValueError('A known condition needs an explicit source role.')


@dataclass(frozen=True)
class MethodExclusion:
    method_id: str
    reason: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self):
        if self.method_id not in METHOD_IDS or not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError('A method exclusion needs a known ID and explicit reason.')
        _references(self.evidence_refs)
        if not self.evidence_refs:
            raise ValueError('An exclusion needs an evidence reference.')


@dataclass(frozen=True)
class MethodSelectionContext:
    business_mode: str
    slot_type: str
    quick_scenario: str | None = None
    output_intent: str = ''
    conditions: tuple[ConditionEvidence, ...] = ()
    exclusions: tuple[MethodExclusion, ...] = ()

    def __post_init__(self):
        if self.business_mode not in ('quick_redesign', 'product_pack'):
            raise ValueError('Use the existing Quick or Listing business mode.')
        if ((self.business_mode == 'quick_redesign' and self.quick_scenario not in ('quick_a', 'quick_b')) or
                (self.business_mode == 'product_pack' and self.quick_scenario is not None)):
            raise ValueError('Quick-A/B must be explicit; do not infer a historical scenario.')
        if not isinstance(self.slot_type, str) or self.slot_type not in SLOT_PRIORITIES:
            raise ValueError('Unknown output slot type.')
        if not isinstance(self.output_intent, str):
            raise ValueError('Output intent must be text; it is not parsed for product facts.')
        for values, kind, key in ((self.conditions, ConditionEvidence, 'condition'),
                                  (self.exclusions, MethodExclusion, 'method_id')):
            if not isinstance(values, tuple) or any(not isinstance(item, kind) for item in values):
                raise ValueError('Selection conditions and exclusions must be typed tuples.')
            if len(values) != len({getattr(item, key) for item in values}):
                raise ValueError('Duplicate or contradictory method conditions/exclusions.')


@dataclass(frozen=True)
class MethodCandidate:
    method_id: str
    method_version: str
    eligibility: str
    selection_reason: str
    evidence_basis: tuple[ConditionEvidence, ...]
    missing_conditions: tuple[str, ...]
    content_hash: str
    priority: int
    exclusion: MethodExclusion | None = None
    omission_reason: str | None = None


@dataclass(frozen=True)
class MethodSelectionResult:
    context: MethodSelectionContext
    selected: tuple[MethodCandidate, ...]
    not_selected: tuple[MethodCandidate, ...]
    max_candidates: int
    stage: str = 'METHOD_CANDIDATE_SELECTED'


def select_methods(context, registry, *, max_candidates=3, priority=None):
    """Return at most the budget, without loading cards into any model Context.

    All six assessments remain visible. Unknown relevance is CONDITIONAL but
    stays outside selected until a source-backed trigger exists. A positive
    trigger with missing prerequisites may be a CONDITIONAL candidate, never an
    instruction to apply the method. ELIGIBLE is not independent fact validation.
    Slot type affects tie-breaking only; free-text intent is retained, not mined.
    """
    if not isinstance(context, MethodSelectionContext) or not isinstance(registry, KnowledgeRegistry):
        raise ValueError('Selection requires a typed context and validated registry.')
    if type(max_candidates) is not int or not 0 <= max_candidates <= len(METHOD_IDS):
        raise ValueError('Candidate budget must be an integer from zero to six.')
    order = SLOT_PRIORITIES[context.slot_type] if priority is None else priority
    if (not isinstance(order, tuple) or len(order) != len(METHOD_IDS) or
            any(item not in METHOD_IDS for item in order) or len(set(order)) != len(METHOD_IDS)):
        raise ValueError('Priority must name every method exactly once.')
    supplied = {item.condition: item for item in context.conditions}
    exclusions = {item.method_id: item for item in context.exclusions}
    assessed = []
    for identity in METHOD_IDS:
        required = METHOD_CONDITIONS[identity]
        basis = tuple(supplied[name] for name in required if name in supplied)
        missing = tuple(name for name in required if name not in supplied or supplied[name].value is None)
        negative = tuple(item.condition for item in basis if item.value is False)
        exclusion = exclusions.get(identity)
        if exclusion or negative:
            eligibility = 'EXCLUDED'
            reason = '明确限制：' + exclusion.reason if exclusion else '条件明确不满足：' + ', '.join(negative)
        elif missing:
            eligibility, reason = 'CONDITIONAL', '缺少明确依据：' + ', '.join(missing)
        else:
            eligibility, reason = 'ELIGIBLE', '调用方提供的条件均有明确来源；仅具备方法候选资格，非独立事实认证。'
        trigger = supplied.get(required[0])
        omission = ('EXPLICIT_EXCLUSION' if eligibility == 'EXCLUDED' else
                    'NO_EXPLICIT_TRIGGER' if trigger is None or trigger.value is not True else None)
        card = registry.get(identity)
        assessed.append(MethodCandidate(identity, card.version, eligibility, reason, basis, missing,
                                        card.content_hash, order.index(identity), exclusion, omission))
    assessed.sort(key=lambda item: ({'ELIGIBLE': 0, 'CONDITIONAL': 1, 'EXCLUDED': 2}[item.eligibility],
                                   item.priority, item.method_id))
    selected, not_selected = [], []
    for candidate in assessed:
        if candidate.omission_reason is not None:
            not_selected.append(candidate)
        elif len(selected) < max_candidates:
            selected.append(candidate)
        else:
            not_selected.append(replace(candidate, omission_reason='CANDIDATE_BUDGET'))
    return MethodSelectionResult(context, tuple(selected), tuple(not_selected), max_candidates)
