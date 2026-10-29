"""Research-candidate presentation methods, independent of business execution.

Nothing is loaded or injected into a model request on import. Conditions are
caller-supplied, source-labelled inputs, not facts verified by this package.
"""

from .registry import KnowledgeCard, KnowledgeRegistry, load_registry
from .selection import (ConditionEvidence, MethodCandidate, MethodExclusion,
                        MethodSelectionContext, MethodSelectionResult, select_methods)

__all__ = ['KnowledgeCard', 'KnowledgeRegistry', 'load_registry', 'ConditionEvidence',
           'MethodCandidate', 'MethodExclusion', 'MethodSelectionContext',
           'MethodSelectionResult', 'select_methods']
