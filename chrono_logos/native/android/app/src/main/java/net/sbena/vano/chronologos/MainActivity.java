package net.sbena.vano.chronologos;

import androidx.activity.ComponentActivity;
import androidx.activity.OnBackPressedCallback;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.os.Message;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.SslErrorHandler;
import android.webkit.URLUtil;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends ComponentActivity {
    private net.sbena.updates.AppUpdates updates;
    private WebView web;
    private ProgressBar progress;
    private LinearLayout errorPanel;
    private TextView errorText;
    private NavigationPolicy policy;
    private String downloadUrl;
    private static final int SAVE_REPORT = 41;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        updates = new net.sbena.updates.AppUpdates(this, BuildConfig.VERSION_CODE);
        policy = new NavigationPolicy(BuildConfig.GAME_URL);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(16,27,33));
        if (Build.VERSION.SDK_INT >= 30) getWindow().setDecorFitsSystemWindows(false);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets area = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
                view.setPadding(area.left,area.top,area.right,area.bottom);
            } else view.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());
            return insets;
        });
        progress = new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);
        root.addView(progress,new LinearLayout.LayoutParams(-1,dp(3)));
        FrameLayout content = new FrameLayout(this);
        root.addView(content,new LinearLayout.LayoutParams(-1,0,1));
        web = new WebView(this);
        content.addView(web,new FrameLayout.LayoutParams(-1,-1));
        errorPanel = new LinearLayout(this);
        errorPanel.setOrientation(LinearLayout.VERTICAL);
        errorPanel.setGravity(Gravity.CENTER);
        errorPanel.setPadding(dp(28),dp(24),dp(28),dp(24));
        errorPanel.setBackgroundColor(Color.rgb(16,27,33));
        errorText = new TextView(this);
        errorText.setTextSize(18);
        errorText.setTextColor(Color.rgb(245,242,233));
        errorText.setGravity(Gravity.CENTER);
        errorPanel.addView(errorText);
        Button retry = new Button(this);
        retry.setText("Повторить подключение");
        retry.setOnClickListener(view -> web.loadUrl(BuildConfig.GAME_URL));
        errorPanel.addView(retry);
        Button checkUpdates = new Button(this);
        checkUpdates.setText("Проверить обновления приложения");
        checkUpdates.setOnClickListener(view -> updates.check(true));
        errorPanel.addView(checkUpdates);
        errorPanel.setVisibility(View.GONE);
        content.addView(errorPanel,new FrameLayout.LayoutParams(-1,-1));
        setContentView(root);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setUserAgentString(settings.getUserAgentString()+" ChronoLogos/1.0");
        if (Build.VERSION.SDK_INT >= 26) settings.setSafeBrowsingEnabled(true);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (policy.internal(url)) return false;
                if (request.isForMainFrame() && request.hasGesture()) openExternal(url);
                return true;
            }
            @Override public void onPageStarted(WebView view,String url,android.graphics.Bitmap icon) {
                errorPanel.setVisibility(View.GONE);progress.setVisibility(View.VISIBLE);
            }
            @Override public void onPageFinished(WebView view,String url) {
                progress.setVisibility(View.GONE);CookieManager.getInstance().flush();
            }
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error) {
                if (request.isForMainFrame()) {
                    String reason;
                    switch (error.getErrorCode()) {
                        case ERROR_HOST_LOOKUP: reason = "Не удалось найти адрес сайта. Проверьте интернет и доменное имя."; break;
                        case ERROR_CONNECT: reason = "Сервер не принимает подключение. Проверьте адрес и порт сайта."; break;
                        case ERROR_TIMEOUT: reason = "Сервер не ответил вовремя. Повторите попытку."; break;
                        default: reason = "Не удалось подключиться к Chrono Logos. Проверьте интернет и доступность сайта.";
                    }
                    showError(reason);
                }
            }
            @Override public void onReceivedHttpError(WebView view,WebResourceRequest request,WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 400) showError("Сайт Chrono Logos временно недоступен. Попробуйте ещё раз позже.");
            }
            @Override public void onReceivedSslError(WebView view,SslErrorHandler handler,SslError error) {
                handler.cancel();
                if (policy.internal(error.getUrl())) showError("Защищённое подключение к Chrono Logos пока не настроено. Нужен действующий HTTPS-сертификат.");
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view,int value) { progress.setProgress(value); }
            @Override public boolean onCreateWindow(WebView view,boolean dialog,boolean userGesture,Message result) {
                if (!userGesture) return false;
                WebView popup = new WebView(MainActivity.this);
                popup.setWebViewClient(new WebViewClient() {
                    @Override public boolean shouldOverrideUrlLoading(WebView child,WebResourceRequest request) {
                        String url = request.getUrl().toString();
                        if (policy.internal(url)) web.loadUrl(url);else openExternal(url);
                        child.post(child::destroy);return true;
                    }
                });
                ((WebView.WebViewTransport)result.obj).setWebView(popup);result.sendToTarget();return true;
            }
        });
        web.setDownloadListener((url,agent,disposition,mime,length) -> {
            if (!policy.internal(url)) return;
            downloadUrl = url;
            Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE);
            save.setType(mime == null ? "application/octet-stream" : mime);
            save.putExtra(Intent.EXTRA_TITLE,URLUtil.guessFileName(url,disposition,mime));
            try { startActivityForResult(save,SAVE_REPORT); }
            catch (ActivityNotFoundException error) { Toast.makeText(this,"На телефоне недоступно сохранение файлов",Toast.LENGTH_LONG).show(); }
        });
        if (state != null) downloadUrl = state.getString("downloadUrl");
        if (state == null || web.restoreState(state) == null) web.loadUrl(BuildConfig.GAME_URL);
        getOnBackPressedDispatcher().addCallback(this,new OnBackPressedCallback(true) {
            @Override public void handleOnBackPressed() { goBack(); }
        });
    }
    private int dp(int value) { return Math.round(value*getResources().getDisplayMetrics().density); }
    private void showError(String message) { progress.setVisibility(View.GONE);errorText.setText(message + "\n\n" + BuildConfig.GAME_URL);errorPanel.setVisibility(View.VISIBLE); }
    private void openExternal(String url) {
        if (!policy.external(url)) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url))); }
        catch (ActivityNotFoundException error) { Toast.makeText(this,"Приложение для этой ссылки не найдено",Toast.LENGTH_LONG).show(); }
    }
    private void goBack() {
        if (errorPanel.getVisibility() == View.VISIBLE) { finish();return; }
        web.evaluateJavascript("(()=>{const d=document.querySelector('dialog[open]');if(d){d.close();return true;}const m=document.getElementById('card-modal');if(m&&!m.hidden){document.querySelector('.modal-close')?.click();return true;}const menu=document.getElementById('game-menu');if(menu&&!menu.hidden){document.getElementById('menu-close')?.click();return true;}return false;})()",handled->{if(!"true".equals(handled)){if(web.canGoBack())web.goBack();else finish();}});
    }
    @Override protected void onSaveInstanceState(Bundle state) { super.onSaveInstanceState(state);web.saveState(state);state.putString("downloadUrl",downloadUrl); }
    @Override protected void onPause() { CookieManager.getInstance().flush();web.onPause();super.onPause(); }
    @Override protected void onResume() { super.onResume();if(web!=null)web.onResume();if(updates!=null)updates.resume(); }
    @Override protected void onDestroy() { web.destroy();super.onDestroy(); }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if (request != SAVE_REPORT || result != RESULT_OK || data == null || data.getData() == null || downloadUrl == null) return;
        String url = downloadUrl;downloadUrl = null;
        if (!policy.internal(url)) return;
        Uri destination = data.getData();String cookie = CookieManager.getInstance().getCookie(url);
        new Thread(() -> {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection)new URL(url).openConnection();
                connection.setConnectTimeout(15000);connection.setReadTimeout(30000);connection.setInstanceFollowRedirects(false);
                if (cookie != null) connection.setRequestProperty("Cookie",cookie);
                if (connection.getResponseCode() != 200) throw new java.io.IOException("Download rejected");
                try (InputStream input=connection.getInputStream();OutputStream output=getContentResolver().openOutputStream(destination,"w")) {
                    if(output==null)throw new java.io.IOException("No destination");
                    byte[] bytes=new byte[8192];int read;long total=0;
                    while((read=input.read(bytes))!=-1){total+=read;if(total>25L*1024*1024)throw new java.io.IOException("File too large");output.write(bytes,0,read);}
                }
                runOnUiThread(()->Toast.makeText(this,"Отчёт сохранён",Toast.LENGTH_LONG).show());
            } catch(Exception error) { runOnUiThread(()->Toast.makeText(this,"Не удалось сохранить отчёт. Повторите попытку.",Toast.LENGTH_LONG).show()); }
            finally { if(connection!=null)connection.disconnect(); }
        },"marathon-report").start();
    }
}
