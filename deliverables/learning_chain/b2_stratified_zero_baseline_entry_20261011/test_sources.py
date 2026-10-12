"""The new entry must include inherited native files and its own controls."""
from pathlib import Path
import sys
import unittest

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import scope_contract as c
import prepare_entry as p


class SourceTests(unittest.TestCase):
    def api(self,name):
        self.assertTrue(callable(getattr(p,name,None)),'Missing behavior: '+name)
        return getattr(p,name)

    def test_inherited_numerical_files_and_new_execution_controls_bound(self):
        binding=self.api('build_binding')()
        old=c.read(c.OLD/'source_binding.json')
        self.assertTrue(all(binding['files'].get(path)==pin for path,pin in old['files'].items()))
        for name in ['baseline_entry.py','baseline_rollout.py','scope_contract.py','assess_results.py','model.xml','case_registry.json','configuration.json']:
            self.assertIn(str(OUT/name),binding['files'])
        self.assertEqual(binding['executable'],old['executable'])
        self.assertEqual(binding['numerical_runtime'],old['numerical_runtime'])

    def test_preceding_delivery_sources_sealed_and_current_docs_not_frozen(self):
        binding=self.api('build_binding')()
        self.assertIn(str(c.SCOPE/'delivery_manifest.json'),binding['files'])
        self.assertIn(str(c.PREV/'delivery_manifest.json'),binding['files'])
        self.assertNotIn(str(c.ROOT/'项目进度跟踪.md'),binding['files'])
        self.assertFalse(binding['scientific_execution_admitted']);self.assertFalse(binding['training_admitted'])

    def test_no_learning_runtime_import_during_binding(self):
        self.api('build_binding')()
        self.assertFalse(any(n.split('.')[0] in {'numpy','mujoco','torch','gymnasium','stable_baselines3'} for n in sys.modules))


if __name__=='__main__':unittest.main(verbosity=2)
