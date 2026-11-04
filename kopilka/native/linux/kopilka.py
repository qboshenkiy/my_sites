#!/usr/bin/env python3
"""Thin GTK client. Accounting stays on the private HTTPS server."""
import gi
from pathlib import Path
from urllib.parse import urlsplit
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,Gio,GLib
APP_ID='net.sbena.vano.kopilka'
GLib.set_prgname(APP_ID)
GLib.set_application_name('Копилка')
Gtk.Window.set_default_icon_name(APP_ID)
class Kopilka(Gtk.Application):
    def __init__(self):super().__init__(application_id=APP_ID)
    def do_activate(self):
        if self.get_active_window():self.get_active_window().present();return
        window=Gtk.ApplicationWindow(application=self,title='Копилка · Личные финансы');window.set_default_size(1180,820);window.set_icon_name(APP_ID)
        root=Path(GLib.get_user_data_dir())/'kopilka';root.mkdir(parents=True,exist_ok=True,mode=0o700)
        manager=WebKit2.WebsiteDataManager(base_data_directory=str(root/'web'),base_cache_directory=str(root/'cache'))
        context=WebKit2.WebContext.new_with_website_data_manager(manager);cookies=context.get_cookie_manager();cookies.set_persistent_storage(str(root/'cookies.sqlite'),WebKit2.CookiePersistentStorage.SQLITE)
        web=WebKit2.WebView.new_with_context(context);web.get_settings().set_enable_javascript(True)
        def decide(view,decision,kind):
            if kind not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):return False
            url=decision.get_request().get_uri();parts=urlsplit(url)
            if parts.scheme=='https' and parts.netloc=='finance.vano.sbena.net':return False
            decision.ignore()
            if parts.scheme=='https':Gio.AppInfo.launch_default_for_uri(url,None)
            return True
        web.connect('decide-policy',decide)
        def download_started(ctx,download):
            def destination(item,suggested):
                folder=Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or Path.home()/'Downloads');folder.mkdir(exist_ok=True)
                import time
                item.set_destination((folder/('kopilka-'+str(time.time_ns())+'.json')).as_uri());return True
            download.connect('decide-destination',destination)
        context.connect('download-started',download_started)
        window.add(web);window.show_all();web.load_uri('https://finance.vano.sbena.net/')
if __name__=='__main__':Kopilka().run()
