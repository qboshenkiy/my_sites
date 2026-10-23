package net.sbena.vano.remote;

import android.accessibilityservice.*;
import android.graphics.Path;
import android.os.Bundle;
import android.view.accessibility.*;
import android.util.DisplayMetrics;
import org.json.*;

public class ControlService extends AccessibilityService {
    static ControlService instance;
    @Override protected void onServiceConnected(){instance=this;}
    @Override public void onDestroy(){if(instance==this)instance=null;super.onDestroy();}
    @Override public void onAccessibilityEvent(AccessibilityEvent e){}
    @Override public void onInterrupt(){}
    static void control(JSONObject command){ControlService s=instance;if(s!=null&&ScreenService.active)s.getMainExecutor().execute(()->s.execute(command));}
    void execute(JSONObject v){
        if(!ScreenService.active||Link.current==null||!Link.current.ready)return;
        try{
            String type=v.getString("type");
            if(type.equals("gesture")){
                DisplayMetrics m=new DisplayMetrics();((android.view.WindowManager)getSystemService(WINDOW_SERVICE)).getDefaultDisplay().getRealMetrics(m);
                JSONArray start=v.getJSONArray("start"),end=v.getJSONArray("end");
                float x=(float)Math.max(0,Math.min(.999,start.getDouble(0)))*m.widthPixels,y=(float)Math.max(0,Math.min(.999,start.getDouble(1)))*m.heightPixels;
                float ex=(float)Math.max(0,Math.min(.999,end.getDouble(0)))*m.widthPixels,ey=(float)Math.max(0,Math.min(.999,end.getDouble(1)))*m.heightPixels;
                Path path=new Path();path.moveTo(x,y);if(Math.hypot(ex-x,ey-y)>8)path.lineTo(ex,ey);
                dispatchGesture(new GestureDescription.Builder().addStroke(new GestureDescription.StrokeDescription(path,0,Math.hypot(ex-x,ey-y)>8?350:80)).build(),null,null);
            }else if(type.equals("action")){
                String name=v.getString("name");if(name.equals("back"))performGlobalAction(GLOBAL_ACTION_BACK);else if(name.equals("home"))performGlobalAction(GLOBAL_ACTION_HOME);else if(name.equals("recents"))performGlobalAction(GLOBAL_ACTION_RECENTS);
            }else if(type.equals("text")){
                AccessibilityNodeInfo root=getRootInActiveWindow();if(root==null)return;AccessibilityNodeInfo focused=root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
                if(focused!=null&&focused.isEditable()){Bundle b=new Bundle();String value=v.getString("value");b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value.substring(0,Math.min(2000,value.length())));focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b);}
            }
        }catch(Exception ignored){}
    }
}
