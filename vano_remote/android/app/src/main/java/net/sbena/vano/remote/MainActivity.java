package net.sbena.vano.remote;

import android.app.*;
import android.os.*;
import android.content.*;
import android.graphics.*;
import android.hardware.biometrics.*;
import android.media.projection.MediaProjectionManager;
import android.security.keystore.*;
import android.provider.Settings;
import android.util.Base64;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import java.security.KeyStore;

public class MainActivity extends Activity implements Link.Listener {
    EditText code,text;
    TextView status;
    RemoteView screen;
    Link link;
    boolean authenticating=false, requestingProjection=false;
    CancellationSignal authCancel;
    static final String ALIAS="vano.remote.pairing.v1";
    @Override public void onCreate(Bundle b){
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(1);layout.setPadding(20,20,20,10);layout.setBackgroundColor(Color.rgb(16,24,39));
        TextView title=new TextView(this);title.setText("VANO / REMOTE");title.setTextSize(25);title.setTextColor(Color.rgb(99,234,210));layout.addView(title);
        status=new TextView(this);status.setTextColor(Color.WHITE);status.setText("Привяжите свой компьютер один раз. Каждый вход — по отпечатку.");layout.addView(status);
        code=new EditText(this);code.setTextColor(Color.WHITE);code.setHintTextColor(Color.LTGRAY);code.setHint("Вставьте секретный код из Windows");code.setMaxLines(3);code.setInputType(0x00080081);layout.addView(code);
        row(layout,new String[]{"Привязать","Войти • отпечаток","Отключить"},new Runnable[]{()->biometric(true),()->biometric(false),this::disconnect});
        row(layout,new String[]{"Передать экран","Разрешить управление"},new Runnable[]{this::share,()->startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))});
        screen=new RemoteView(this);layout.addView(screen,new LinearLayout.LayoutParams(-1,0,1));
        text=new EditText(this);text.setTextColor(Color.WHITE);text.setHintTextColor(Color.LTGRAY);text.setHint("Текст для компьютера");layout.addView(text);
        row(layout,new String[]{"Отправить","Enter","⌫","Esc"},new Runnable[]{()->{send("text","value",text.getText().toString());text.setText("");},()->send("key","name","enter"),()->send("key","name","backspace"),()->send("key","name","esc")});
        row(layout,new String[]{"ПК ↑","ПК ↓","Правый клик","Удалить привязку"},new Runnable[]{()->send("scroll","dy",3),()->send("scroll","dy",-3),()->screen.right=true,this::forget});
        setContentView(layout);
        if(Build.VERSION.SDK_INT>=33)requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},5);
    }
    void row(LinearLayout parent,String[] names,Runnable[] actions){LinearLayout r=new LinearLayout(this);for(int i=0;i<names.length;i++){Button b=new Button(this);b.setText(names[i]);b.setTextSize(11);final Runnable a=actions[i];b.setOnClickListener(v->a.run());r.addView(b,new LinearLayout.LayoutParams(0,-2,1));}parent.addView(r);}
    android.content.SharedPreferences prefs(){return getSharedPreferences("pairing",MODE_PRIVATE);}
    void biometric(boolean enroll){
        if(authenticating)return;
        try{
            if(((BiometricManager)getSystemService(BIOMETRIC_SERVICE)).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG)!=BiometricManager.BIOMETRIC_SUCCESS)throw new Exception("Настройте отпечаток в настройках телефона. Требуется сильная биометрия.");
            final String raw=code.getText().toString().trim();
            if(enroll){JSONObject p=new JSONObject(raw);if(!p.has("secret")||!p.has("room")||!p.has("server"))throw new Exception("Вставьте код из Windows");if(prefs().contains("value"))throw new Exception("Сначала удалите старую привязку");}
            else if(!prefs().contains("value"))throw new Exception("Сначала привяжите компьютер");
            KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
            if(!ks.containsAlias(ALIAS)){
                if(!enroll)throw new Exception("Ключ недоступен. Повторите привязку.");
                KeyGenerator g=KeyGenerator.getInstance("AES","AndroidKeyStore");
                g.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).setUserAuthenticationRequired(true).setUserAuthenticationParameters(0,KeyProperties.AUTH_BIOMETRIC_STRONG).setInvalidatedByBiometricEnrollment(true).build());g.generateKey();
            }
            Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
            if(enroll)cipher.init(Cipher.ENCRYPT_MODE,ks.getKey(ALIAS,null));
            else cipher.init(Cipher.DECRYPT_MODE,ks.getKey(ALIAS,null),new GCMParameterSpec(128,Base64.decode(prefs().getString("iv",""),Base64.NO_WRAP)));
            authenticating=true;authCancel=new CancellationSignal();
            new BiometricPrompt.Builder(this).setTitle(enroll?"Привязать компьютер":"Подключиться к компьютеру").setSubtitle("Vano Remote • разрешить использование ключа").setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG).setNegativeButton("Отмена",getMainExecutor(),(d,w)->{}).build().authenticate(new BiometricPrompt.CryptoObject(cipher),authCancel,getMainExecutor(),new BiometricPrompt.AuthenticationCallback(){
                @Override public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult result){authenticating=false;try{
                    Cipher c=result.getCryptoObject().getCipher();
                    if(enroll){byte[] encrypted=c.doFinal(Link.utf(raw));prefs().edit().putString("iv",Base64.encodeToString(c.getIV(),Base64.NO_WRAP)).putString("value",Base64.encodeToString(encrypted,Base64.NO_WRAP)).commit();code.setText("");status("Привязка сохранена. Нажмите «Войти • отпечаток».");}
                    else {byte[] plain=c.doFinal(Base64.decode(prefs().getString("value",""),Base64.NO_WRAP));try{disconnect();link=new Link(new JSONObject(new String(plain,java.nio.charset.StandardCharsets.UTF_8)),MainActivity.this);}finally{java.util.Arrays.fill(plain,(byte)0);}}
                }catch(Exception e){status("Ошибка ключа или кода. Повторите привязку.");}}
                @Override public void onAuthenticationError(int error,CharSequence message){authenticating=false;status(message.toString());}
            });
        }catch(Exception e){authenticating=false;status(e.getMessage()==null?"Ошибка биометрии":e.getMessage());}
    }
    void forget(){new AlertDialog.Builder(this).setMessage("Удалить привязку с телефона? Чтобы отозвать доступ полностью, нажмите «Отозвать телефон» также в Windows.").setPositiveButton("Удалить",(d,w)->{disconnect();prefs().edit().clear().commit();try{KeyStore k=KeyStore.getInstance("AndroidKeyStore");k.load(null);k.deleteEntry(ALIAS);}catch(Exception ignored){}status("Привязка удалена");}).setNegativeButton("Отмена",null).show();}
    void disconnect(){if(link!=null){link.close();link=null;}stopService(new Intent(this,ScreenService.class));if(screen!=null){screen.bitmap=null;screen.invalidate();}status("Отключено");}
    void send(String type,String field,Object value){try{if(link!=null)link.send(new JSONObject().put("type",type).put(field,value));}catch(Exception ignored){}}
    @Override public void status(String value){runOnUiThread(()->status.setText(value));}
    @Override public void ended(){runOnUiThread(this::disconnect);}
    @Override public void data(JSONObject v){
        try{String t=v.getString("type");if(t.equals("frame")){byte[] jpeg=Base64.decode(v.getString("jpeg"),Base64.NO_WRAP);Bitmap b=BitmapFactory.decodeByteArray(jpeg,0,jpeg.length);runOnUiThread(()->{screen.bitmap=b;screen.invalidate();});}else if(ScreenService.active){ControlService.control(v);}}catch(Exception ignored){}
    }
    void share(){if(link==null||!link.ready){status("Сначала подключитесь по отпечатку");return;}if(ScreenService.active){stopService(new Intent(this,ScreenService.class));return;}MediaProjectionManager m=(MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE);requestingProjection=true;startActivityForResult(m.createScreenCaptureIntent(),7);}
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request==7){requestingProjection=false;if(result==RESULT_OK&&link!=null&&link.ready){Intent i=new Intent(this,ScreenService.class).putExtra("result",result).putExtra("data",data);startForegroundService(i);}}}
    @Override protected void onStop(){super.onStop();if(authenticating&&authCancel!=null)authCancel.cancel();if(!ScreenService.active&&!requestingProjection)disconnect();}
    @Override protected void onDestroy(){if(authCancel!=null)authCancel.cancel();disconnect();super.onDestroy();}
    class RemoteView extends View {
        Bitmap bitmap;RectF rect=new RectF();boolean right=false;float downX,downY;boolean downValid=false;
        RemoteView(Context c){super(c);setBackgroundColor(Color.rgb(7,13,22));}
        @Override protected void onDraw(Canvas canvas){super.onDraw(canvas);if(bitmap!=null){float scale=Math.min((float)getWidth()/bitmap.getWidth(),(float)getHeight()/bitmap.getHeight());float w=bitmap.getWidth()*scale,h=bitmap.getHeight()*scale;rect.set((getWidth()-w)/2,(getHeight()-h)/2,(getWidth()+w)/2,(getHeight()+h)/2);canvas.drawBitmap(bitmap,null,rect,new Paint(Paint.FILTER_BITMAP_FLAG));}}
        @Override public boolean onTouchEvent(MotionEvent e){
            if(e.getAction()==MotionEvent.ACTION_DOWN){downValid=bitmap!=null&&rect.contains(e.getX(),e.getY());downX=e.getX();downY=e.getY();}
            if(e.getAction()==MotionEvent.ACTION_UP&&downValid&&bitmap!=null&&rect.contains(e.getX(),e.getY())){
                try{if(link!=null){boolean drag=Math.hypot(e.getX()-downX,e.getY()-downY)>14&&!right;link.send(new JSONObject().put("type",drag?"drag":"click").put("x",(downX-rect.left)/rect.width()).put("y",(downY-rect.top)/rect.height()).put("ex",(e.getX()-rect.left)/rect.width()).put("ey",(e.getY()-rect.top)/rect.height()).put("button",right?"right":"left"));}}catch(Exception ignored){}right=false;downValid=false;performClick();
            }return true;
        }
        @Override public boolean performClick(){super.performClick();return true;}
    }
}
