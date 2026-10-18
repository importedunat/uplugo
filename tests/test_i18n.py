# SPDX-License-Identifier: GPL-3.0-only
import ast
import json
import string
import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import i18n
from presentation import MODES, ControllerState


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('pt-BR')

    def test_catalogs_cover_each_other_and_preserve_format_fields(self):
        catalogs = [json.loads((i18n.CATALOG_DIR / (code+'.json')).read_text()) for code in ('en', 'es')]
        self.assertEqual(catalogs[0].keys(), catalogs[1].keys())
        def fields(text):
            return sorted((field, spec, conv or '') for _, field, spec, conv in string.Formatter().parse(text) if field is not None)
        for catalog in catalogs:
            for source, translated in catalog.items():
                self.assertTrue(translated)
                self.assertEqual(fields(source), fields(translated), source)
        # Every marked literal must exist in both bundled catalogs.
        for path in Path(__file__).resolve().parents[1].glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_' and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        self.assertIn(arg.value, catalogs[0], str(path)+': '+arg.value)

    def test_dynamic_states_and_modes_follow_language(self):
        state = ControllerState('sample', 'Meu controle', effective='charge', confirmed=True, fresh=True,
                                reading={'status':'Charging','capacity':55})
        for code, mode, battery in [('en','Charge only','Charging'), ('es','Solo cargar','Cargando'), ('pt-BR','Só carregar','Carregando')]:
            i18n.set_language(code)
            self.assertEqual(MODES['charge'][0], mode)
            self.assertEqual(state.battery_label, battery)
            self.assertEqual(state.name, 'Meu controle')
        i18n.set_language('../../unsupported')
        self.assertEqual(i18n.language(), 'pt-BR')
        self.assertEqual(i18n._('Unknown OS error'), 'Unknown OS error')

    def test_first_use_matches_supported_locale_and_falls_back_to_english(self):
        cases=[({'LANG':'pt_PT.UTF-8'},'pt-BR'),({'LANG':'es_MX.UTF-8'},'es'),
               ({'LANG':'en_GB.UTF-8'},'en'),({'LANG':'de_DE.UTF-8','LANGUAGE':'de:es:en'},'es'),
               ({'LANG':'es_ES.UTF-8','LC_ALL':'pt_BR.UTF-8'},'pt-BR'),
               ({'LANG':'en_US.UTF-8','LC_MESSAGES':'es_ES.UTF-8'},'es'),
               ({'LANG':'C.UTF-8'},'en'),({},'en')]
        for environment,expected in cases:
            with self.subTest(environment=environment):self.assertEqual(i18n.system_language(environment),expected)

    def test_saved_choice_wins_over_system_and_missing_or_invalid_config_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'dualsense-usb/controllers.json'
            with patch.dict(os.environ,{'XDG_CONFIG_HOME':directory,'LANGUAGE':'es'},clear=True):
                self.assertEqual(i18n.saved_language(),'es');self.assertFalse(path.exists())
                path.parent.mkdir();path.write_text('{"ui":{"language":"en"}}')
                self.assertEqual(i18n.saved_language(),'en')
                for content in ('[]','null','{"ui":null}','not json','{"ui":{"language":"invalid"}}'):
                    path.write_text(content)
                    self.assertEqual(i18n.saved_language(),'es')
                    self.assertEqual(path.read_text(),content)
