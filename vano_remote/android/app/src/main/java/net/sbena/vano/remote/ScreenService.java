package net.sbena.vano.remote;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.hardware.display.*;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.*;
import android.os.*;
import android.util.*;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import org.json.JSONObject;

public class ScreenService extends Service {
    static volatile boolean active=false;
    MediaProjection projection;
    VirtualDisplay display;
    ImageReader reader;
    HandlerThread worker;
    long last=0;
    @Override public int onStartCommand(Intent intent,int flags,int id){
        if(intent==null||"STOP".equals(intent.getAction())){stopSelf();return START_NOT_STICKY;}
        if(active)return START_NOT_STICKY;
        NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        n.createNotificationChannel(new NotificationChannel("screen","Удалённый доступ",NotificationManager.IMPORTANCE_LOW));
        PendingIntent stop=PendingIntent.getService(this,0,new Intent(this,ScreenService.class).setAction("STOP"),PendingIntent.FLAG_IMMUTABLE);
        PendingIntent open=PendingIntent.getActivity(this,1,new Intent(this,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),PendingIntent.FLAG_IMMUTABLE);
        startForeground(1,new Notification.Builder(this,"screen").setSmallIcon(android.R.drawable.ic_menu_view).setContentTitle("Vano Remote: экран доступен компьютеру").setContentText("Нажмите «Остановить», чтобы прекратить просмотр и управление").setContentIntent(open).setOngoing(true).addAction(new Notification.Action.Builder(null,"Остановить",stop).build()).build());
        try{
            Link link=Link.current;if(link==null||!link.ready)throw new Exception("No session");
            Intent permission=intent.getParcelableExtra("data");
            projection=((MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE)).getMediaProjection(intent.getIntExtra("result",0),permission);
            worker=new HandlerThread("VanoCapture");worker.start();Handler handler=new Handler(worker.getLooper());
            projection.registerCallback(new MediaProjection.Callback(){@Override public void onStop(){stopSelf();}},handler);
            DisplayMetrics metrics=new DisplayMetrics();((android.view.WindowManager)getSystemService(WINDOW_SERVICE)).getDefaultDisplay().getRealMetrics(metrics);
            float scale=Math.min(1f,Math.min(640f/metrics.widthPixels,1280f/metrics.heightPixels));
            int w=Math.max(2,(int)(metrics.widthPixels*scale)),h=Math.max(2,(int)(metrics.heightPixels*scale));
            reader=ImageReader.newInstance(w,h,PixelFormat.RGBA_8888,2);
            active=true;
            reader.setOnImageAvailableListener(r->{
                try(Image image=r.acquireLatestImage()){
                    if(image==null)return;
                    Link connection=Link.current;
                    if(connection==null||!connection.ready){stopSelf();return;}
                    long now=SystemClock.elapsedRealtime();if(now-last<300)return;last=now;
                    Image.Plane plane=image.getPlanes()[0];ByteBuffer buffer=plane.getBuffer();int stride=plane.getPixelStride();int padding=plane.getRowStride()-stride*w;
                    Bitmap padded=Bitmap.createBitmap(w+padding/stride,h,Bitmap.Config.ARGB_8888);padded.copyPixelsFromBuffer(buffer);
                    Bitmap cropped=Bitmap.createBitmap(padded,0,0,w,h);ByteArrayOutputStream output=new ByteArrayOutputStream();cropped.compress(Bitmap.CompressFormat.JPEG,55,output);
                    connection.send(new JSONObject().put("type","frame").put("jpeg",Base64.encodeToString(output.toByteArray(),Base64.NO_WRAP)));
                    if(cropped!=padded)cropped.recycle();padded.recycle();
                }catch(Exception e){stopSelf();}
            },handler);
            display=projection.createVirtualDisplay("VanoRemote",w,h,metrics.densityDpi,DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,reader.getSurface(),null,handler);
        }catch(Exception e){stopSelf();}
        return START_NOT_STICKY;
    }
    @Override public void onDestroy(){
        active=false;
        try{if(display!=null)display.release();if(reader!=null)reader.close();if(projection!=null)projection.stop();if(worker!=null)worker.quitSafely();Link l=Link.current;if(l!=null)l.send(new JSONObject().put("type","sharing_stopped"));}catch(Exception ignored){}
        stopForeground(STOP_FOREGROUND_REMOVE);super.onDestroy();
    }
    @Override public IBinder onBind(Intent i){return null;}
}
