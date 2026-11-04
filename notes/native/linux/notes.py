#!/usr/bin/env python3
"""Private Ubuntu client; note data and authentication stay on the HTTPS service."""
import gi
from pathlib import Path
from urllib.parse import urlsplit
import time
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,Gio,GLib
URL='https://notes.vano.sbena.net/'
class Notes(Gtk.Application):
    def __init__(self):super().__init__(application_id='net.sbena.vano.notes')
    def do_activate(self):
        if self.get_active_window():self.get_active_window().present();return
        window=Gtk.ApplicationWindow(application=self,title='Заметки · Место для мыслей');window.set_default_size(1280,840)
        icon=Path(__file__).with_name('icon.svg')
        if icon.exists():window.set_icon_from_file(str(icon))
        root=Path(GLib.get_user_data_dir())/'vano-notes';root.mkdir(parents=True,exist_ok=True,mode=0o700)
        manager=WebKit2.WebsiteDataManager(base_data_directory=str(root/'web'),base_cache_directory=str(root/'cache'))
        context=WebKit2.WebContext.new_with_website_data_manager(manager);context.get_cookie_manager().set_persistent_storage(str(root/'cookies.sqlite'),WebKit2.CookiePersistentStorage.SQLITE)
        web=WebKit2.WebView.new_with_context(context);web.get_settings().set_enable_javascript(True)
        def decide(view,decision,kind):
            if kind not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):return False
            uri=decision.get_request().get_uri();parts=urlsplit(uri)
            if parts.scheme=='https' and parts.netloc=='notes.vano.sbena.net':return False
            decision.ignore()
            if parts.scheme=='https':Gio.AppInfo.launch_default_for_uri(uri,None)
            return True
        web.connect('decide-policy',decide)
        def download_started(ctx,download):
            def destination(item,suggested):
                folder=Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or Path.home()/'Downloads');folder.mkdir(exist_ok=True)
                extension='.deb' if suggested.endswith('.deb') else '.json' if suggested.endswith('.json') else '.txt'
                item.set_destination((folder/('notes-'+str(time.time_ns())+extension)).as_uri());return True
            download.connect('decide-destination',destination)
        context.connect('download-started',download_started)
        closing=False
        def delete_event(win,event):
            nonlocal closing
            if closing:return False
            closing=True
            def checked(view,result):
                nonlocal closing
                try:unsaved=view.run_javascript_finish(result).get_js_value().to_boolean()
                except GLib.Error:unsaved=True
                if unsaved:
                    dialog=Gtk.MessageDialog(transient_for=window,modal=True,message_type=Gtk.MessageType.WARNING,buttons=Gtk.ButtonsType.NONE,text='Есть несохранённые изменения')
                    dialog.format_secondary_text('Вернитесь в заметку и дождитесь сохранения. Если сеть недоступна, скачайте свой текст перед закрытием.')
                    dialog.add_button('Остаться',Gtk.ResponseType.CANCEL);dialog.add_button('Закрыть без сохранения',Gtk.ResponseType.OK)
                    answer=dialog.run();dialog.destroy()
                    if answer!=Gtk.ResponseType.OK:closing=False;return
                window.destroy()
            web.run_javascript("document.body.dataset.unsaved === 'true'",None,checked)
            return True
        window.connect('delete-event',delete_event)
        window.add(web);window.show_all();web.load_uri(URL)
if __name__=='__main__':Notes().run()
