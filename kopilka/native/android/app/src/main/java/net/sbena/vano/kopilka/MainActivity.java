package net.sbena.vano.kopilka;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.Intent;
import android.content.ActivityNotFoundException;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
public class MainActivity extends Activity {
 private WebView web;
 private static final String URL="https://finance.vano.sbena.net/";
 @Override public void onCreate(Bundle state){super.onCreate(state);web=new WebView(this);setContentView(web);WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
 web.setWebViewClient(new WebViewClient(){@Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){Uri u=r.getUrl();if("https".equals(u.getScheme())&&"finance.vano.sbena.net".equals(u.getHost())&&u.getPort()==-1&&u.getUserInfo()==null)return false;if("https".equals(u.getScheme()))try{startActivity(new Intent(Intent.ACTION_VIEW,u));}catch(ActivityNotFoundException ignored){}return true;}});
 web.setWebChromeClient(new WebChromeClient(){@Override public boolean onJsConfirm(WebView v,String url,String message,android.webkit.JsResult result){new AlertDialog.Builder(MainActivity.this).setMessage(message).setPositiveButton("Да",(d,w)->result.confirm()).setNegativeButton("Отмена",(d,w)->result.cancel()).setOnCancelListener(d->result.cancel()).show();return true;}});
 web.setDownloadListener((url,agent,disposition,mime,length)->{Uri u=Uri.parse(url);if(!"https".equals(u.getScheme())||!"finance.vano.sbena.net".equals(u.getHost())||!"/api/export".equals(u.getPath()))return;DownloadManager.Request req=new DownloadManager.Request(u);req.addRequestHeader("Cookie",CookieManager.getInstance().getCookie(URL));req.setTitle("Резервная копия Копилки");req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,"kopilka-"+System.currentTimeMillis()+".json");req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);((DownloadManager)getSystemService(DOWNLOAD_SERVICE)).enqueue(req);Toast.makeText(this,"Копия скачивается в Загрузки",Toast.LENGTH_LONG).show();});
 if(state==null)web.loadUrl(URL);else web.restoreState(state);
 }
 @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);web.saveState(state);}
 @SuppressWarnings("deprecation") @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
 @Override protected void onDestroy(){web.destroy();super.onDestroy();}
}
