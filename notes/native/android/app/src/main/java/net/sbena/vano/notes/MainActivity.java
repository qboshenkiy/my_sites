package net.sbena.vano.notes;
import androidx.activity.ComponentActivity;
import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.ActivityNotFoundException;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.ValueCallback;
import android.provider.MediaStore;
import androidx.core.content.FileProvider;
import java.io.File;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class MainActivity extends ComponentActivity {
 private WebView web;
 private byte[] exportContent;
 private ValueCallback<Uri[]> photoCallback;
 private Uri cameraUri;
 private final ActivityResultLauncher<Intent> choosePhoto=registerForActivityResult(new ActivityResultContracts.StartActivityForResult(),result->{
  ValueCallback<Uri[]> callback=photoCallback;photoCallback=null;
  if(callback==null)return;
  Uri[] uris=null;
  if(result.getResultCode()==RESULT_OK){if(result.getData()!=null&&result.getData().getData()!=null)uris=new Uri[]{result.getData().getData()};else if(cameraUri!=null)uris=new Uri[]{cameraUri};}
  cameraUri=null;callback.onReceiveValue(uris);
 });
 private static final String URL="https://notes.vano.sbena.net/";
 private final ActivityResultLauncher<Intent> saveFile=registerForActivityResult(new ActivityResultContracts.StartActivityForResult(),result->{
  byte[] content=exportContent;exportContent=null;
  if(result.getResultCode()!=RESULT_OK||result.getData()==null||result.getData().getData()==null||content==null)return;
  try(OutputStream out=getContentResolver().openOutputStream(result.getData().getData())){if(out==null)throw new java.io.IOException();out.write(content);Toast.makeText(this,"Файл сохранён",Toast.LENGTH_SHORT).show();}
  catch(java.io.IOException error){Toast.makeText(this,"Не удалось сохранить файл. Повторите экспорт.",Toast.LENGTH_LONG).show();}
 });
 private boolean ownPage(){Uri u=Uri.parse(web.getUrl()==null?"":web.getUrl());return "https".equals(u.getScheme())&&"notes.vano.sbena.net".equals(u.getHost())&&u.getUserInfo()==null&&(u.getPort()==-1||u.getPort()==443);}
 public final class ExportBridge {
  @JavascriptInterface public void exportText(String filename,String content){
   if(filename==null||content==null||content.length()>5000000)return;
   runOnUiThread(()->{if(!ownPage()||exportContent!=null)return;String safe=filename.replaceAll("[^A-Za-z0-9._-]","_");if(safe.length()>120)safe="notes-export.txt";exportContent=content.getBytes(StandardCharsets.UTF_8);
    Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(safe.endsWith(".json")?"application/json":"text/plain").putExtra(Intent.EXTRA_TITLE,safe);
    try{saveFile.launch(intent);}catch(ActivityNotFoundException error){exportContent=null;Toast.makeText(MainActivity.this,"Не найдено приложение для сохранения файлов",Toast.LENGTH_LONG).show();}
   });
  }
 }
 @Override public void onCreate(Bundle state){super.onCreate(state);
  WindowCompat.setDecorFitsSystemWindows(getWindow(),false);
  WindowCompat.getInsetsController(getWindow(),getWindow().getDecorView()).setAppearanceLightStatusBars(true);
  WindowCompat.getInsetsController(getWindow(),getWindow().getDecorView()).setAppearanceLightNavigationBars(true);
  FrameLayout viewport=new FrameLayout(this);viewport.setBackgroundColor(Color.rgb(251,250,247));
  web=new WebView(this);viewport.addView(web,new FrameLayout.LayoutParams(-1,-1));
  ViewCompat.setOnApplyWindowInsetsListener(viewport,(view,insets)->{int types=WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout()|WindowInsetsCompat.Type.ime();Insets safe=insets.getInsets(types);view.setPadding(safe.left,safe.top,safe.right,safe.bottom);return new WindowInsetsCompat.Builder(insets).setInsets(types,Insets.NONE).build();});
  setContentView(viewport);ViewCompat.requestApplyInsets(viewport);
  WebSettings settings=web.getSettings();settings.setJavaScriptEnabled(true);settings.setDomStorageEnabled(true);settings.setAllowFileAccess(false);settings.setAllowContentAccess(true);settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);settings.setUserAgentString(settings.getUserAgentString()+" VanoNotes/1.1");
  CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);web.addJavascriptInterface(new ExportBridge(),"NotesAndroid");
  web.setWebViewClient(new WebViewClient(){@Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){Uri u=request.getUrl();if("https".equals(u.getScheme())&&"notes.vano.sbena.net".equals(u.getHost())&&u.getUserInfo()==null&&(u.getPort()==-1||u.getPort()==443))return false;
   if("https".equals(u.getScheme()))try{startActivity(new Intent(Intent.ACTION_VIEW,u));}catch(ActivityNotFoundException ignored){}return true;
  }});
  web.setWebChromeClient(new WebChromeClient(){
   @Override public boolean onShowFileChooser(WebView view,ValueCallback<Uri[]> callback,FileChooserParams params){
    if(!ownPage())return false;if(photoCallback!=null)photoCallback.onReceiveValue(null);photoCallback=callback;cameraUri=null;
    try{
     Intent intent;
     if(params.isCaptureEnabled()){
      File folder=new File(getCacheDir(),"photos");if(!folder.exists()&&!folder.mkdirs())throw new java.io.IOException();
      File file=File.createTempFile("photo-",".jpg",folder);cameraUri=FileProvider.getUriForFile(MainActivity.this,getPackageName()+".photos",file);
      intent=new Intent(MediaStore.ACTION_IMAGE_CAPTURE).putExtra(MediaStore.EXTRA_OUTPUT,cameraUri).addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_READ_URI_PERMISSION);
     }else intent=new Intent(Intent.ACTION_GET_CONTENT).addCategory(Intent.CATEGORY_OPENABLE).setType("image/*");
     choosePhoto.launch(intent);
    }catch(ActivityNotFoundException|java.io.IOException error){photoCallback=null;cameraUri=null;callback.onReceiveValue(null);Toast.makeText(MainActivity.this,"Не удалось открыть фото. Выбери снимок из галереи.",Toast.LENGTH_LONG).show();}
    return true;
   }
   @Override public boolean onJsConfirm(WebView view,String url,String text,android.webkit.JsResult result){new AlertDialog.Builder(MainActivity.this).setMessage(text).setPositiveButton("Да",(d,w)->result.confirm()).setNegativeButton("Отмена",(d,w)->result.cancel()).setOnCancelListener(d->result.cancel()).show();return true;}});
  getOnBackPressedDispatcher().addCallback(this,new OnBackPressedCallback(true){@Override public void handleOnBackPressed(){if(!ownPage()){finish();return;}web.evaluateJavascript("(()=>{const dialog=document.querySelector('dialog[open]');if(dialog){dialog.close();return true}const app=document.getElementById('app');if(app&&!app.hidden&&app.classList.contains('editing')){document.getElementById('back').click();return true}return false})()",handled->{if(!"true".equals(handled)){if(web.canGoBack())web.goBack();else finish();}});}});
  if(state==null)web.loadUrl(URL);else web.restoreState(state);
 }
 @Override protected void onPause(){if(web!=null&&ownPage()){web.evaluateJavascript("window.dispatchEvent(new Event('notes-save-now'))",null);CookieManager.getInstance().flush();}super.onPause();}
 @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);web.saveState(state);}
 @Override protected void onDestroy(){if(photoCallback!=null){photoCallback.onReceiveValue(null);photoCallback=null;}web.removeJavascriptInterface("NotesAndroid");web.destroy();super.onDestroy();}
}
