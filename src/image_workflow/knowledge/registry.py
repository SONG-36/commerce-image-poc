"""Fixed local research assets; no environment, business storage or SDK access."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re


METHOD_IDS = ('K01', 'K02', 'K03', 'K04', 'K05', 'K06')
RESEARCH_DOCUMENT = 'docs/04_AI_AGENT_SUITABILITY/S5_PROFESSIONAL_DESIGN_KNOWLEDGE_RESEARCH_V0.1.md'
SOURCE_IDS = tuple(f'SRC-{i:02}' for i in range(1, 10))


def _text(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError('Knowledge text must be a nonempty, trimmed string.')
    return value


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError('Knowledge version must be an explicit major.minor string.')
    return value


def _texts(value):
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError('Knowledge text collections must be nonempty arrays.')
    result = tuple(_text(item) for item in value)
    if len(result) != len(set(result)):
        raise ValueError('Duplicate Knowledge text entries.')
    return result


@dataclass(frozen=True)
class SourceReference:
    """Source IDs are unverified research leads, not primary-source endorsement."""

    document: str
    card_section: str
    registered_source_ids: tuple[str, ...]
    source_status: str

    def to_dict(self):
        return dict(document=self.document, card_section=self.card_section,
                    registered_source_ids=list(self.registered_source_ids), source_status=self.source_status)


@dataclass(frozen=True)
class KnowledgeCard:
    method_id: str
    version: str
    title: str
    applicable_conditions: tuple[str, ...]
    method_instructions: tuple[str, ...]
    limitations: tuple[str, ...]
    source_reference: SourceReference
    status: str

    @classmethod
    def from_dict(cls, data):
        fields = {'method_id', 'version', 'title', 'applicable_conditions', 'method_instructions',
                  'limitations', 'source_reference', 'status'}
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError('Invalid Knowledge card fields.')
        if data['method_id'] not in METHOD_IDS or data['status'] != 'RESEARCH_CANDIDATE':
            raise ValueError('Unknown method or non-candidate Knowledge status.')
        title = _text(data['title'])
        source = data['source_reference']
        if not isinstance(source, dict) or set(source) != {
                'document', 'card_section', 'registered_source_ids', 'source_status'}:
            raise ValueError('Invalid Knowledge source reference.')
        sources = _texts(source['registered_source_ids'])
        if (source['document'] != RESEARCH_DOCUMENT or
                source['card_section'] != data['method_id'] + '｜' + title or
                any(item not in SOURCE_IDS for item in sources) or
                source['source_status'] != 'SOURCE_LEAD_VERIFY'):
            raise ValueError('Knowledge must retain the registered research source and uncertainty.')
        return cls(data['method_id'], _version(data['version']), title,
                   _texts(data['applicable_conditions']), _texts(data['method_instructions']),
                   _texts(data['limitations']), SourceReference(source['document'], source['card_section'],
                   sources, source['source_status']), data['status'])

    def to_dict(self):
        """Independent JSON-ready data; content_hash is derived, never self-hashed."""
        return dict(method_id=self.method_id, version=self.version, title=self.title,
                    applicable_conditions=list(self.applicable_conditions),
                    method_instructions=list(self.method_instructions), limitations=list(self.limitations),
                    source_reference=self.source_reference.to_dict(), status=self.status)

    @property
    def content_hash(self):
        canonical = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                               separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


class KnowledgeRegistry:
    """One explicit version per stable method ID; in-memory data validation only.

    Query arguments are IDs/versions, never file paths. A registry cannot contain
    two versions of the same ID: a different revision needs a separate registry.
    """

    def __init__(self, data):
        if not isinstance(data, (list, tuple)):
            raise ValueError('Knowledge assets must be a card array, not a path.')
        cards = {}
        for item in data:
            card = KnowledgeCard.from_dict(item)
            if card.method_id in cards:
                raise ValueError('Duplicate method ID or conflicting versions.')
            cards[card.method_id] = card
        if set(cards) != set(METHOD_IDS):
            raise ValueError('The research registry must contain K01 through K06 exactly once.')
        self._cards = tuple(cards[identity] for identity in METHOD_IDS)

    @property
    def cards(self):
        return self._cards

    def get(self, method_id, *, version=None):
        if not isinstance(method_id, str) or method_id not in METHOD_IDS:
            raise KeyError('Knowledge method does not exist.')
        if version is not None:
            _version(version)
        card = self._cards[METHOD_IDS.index(method_id)]
        if version is not None and version != card.version:
            raise KeyError('Requested Knowledge version is not loaded.')
        return card


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate Knowledge JSON field.')
        result[key] = value
    return result


def load_registry():
    """Read only the package's named static asset. No caller-provided paths."""
    asset = Path(__file__).with_name('cards_v0_1.json')
    if asset.is_symlink():
        raise ValueError('Knowledge asset must not be a symlink.')
    return KnowledgeRegistry(json.loads(asset.read_text(encoding='utf-8'), object_pairs_hook=_unique_object))
