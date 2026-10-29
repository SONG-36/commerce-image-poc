"""B-01: fixed research assets and pure per-output selection, no model calls."""

import copy
from dataclasses import FrozenInstanceError, asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from image_workflow.knowledge import (ConditionEvidence, KnowledgeCard, KnowledgeRegistry,
                                     MethodExclusion, MethodSelectionContext, load_registry, select_methods)
from image_workflow.knowledge.registry import RESEARCH_DOCUMENT


def evidence(name, value=True, kind='PERMITTED_CLAIM', reference=None):
    return ConditionEvidence(name, value, kind, (reference or 'anonymous-brief#' + name,))


def component_conditions():
    return (evidence('visible_component', kind='PRODUCT_MATERIAL', reference='product_001#connector'),
            evidence('product_detail_view', kind='PRODUCT_MATERIAL', reference='product_002#closeup'),
            evidence('component_description', reference='listing#connector'))


def all_conditions():
    return component_conditions() + (
        evidence('multiple_states_supported'), evidence('state_materials', kind='PRODUCT_MATERIAL'),
        evidence('usage_scene_supported'), evidence('usage_limits_known'),
        evidence('abstract_claim_supported'), evidence('truthful_visual_basis', kind='PRODUCT_MATERIAL'),
        evidence('multiple_information_items'), evidence('required_content_known', kind='OPERATOR_INPUT'),
        evidence('readability_target', kind='OUTPUT_SPEC'), evidence('copy_and_size_available', kind='OUTPUT_SPEC'))


class KnowledgeRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()
        self.data = [card.to_dict() for card in self.registry.cards]

    def test_six_cards_have_explicit_versions_actionable_methods_and_uncertainty(self):
        self.assertEqual([card.method_id for card in self.registry.cards],
                         ['K01', 'K02', 'K03', 'K04', 'K05', 'K06'])
        for card in self.registry.cards:
            self.assertEqual(card.version, '0.1')
            self.assertEqual(card.status, 'RESEARCH_CANDIDATE')
            self.assertTrue(card.applicable_conditions)
            self.assertGreaterEqual(len(card.method_instructions), 2)
            self.assertIn('HOW TO PRESENT', '\n'.join(card.limitations))
            self.assertIn('WHAT IS TRUE', '\n'.join(card.limitations))
            self.assertIn('未获运营验证', '\n'.join(card.limitations))
            self.assertEqual(self.registry.get(card.method_id, version='0.1'), card)

    def test_sources_refer_to_existing_card_sections_and_registered_unverified_leads(self):
        document = Path(__file__).resolve().parents[1] / RESEARCH_DOCUMENT
        research = document.read_text(encoding='utf-8')
        for card in self.registry.cards:
            source = card.source_reference
            self.assertEqual(source.document, RESEARCH_DOCUMENT)
            self.assertIn('### ' + source.card_section, research)
            self.assertEqual(source.source_status, 'SOURCE_LEAD_VERIFY')
            for identity in source.registered_source_ids:
                self.assertIn('| ' + identity + ' |', research)

    def test_hash_is_canonical_stable_and_independent_of_json_key_order(self):
        reverse = [{key: row[key] for key in reversed(row)} for row in reversed(self.data)]
        other = KnowledgeRegistry(reverse)
        for card in self.registry.cards:
            canonical = json.dumps(card.to_dict(), ensure_ascii=False, sort_keys=True,
                                   separators=(',', ':'), allow_nan=False).encode('utf-8')
            self.assertEqual(card.content_hash, hashlib.sha256(canonical).hexdigest())
            self.assertEqual(other.get(card.method_id).content_hash, card.content_hash)
            self.assertEqual(load_registry().get(card.method_id).content_hash, card.content_hash)

    def test_content_and_version_changes_are_detectable(self):
        original = self.registry.get('K01')
        for field in ('method_instructions', 'limitations', 'applicable_conditions'):
            changed = original.to_dict()
            changed[field].append('匿名测试新增内容，非生产知识。')
            self.assertNotEqual(KnowledgeCard.from_dict(changed).content_hash, original.content_hash)
        changed = original.to_dict()
        changed['version'] = '0.2'
        updated = KnowledgeCard.from_dict(changed)
        self.assertNotEqual(updated.content_hash, original.content_hash)
        registry = KnowledgeRegistry([updated.to_dict()] + self.data[1:])
        self.assertEqual(registry.get('K01', version='0.2'), updated)
        with self.assertRaises(KeyError):
            registry.get('K01', version='0.1')

    def test_duplicate_ids_and_conflicting_versions_are_rejected(self):
        for version in ('0.1', '0.2'):
            extra = {**self.data[0], 'version': version}
            with self.assertRaisesRegex(ValueError, 'Duplicate method ID'):
                KnowledgeRegistry(self.data + [extra])

    def test_missing_unknown_or_malformed_cards_are_rejected(self):
        variants = [None, {}, RESEARCH_DOCUMENT, [], self.data[:-1]]
        for field, value in [('method_id', 'K99'), ('version', 0.1), ('version', 'latest'),
                             ('version', '0.01'), ('version', '../0.1'), ('version', '0.1.0'),
                             ('status', 'BUSINESS_VALIDATED'), ('title', ''),
                             ('method_instructions', []), ('limitations', 'not an array'),
                             ('applicable_conditions', [True])]:
            changed = copy.deepcopy(self.data)
            changed[0][field] = value
            variants.append(changed)
        changed = copy.deepcopy(self.data)
        del changed[0]['limitations']
        variants.append(changed)
        changed = copy.deepcopy(self.data)
        changed[0]['unexpected'] = 'not accepted'
        variants.append(changed)
        for data in variants:
            with self.subTest(data_type=type(data).__name__), self.assertRaises(ValueError):
                KnowledgeRegistry(data)

    def test_source_paths_and_source_certification_cannot_be_substituted(self):
        for field, value in [('document', '../../outside'), ('card_section', 'invented source'),
                             ('registered_source_ids', ['UNKNOWN']), ('registered_source_ids', ['SRC-01', 'SRC-01']),
                             ('source_status', 'VERIFIED')]:
            changed = copy.deepcopy(self.data)
            changed[0]['source_reference'][field] = value
            with self.assertRaises(ValueError):
                KnowledgeRegistry(changed)

    def test_unknown_id_version_and_arbitrary_path_queries_do_not_read_files(self):
        with patch.object(Path, 'open', side_effect=AssertionError('Queries must not open files')):
            self.assertEqual(self.registry.get('K02').version, '0.1')
            for identity in ('K00', '../../.env', RESEARCH_DOCUMENT, None):
                with self.assertRaises(KeyError):
                    self.registry.get(identity)
            with self.assertRaises(KeyError):
                self.registry.get('K01', version='9.9')
            with self.assertRaises(ValueError):
                self.registry.get('K01', version='latest')
        with self.assertRaises(TypeError):
            load_registry('/arbitrary/path')

    def test_static_loader_rejects_duplicate_json_fields_and_symlinks(self):
        with patch.object(Path, 'read_text', return_value='[{"method_id":"K01","method_id":"K02"}]'):
            with self.assertRaisesRegex(ValueError, 'Duplicate Knowledge JSON'):
                load_registry()
        with patch.object(Path, 'read_text', return_value='not json'):
            with self.assertRaises(ValueError):
                load_registry()
        with patch.object(Path, 'is_symlink', return_value=True), patch.object(Path, 'read_text') as reader:
            with self.assertRaises(ValueError):
                load_registry()
            reader.assert_not_called()

    def test_loaded_cards_and_returned_payloads_do_not_share_mutable_state(self):
        card = self.registry.get('K01')
        original = card.content_hash
        self.data[0]['method_instructions'][0] = 'external mutation'
        exported = card.to_dict()
        exported['limitations'].clear()
        exported['source_reference']['registered_source_ids'].clear()
        with self.assertRaises(FrozenInstanceError):
            card.version = '1.0'
        with self.assertRaises(FrozenInstanceError):
            card.source_reference.document = 'outside'
        self.assertEqual(card.content_hash, original)
        self.assertTrue(card.limitations)


class MethodSelectionTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def context(self, conditions=(), **extra):
        return MethodSelectionContext(**{'business_mode': 'product_pack', 'slot_type': 'selling_point',
                                         'output_intent': '表达当前资料允许的卖点', 'conditions': conditions, **extra})

    def assessment(self, result, identity):
        rows = result.selected + result.not_selected
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({row.method_id for row in rows}), 6)
        return next(row for row in rows if row.method_id == identity)

    def test_k01_has_source_backed_candidate_without_certifying_product_facts(self):
        context = self.context(component_conditions())
        result = select_methods(context, self.registry)
        self.assertEqual([row.method_id for row in result.selected], ['K01'])
        row = result.selected[0]
        self.assertEqual(row.eligibility, 'ELIGIBLE')
        self.assertEqual(row.evidence_basis, context.conditions)
        self.assertEqual(row.missing_conditions, ())
        self.assertIn('非独立事实认证', row.selection_reason)
        self.assertEqual(row.content_hash, self.registry.get('K01').content_hash)
        self.assertEqual(result.stage, 'METHOD_CANDIDATE_SELECTED')
        self.assertNotIn('MODEL_METHOD_ADOPTED', json.dumps(asdict(result)))

    def test_k01_missing_detail_view_remains_conditional_with_exact_gap(self):
        result = select_methods(self.context((component_conditions()[0], component_conditions()[2])), self.registry)
        row = self.assessment(result, 'K01')
        self.assertEqual(row.eligibility, 'CONDITIONAL')
        self.assertEqual(row.missing_conditions, ('product_detail_view',))
        self.assertIn(row, result.selected)
        self.assertNotIn('VERIFIED_APPLICABLE', json.dumps(asdict(result)))

    def test_k02_unknown_states_are_not_assumed_from_slot_or_marketing_words(self):
        result = select_methods(self.context(output_intent='2WAY、可变形、多状态，参考名 two-modes.jpg'), self.registry)
        row = self.assessment(result, 'K02')
        self.assertEqual(row.eligibility, 'CONDITIONAL')
        self.assertEqual(row.missing_conditions, ('multiple_states_supported', 'state_materials'))
        self.assertEqual(row.omission_reason, 'NO_EXPLICIT_TRIGGER')
        self.assertEqual(result.selected, ())

    def test_k02_supported_states_and_materials_are_eligible(self):
        result = select_methods(self.context((evidence('multiple_states_supported'),
            evidence('state_materials', kind='PRODUCT_MATERIAL'))), self.registry)
        self.assertEqual([(r.method_id, r.eligibility) for r in result.selected], [('K02', 'ELIGIBLE')])

    def test_k03_scene_slot_never_creates_unconfirmed_use(self):
        unknown = select_methods(self.context(slot_type='scene'), self.registry)
        self.assertEqual(self.assessment(unknown, 'K03').eligibility, 'CONDITIONAL')
        self.assertEqual(unknown.selected, ())
        unsupported = select_methods(self.context((evidence('usage_scene_supported', False),), slot_type='scene'), self.registry)
        self.assertEqual(self.assessment(unsupported, 'K03').eligibility, 'EXCLUDED')
        supported = select_methods(self.context((evidence('usage_scene_supported'),
            evidence('usage_limits_known', kind='OPERATOR_INPUT')), slot_type='scene'), self.registry)
        self.assertEqual([(r.method_id, r.eligibility) for r in supported.selected], [('K03', 'ELIGIBLE')])

    def test_k04_abstract_claim_needs_a_truthful_presentation_basis(self):
        incomplete = select_methods(self.context((evidence('abstract_claim_supported'),)), self.registry)
        self.assertEqual(self.assessment(incomplete, 'K04').eligibility, 'CONDITIONAL')
        self.assertEqual(self.assessment(incomplete, 'K04').missing_conditions, ('truthful_visual_basis',))
        complete = select_methods(self.context((evidence('abstract_claim_supported'),
            evidence('truthful_visual_basis', kind='PRODUCT_MATERIAL'))), self.registry)
        self.assertEqual(self.assessment(complete, 'K04').eligibility, 'ELIGIBLE')

    def test_k05_multiple_items_and_operator_required_information_select_candidate(self):
        conditions = (evidence('multiple_information_items'), evidence('required_content_known', kind='OPERATOR_INPUT'))
        result = select_methods(self.context(conditions), self.registry)
        self.assertEqual([(r.method_id, r.eligibility) for r in result.selected], [('K05', 'ELIGIBLE')])
        self.assertEqual(result.selected[0].evidence_basis, conditions)

    def test_k06_requires_explicit_display_goal_copy_and_size(self):
        conditions = (evidence('readability_target', kind='OUTPUT_SPEC'),)
        partial = select_methods(self.context(conditions), self.registry)
        self.assertEqual(self.assessment(partial, 'K06').eligibility, 'CONDITIONAL')
        self.assertIn('copy_and_size_available', self.assessment(partial, 'K06').missing_conditions)
        result = select_methods(self.context(conditions + (evidence('copy_and_size_available', kind='OUTPUT_SPEC'),)), self.registry)
        self.assertEqual(self.assessment(result, 'K06').eligibility, 'ELIGIBLE')

    def test_explicit_false_and_operator_exclusions_are_traceable(self):
        context = self.context(component_conditions(), exclusions=(MethodExclusion('K01', '本图禁止局部特写',
                                                                                  ('slot-requirements#no-closeup',)),))
        result = select_methods(context, self.registry)
        row = self.assessment(result, 'K01')
        self.assertEqual(row.eligibility, 'EXCLUDED')
        self.assertEqual(row.exclusion, context.exclusions[0])
        self.assertIn('本图禁止局部特写', row.selection_reason)
        self.assertEqual(row.omission_reason, 'EXPLICIT_EXCLUSION')
        absent = list(component_conditions())
        absent[1] = evidence('product_detail_view', False, 'PRODUCT_MATERIAL')
        row = self.assessment(select_methods(self.context(tuple(absent)), self.registry), 'K01')
        self.assertEqual(row.eligibility, 'EXCLUDED')
        self.assertIn('product_detail_view', row.selection_reason)

    def test_unknown_is_not_false_and_no_slot_unconditionally_loads_all_cards(self):
        for slot in ('main', 'dimensions', 'comparison', 'selling_point', 'scene'):
            context = self.context((ConditionEvidence('product_detail_view', None),), slot_type=slot)
            result = select_methods(context, self.registry)
            self.assertEqual(result.selected, ())
            self.assertEqual({r.eligibility for r in result.not_selected}, {'CONDITIONAL'})

    def test_priority_budget_and_omissions_are_deterministic_not_business_limits(self):
        context = self.context(all_conditions())
        before = asdict(context)
        result = select_methods(context, self.registry)
        self.assertEqual([r.method_id for r in result.selected], ['K01', 'K02', 'K04'])
        self.assertEqual({r.eligibility for r in result.not_selected}, {'ELIGIBLE'})
        self.assertEqual({r.omission_reason for r in result.not_selected}, {'CANDIDATE_BUDGET'})
        self.assertEqual(select_methods(context, self.registry), result)
        self.assertEqual(asdict(context), before)
        order = ('K06', 'K05', 'K04', 'K03', 'K02', 'K01')
        changed = select_methods(context, self.registry, max_candidates=2, priority=order)
        self.assertEqual([r.method_id for r in changed.selected], ['K06', 'K05'])
        self.assertEqual(len(select_methods(context, self.registry, max_candidates=6).selected), 6)
        self.assertEqual(select_methods(context, self.registry, max_candidates=0).selected, ())

    def test_eligible_precedes_conditional_even_when_conditional_has_higher_priority(self):
        conditions = (component_conditions()[0], evidence('multiple_information_items'),
                      evidence('required_content_known', kind='OPERATOR_INPUT'))
        result = select_methods(self.context(conditions), self.registry, max_candidates=1)
        self.assertEqual([(r.method_id, r.eligibility) for r in result.selected], [('K05', 'ELIGIBLE')])
        row = self.assessment(result, 'K01')
        self.assertEqual((row.eligibility, row.omission_reason), ('CONDITIONAL', 'CANDIDATE_BUDGET'))

    def test_same_conditions_across_modes_do_not_change_permissions_or_require_planning(self):
        for mode, scenario in [('quick_redesign', 'quick_a'), ('quick_redesign', 'quick_b'), ('product_pack', None)]:
            context = self.context(component_conditions(), business_mode=mode, quick_scenario=scenario)
            result = select_methods(context, self.registry)
            self.assertEqual(result.context, context)
            self.assertEqual([(r.method_id, r.eligibility) for r in result.selected], [('K01', 'ELIGIBLE')])
            self.assertFalse(hasattr(result, 'plan'))
            self.assertFalse(hasattr(result, 'verified_claims'))

    def test_many_slots_do_not_share_conditions_or_selection_state(self):
        first = self.context(component_conditions(), output_intent='slot-01')
        original = select_methods(first, self.registry)
        for index in range(12):
            other = self.context((evidence('usage_scene_supported', False, reference=f'slot-{index}#restriction'),),
                                 slot_type='scene', output_intent=f'slot-{index + 2}')
            result = select_methods(other, self.registry)
            self.assertEqual(result.selected, ())
            self.assertEqual(self.assessment(result, 'K01').evidence_basis, ())
        self.assertEqual(select_methods(first, self.registry), original)

    def test_duplicate_contradictory_untyped_or_wrong_role_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            self.context((evidence('visible_component', kind='PRODUCT_MATERIAL'),
                          evidence('visible_component', False, 'PRODUCT_MATERIAL')))
        for args in [('visible_component', True, 'REFERENCE_IMAGE', ('ref#detail',)),
                     ('visible_component', True, 'PRODUCT_MATERIAL', ()),
                     ('unknown_condition', True, 'PRODUCT_MATERIAL', ('ref',)),
                     ('product_detail_view', 1, 'PRODUCT_MATERIAL', ('ref',)),
                     ('usage_scene_supported', True, None, ('ref',))]:
            with self.assertRaises(ValueError):
                ConditionEvidence(*args)
        for values in ([evidence('multiple_states_supported')], ({'multiple_states_supported': True},)):
            with self.assertRaises(ValueError):
                self.context(values)

    def test_invalid_context_priority_and_budget_are_rejected(self):
        for extra in [dict(business_mode='automatic'), dict(business_mode='quick_redesign'),
                      dict(quick_scenario='quick_a'), dict(slot_type='invented'), dict(output_intent=None)]:
            with self.assertRaises(ValueError):
                self.context(**extra)
        for budget in (-1, 7, True, '3'):
            with self.assertRaises(ValueError):
                select_methods(self.context(), self.registry, max_candidates=budget)
        for order in (('K01',), ('K01',) * 6, ('K01', 'K02', 'K03', 'K04', 'K05', '../file')):
            with self.assertRaises(ValueError):
                select_methods(self.context(), self.registry, priority=order)

    def test_selection_does_not_open_files_network_or_business_data(self):
        context = self.context(component_conditions())
        with patch.object(Path, 'open', side_effect=AssertionError('No file reads/writes')), \
                patch('builtins.open', side_effect=AssertionError('No business storage')), \
                patch('socket.socket.connect', side_effect=AssertionError('No network')):
            result = select_methods(context, self.registry)
            self.assertEqual([row.method_id for row in result.selected], ['K01'])

    def test_standalone_import_and_execution_cannot_load_sdk_or_other_workflows(self):
        code = '''
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        blocked = ('flask', 'openai', 'httpx', 'infrastructure', 'persistence',
                   'image_workflow.tasks', 'image_workflow.planning', 'image_workflow.generation',
                   'image_workflow.review', 'image_workflow.inspector')
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise AssertionError('Forbidden dependency: ' + fullname)
sys.meta_path.insert(0, Guard())
from image_workflow.knowledge import load_registry, MethodSelectionContext, select_methods
result = select_methods(MethodSelectionContext('product_pack', 'selling_point'), load_registry())
assert result.selected == ()
assert result.stage == 'METHOD_CANDIDATE_SELECTED'
'''
        result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
