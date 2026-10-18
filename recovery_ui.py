#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Visible recovery for an interrupted user install; never opens USB itself."""
import os
from pathlib import Path
import subprocess
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from i18n import _
from maintenance import Locations
from ui import label, style, ASSETS

BASE = Path(__file__).resolve().parent


class RecoveryDialog(Gtk.Dialog):
    def __init__(self, locations=None, operation=None):
        super().__init__(title=_('Recuperar Uplugo'), modal=True)
        style(self,'dualsense')
        self.locations=locations or Locations.current()
        self.operation=operation or self.repair
        self.running=False
        self.recovered=False
        self.can_open=False
        display=Gdk.Display.get_default();monitor=display.get_monitor(0)
        area=monitor.get_workarea() if monitor else None
        self.set_default_size(min(560,area.width-64) if area else 560,
                              min(500,area.height-80) if area else 500)
        self.add_button(_('Fechar'),Gtk.ResponseType.CANCEL)
        self.primary=self.add_button(_('Recuperar instalação'),Gtk.ResponseType.OK)
        style(self.primary,'primary')
        self.connect('delete-event',lambda *args:self.running)
        self.connect('response',self.guard_response)
        outer=self.get_content_area();outer.set_border_width(22)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14)
        content.set_valign(Gtk.Align.START)
        viewport=Gtk.ScrolledWindow();viewport.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        viewport.add(content);outer.pack_start(viewport,True,True,0)
        self.heading=label(_('A atualização precisa ser recuperada'),'controller-name',wrap=True)
        content.pack_start(self.heading,False,False,0)
        self.description=label(_('O processo de instalação foi interrompido. Vamos restaurar a versão anterior ou concluir a limpeza se a atualização já tiver terminado.'),wrap=True)
        content.pack_start(self.description,False,False,0)
        content.pack_start(label(_('Seus nomes, preferências, fotos e histórico serão preservados. Esta etapa não pede senha nem muda o acesso USB.'),'muted',wrap=True),False,False,0)
        self.status=label(_('Encerre o app pela bandeja, se ele ainda estiver aberto.'),wrap=True)
        content.pack_start(self.status,False,False,0)
        self.spinner=Gtk.Spinner();self.spinner.set_halign(Gtk.Align.START)
        content.pack_start(self.spinner,False,False,0)
        self.details=Gtk.Expander(label=_('Detalhes da recuperação'))
        self.details.set_no_show_all(True)
        self.error=label('', 'small',wrap=True);self.error.set_selectable(True)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(80);scroll.set_max_content_height(100);scroll.add(self.error)
        scroll.show_all();self.details.add(scroll)
        content.pack_start(self.details,True,True,0)

    def guard_response(self,dialog,response):
        if self.running:self.stop_emission_by_name('response')

    def repair(self):
        return subprocess.run(['/usr/bin/python3',str(BASE/'install.py'),'--recover'],
                              capture_output=True,text=True)

    def start(self):
        if self.running or self.recovered:return
        self.running=True;self.primary.set_sensitive(False)
        self.get_widget_for_response(Gtk.ResponseType.CANCEL).set_sensitive(False)
        self.details.hide();self.spinner.start()
        self.status.set_text(_('Recuperando os arquivos… Aguarde a conclusão.'))
        def worker():
            try:result=self.operation()
            except Exception as exc:result=subprocess.CompletedProcess([],1,'',str(exc))
            GLib.idle_add(self.completed,result)
        threading.Thread(target=worker,daemon=True).start()

    def completed(self,result):
        self.running=False;self.spinner.stop()
        self.get_widget_for_response(Gtk.ResponseType.CANCEL).set_sensitive(True)
        self.primary.set_sensitive(True)
        if result.returncode:
            self.status.set_text(_('A recuperação não foi concluída. Os arquivos de recuperação foram mantidos. Confira os detalhes e tente novamente.'))
            self.error.set_text((result.stderr or result.stdout or _('Nenhum detalhe foi informado.')).strip())
            self.details.show();self.details.set_expanded(True)
            self.primary.set_label(_('Tentar novamente'))
        else:
            self.recovered=True;self.can_open=(self.locations.app/'launch.py').is_file()
            self.set_title(_('Recuperação concluída'))
            if self.can_open:
                self.heading.set_text(_('Tudo pronto para abrir o app'))
                self.description.set_text(_('Abra o app para retomar o uso dos seus controles.'))
                self.status.set_text(_('Recuperação concluída. Você pode abrir o app.'))
                self.primary.set_label(_('Abrir app'))
            else:
                self.heading.set_text(_('Instalação inicial desfeita'))
                self.description.set_text(_('Execute novamente o instalador da pasta do download.'))
                self.status.set_text(_('A primeira instalação foi desfeita. Abra a pasta do download e execute o instalador novamente. Seus dados foram preservados.'))
                self.primary.hide()
        return False


def main():
    if os.geteuid()==0:raise SystemExit(_('Abra o app como seu usuário, sem sudo.'))

    from theme import install_theme
    install_theme()
    dialog=RecoveryDialog();dialog.show_all()
    launch=False
    try:
        while True:
            response=dialog.run()
            if response!=Gtk.ResponseType.OK:break
            if dialog.recovered:
                launch=dialog.can_open;break
            dialog.start()
    finally:dialog.destroy()
    if launch:
        path=Locations.current().app/'launch.py'
        # Recovery may restore an older release: start a fresh interpreter so
        # no already-imported code from the interrupted update is reused.
        os.execv('/usr/bin/python3',['/usr/bin/python3',str(path)])
    return 0


if __name__=='__main__':raise SystemExit(main())
