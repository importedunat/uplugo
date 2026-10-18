# SPDX-License-Identifier: GPL-3.0-only
import unittest
from presentation import ControllerState, confirmed_mode, mode_consequence


class ControllerSafetyTests(unittest.TestCase):
    def setUp(self):
        import i18n
        previous=i18n.language()
        i18n.set_language('pt-BR')
        self.addCleanup(i18n.set_language,previous)

    def test_charge_never_enables_effects(self):
        state=ControllerState('hid:sample','Controle',requested='charge',effective='charge',confirmed=True,fresh=True)
        self.assertFalse(state.can_customize)
        self.assertTrue(state.can_change)

    def test_selected_mode_is_not_confirmation(self):
        status={'mode':'charge','exclusive':True,'virtual_started':False}
        self.assertFalse(confirmed_mode('proxy',status,True,'managed'))
        self.assertFalse(confirmed_mode('proxy',{'mode':'proxy','exclusive':True},True,'managed'))
        self.assertTrue(confirmed_mode('proxy',dict(status,mode='proxy',virtual_started=True),True,'managed'))
        self.assertFalse(confirmed_mode('play',{},True,'direct',False))
        self.assertTrue(confirmed_mode('play',{},True,'direct',True))

    def test_stale_cached_battery_never_animates_as_charging(self):
        state=ControllerState('hid:sample','Controle',reading={'capacity':65,'status':'Charging','time':'20:00'},fresh=False)
        self.assertFalse(state.charging)
        self.assertIn('Última leitura',state.battery_label)
        self.assertFalse(state.can_customize)

    def test_unplug_and_transition_block_actions(self):
        state=ControllerState('hid:sample','Controle',effective='proxy',confirmed=True,fresh=True,transition=True)
        self.assertFalse(state.can_change)
        self.assertFalse(state.can_customize)
        state.transition=False;state.connected=False
        self.assertEqual(state.title,'Desconectado')
        self.assertFalse(state.can_change)

    def test_error_does_not_look_like_success(self):
        state=ControllerState('hid:sample','Controle',effective='proxy',confirmed=True,fresh=True,error='Falhou')
        self.assertEqual(state.title,'Precisa de atenção')
        self.assertFalse(state.can_customize)
        self.assertTrue(state.can_change)

    def test_native_game_exception_is_visible_before_apply(self):
        self.assertIn('Meu jogo',mode_consequence('charge','proxy','Meu jogo'))
        self.assertIn('pausadas',mode_consequence('proxy','play'))
        self.assertIn('sai dos jogos',mode_consequence('proxy','charge'))
