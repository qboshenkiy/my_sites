import copy
import importlib.util
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from register_gitdeck import add_project, PROJECT
path=Path(__file__).resolve().parents[2]/'deploy-panel'/'app.py'
spec=importlib.util.spec_from_file_location('panel_for_duty_tests',path)
panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)

class GitDeckTests(unittest.TestCase):
    def setUp(self):
        self.config={'state_dir':'/var/lib/gitdeck','port':8120,'custom':'preserved','projects':[dict(PROJECT,id='other',name='Other',directory='/opt/other',subdir='other')]}
    def test_registration_validates_and_preserves_other_projects(self):
        original=copy.deepcopy(self.config)
        projects,changed=add_project(panel,self.config)
        self.assertTrue(changed)
        self.assertEqual(projects[0],original['projects'][0])
        self.assertEqual(projects[1],PROJECT)
        self.assertEqual(self.config,original)
        panel.validate_config(dict(self.config,projects=projects))
    def test_second_registration_preserves_edited_name_and_branch(self):
        projects,_=add_project(panel,self.config)
        projects[-1]['name']='My team';projects[-1]['branch']='production'
        result,changed=add_project(panel,dict(self.config,projects=projects))
        self.assertFalse(changed);self.assertEqual(result[-1]['branch'],'production')
    def test_conflicting_id_or_directory_is_rejected(self):
        config=copy.deepcopy(self.config)
        config['projects'].append(dict(PROJECT,repo='https://github.com/example/other.git'))
        with self.assertRaises(ValueError):add_project(panel,config)
        config=copy.deepcopy(self.config);config['projects'][0]['directory']='/opt/milk-duty'
        with self.assertRaises(ValueError):add_project(panel,config)

if __name__=='__main__':unittest.main()
