package net.sbena.updates;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.widget.Toast;
import androidx.core.content.FileProvider;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Native-only updater. Web pages cannot supply an APK or invoke installation. */
public final class AppUpdates {
    static final String FEED = "https://github.com/qboshenkiy/my_sites/releases/download/android-latest/updates.json";
    private final Activity activity;
    private final long installed;
    private boolean busy, awaitingPermission;
    private File pending;
    private JSONObject offer;
    public AppUpdates(Activity activity, long installed) { this.activity=activity;this.installed=installed; }
    public void check(boolean manual) {
        long now=System.currentTimeMillis();
        android.content.SharedPreferences preferences=activity.getSharedPreferences("app-updates",0);
        if(busy || (!manual && now-preferences.getLong("checked",0)<6*60*60*1000L)) return;
        busy=true;
        new Thread(()->{
            try {
                byte[] bytes=read(FEED+"?check="+now,128*1024,null);
                JSONObject candidate=new JSONObject(new String(bytes,StandardCharsets.UTF_8)).getJSONObject("apps").getJSONObject(activity.getPackageName());
                long version=candidate.getLong("versionCode");
                if(version<=installed) { ui(()->{if(manual)toast("Установлена последняя версия");}); }
                else {
                    if(!validAsset(candidate.getString("url")) || !candidate.getString("sha256").matches("[a-f0-9]{64}") || candidate.getLong("size")<1 || candidate.getLong("size")>50L*1024*1024) throw new IOException("Invalid release");
                    offer=candidate;
                    ui(()->new AlertDialog.Builder(activity).setTitle("Доступно обновление")
                        .setMessage("Версия "+candidate.optString("versionName")+". Скачать и установить? Ваши данные и вход сохранятся.")
                        .setPositiveButton("Обновить",(d,w)->download()).setNegativeButton("Позже",null).show());
                }
                preferences.edit().putLong("checked",now).apply();
            } catch(Exception error) { if(manual)ui(()->toast("Не удалось проверить обновления. Проверьте интернет или повторите позже.")); }
            finally { busy=false; }
        },"app-update-check").start();
    }
    public static boolean validAsset(String address) {
        try { URI u=new URI(address);return "https".equals(u.getScheme()) && "github.com".equals(u.getHost()) && u.getPort()==-1 && u.getUserInfo()==null && u.getRawQuery()==null && u.getFragment()==null && u.getRawPath().startsWith("/qboshenkiy/my_sites/releases/download/android-") && u.getRawPath().endsWith(".apk") && !u.getRawPath().contains(".."); }
        catch(Exception error){return false;}
    }
    private static boolean allowedDownload(URL url) {
        return "https".equals(url.getProtocol()) && url.getUserInfo()==null && (url.getPort()==-1||url.getPort()==443)
            && Arrays.asList("github.com","release-assets.githubusercontent.com","objects.githubusercontent.com").contains(url.getHost());
    }
    private static byte[] read(String address,long limit,File destination) throws Exception {
        URL url=new URL(address);
        for(int redirects=0;redirects<=5;redirects++) {
            if(!allowedDownload(url))throw new IOException("Untrusted download");
            HttpURLConnection connection=(HttpURLConnection)url.openConnection();
            connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(15000);connection.setReadTimeout(30000);
            connection.setRequestProperty("Cache-Control","no-cache");
            try {
                int status=connection.getResponseCode();
                if(status==301||status==302||status==303||status==307||status==308){url=new URL(url,connection.getHeaderField("Location"));continue;}
                if(status!=200 || connection.getContentLengthLong()>limit)throw new IOException("Download unavailable");
                ByteArrayOutputStream memory=destination==null?new ByteArrayOutputStream():null;
                try(InputStream input=connection.getInputStream();OutputStream output=destination==null?memory:new FileOutputStream(destination)) {
                    byte[] buffer=new byte[8192];int n;long total=0;
                    while((n=input.read(buffer))!=-1){total+=n;if(total>limit)throw new IOException("Download too large");output.write(buffer,0,n);}
                }
                return memory==null?new byte[0]:memory.toByteArray();
            } finally {connection.disconnect();}
        }
        throw new IOException("Too many redirects");
    }
    private void download() {
        if(busy)return;busy=true;toast("Скачиваем обновление…");
        new Thread(()->{
            File file=new File(activity.getCacheDir(),"updates/update.apk");
            try {
                if(!file.getParentFile().isDirectory()&&!file.getParentFile().mkdirs())throw new IOException("No cache");
                read(offer.getString("url"),50L*1024*1024,file);
                if(file.length()!=offer.getLong("size"))throw new IOException("Incomplete update");
                MessageDigest digest=MessageDigest.getInstance("SHA-256");
                try(InputStream input=new FileInputStream(file)){byte[] buffer=new byte[8192];int n;while((n=input.read(buffer))!=-1)digest.update(buffer,0,n);}
                StringBuilder hash=new StringBuilder();for(byte b:digest.digest())hash.append(String.format(Locale.ROOT,"%02x",b&255));
                if(!hash.toString().equals(offer.getString("sha256")))throw new IOException("Checksum mismatch");
                validatePackage(file,offer.getLong("versionCode"));
                pending=file;ui(this::install);
            } catch(Exception error){file.delete();ui(()->toast("Обновление не установлено: файл недоступен или не прошёл проверку. Повторите позже."));}
            finally{busy=false;}
        },"app-update-download").start();
    }
    @SuppressWarnings("deprecation") private void validatePackage(File file,long expected) throws Exception {
        PackageManager manager=activity.getPackageManager();
        int flags=Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES;
        PackageInfo next=manager.getPackageArchiveInfo(file.getAbsolutePath(),flags),current=manager.getPackageInfo(activity.getPackageName(),flags);
        if(next==null || !activity.getPackageName().equals(next.packageName))throw new IOException("Wrong application");
        long code=Build.VERSION.SDK_INT>=28?next.getLongVersionCode():next.versionCode;
        if(code!=expected || code<=installed)throw new IOException("Wrong version");
        Signature[] a=Build.VERSION.SDK_INT>=28?next.signingInfo.getApkContentsSigners():next.signatures;
        Signature[] b=Build.VERSION.SDK_INT>=28?current.signingInfo.getApkContentsSigners():current.signatures;
        if(a==null||b==null||a.length==0||!new HashSet<>(Arrays.asList(a)).equals(new HashSet<>(Arrays.asList(b))))throw new IOException("Wrong signing key");
    }
    private void install() {
        if(pending==null||!pending.isFile())return;
        try {
            validatePackage(pending,offer.getLong("versionCode"));
            if(Build.VERSION.SDK_INT>=26&&!activity.getPackageManager().canRequestPackageInstalls()) {
                new AlertDialog.Builder(activity).setTitle("Разрешите обновления")
                    .setMessage("Android попросит разрешить установку из этого приложения. После разрешения вернитесь сюда — откроется установка обновления.")
                    .setPositiveButton("Открыть настройки",(d,w)->{awaitingPermission=true;activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+activity.getPackageName())));})
                    .setNegativeButton("Позже",null).show();return;
            }
            Uri uri=FileProvider.getUriForFile(activity,activity.getPackageName()+".updates",pending);
            activity.startActivity(new Intent(Intent.ACTION_VIEW).setDataAndType(uri,"application/vnd.android.package-archive").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));
            pending=null;
        } catch(Exception error){toast("Не удалось открыть установку обновления");}
    }
    public void resume() {if(awaitingPermission){awaitingPermission=false;if(Build.VERSION.SDK_INT<26||activity.getPackageManager().canRequestPackageInstalls())install();}else check(false);}
    private void ui(Runnable action){activity.runOnUiThread(()->{if(!activity.isFinishing()&&!activity.isDestroyed())action.run();});}
    private void toast(String text){Toast.makeText(activity,text,Toast.LENGTH_LONG).show();}
}
