package net.sbena.vano.remote;

import android.util.Base64;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.concurrent.TimeUnit;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import okhttp3.*;
import okio.ByteString;

final class Link extends WebSocketListener {
    interface Listener { void status(String s); void data(JSONObject v); void ended(); }
    static volatile Link current;
    final Listener listener;
    final byte[] base;
    byte[] local, key;
    long sent=0, received=0;
    volatile boolean ready=false, closed=false;
    WebSocket socket;
    final OkHttpClient client=new OkHttpClient.Builder().pingInterval(20,TimeUnit.SECONDS).build();
    static byte[] hash(byte[] b) throws Exception { return MessageDigest.getInstance("SHA-256").digest(b); }
    static byte[] utf(String s) { return s.getBytes(StandardCharsets.UTF_8); }
    static String hex(byte[] b) { StringBuilder s=new StringBuilder(); for(byte x:b)s.append(String.format("%02x",x&255)); return s.toString(); }
    static byte[] unhex(String s) throws Exception { if(!s.matches("[a-f0-9]{64}"))throw new Exception("Challenge");byte[] b=new byte[32];for(int i=0;i<32;i++)b[i]=(byte)Integer.parseInt(s.substring(i*2,i*2+2),16);return b; }
    static byte[] concat(byte[]... arrays) { int n=0;for(byte[] a:arrays)n+=a.length;byte[] b=new byte[n];int p=0;for(byte[] a:arrays){System.arraycopy(a,0,b,p,a.length);p+=a.length;}return b; }
    Link(JSONObject pairing,Listener listener) throws Exception {
        this.listener=listener;
        String server=pairing.getString("server");
        java.net.URI uri=new java.net.URI(server);
        if(!"wss".equals(uri.getScheme()) || uri.getHost()==null || uri.getUserInfo()!=null || uri.getQuery()!=null || uri.getFragment()!=null || !(uri.getPath().isEmpty()||uri.getPath().equals("/")))throw new Exception("Нужен адрес wss://домен");
        String room=pairing.getString("room"), secret=pairing.getString("secret");
        if(!room.matches("[a-f0-9]{32}") || secret.length()<40)throw new Exception("Неверный код привязки");
        base=hash(utf("e2e:"+secret));
        Request request=new Request.Builder().url(server.replaceAll("/$","")+"/ws/"+room+"/android").header("Authorization","Bearer "+hex(hash(utf("auth:"+secret)))).build();
        current=this;
        socket=client.newWebSocket(request,this);
    }
    static byte[] seal(byte[] k,JSONObject value) throws Exception {
        byte[] iv=new byte[12];new SecureRandom().nextBytes(iv);
        Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,new SecretKeySpec(k,"AES"),new GCMParameterSpec(128,iv));c.updateAAD(utf("vano1"));
        return concat(iv,c.doFinal(utf(value.toString())));
    }
    static JSONObject open(byte[] k,byte[] packet) throws Exception {
        if(packet.length<28 || packet.length>4000000)throw new Exception("Packet size");
        Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,new SecretKeySpec(k,"AES"),new GCMParameterSpec(128,packet,0,12));c.updateAAD(utf("vano1"));
        return new JSONObject(new String(c.doFinal(packet,12,packet.length-12),StandardCharsets.UTF_8));
    }
    @Override public void onOpen(WebSocket ws,Response response) {listener.status("Ожидаю компьютер…");}
    @Override public synchronized void onMessage(WebSocket ws,String text) {
        if(closed)return;
        try {
            if(new JSONObject(text).optString("event").equals("paired")) {
                if(local!=null)throw new Exception("Повторное рукопожатие");
                local=new byte[32];new SecureRandom().nextBytes(local);
                ws.send(ByteString.of(seal(base,new JSONObject().put("type","hello").put("role","android").put("nonce",hex(local)))));
            }
        } catch(Exception e){ fail("Ошибка соединения"); }
    }
    @Override public synchronized void onMessage(WebSocket ws,ByteString bytes) {
        if(closed)return;
        try {
            if(local==null)throw new Exception("Handshake missing");
            if(key==null) {
                JSONObject v=open(base,bytes.toByteArray());
                if(!v.getString("type").equals("hello") || !v.getString("role").equals("windows"))throw new Exception("Handshake role");
                key=hash(concat(base,unhex(v.getString("nonce")),local));ready=true;
                listener.status("Компьютер подключён • нажимайте на экран");
            } else {
                JSONObject v=open(key,bytes.toByteArray());
                if(!v.getString("role").equals("windows") || v.getLong("seq")<=received)throw new Exception("Replay");
                received=v.getLong("seq");listener.data(v);
            }
        } catch(Exception e){fail("Не удалось проверить защищённое соединение");}
    }
    synchronized void send(JSONObject v) {
        if(!ready||closed||socket==null)return;
        try {
            // Drop screen frames under congestion instead of building a memory queue.
            if(v.optString("type").equals("frame") && socket.queueSize()>500000)return;
            socket.send(ByteString.of(seal(key,v.put("seq",++sent).put("role","android"))));
        } catch(Exception e){fail("Ошибка отправки");}
    }
    @Override public void onFailure(WebSocket ws,Throwable t,Response response){fail("Нет соединения. Проверьте адрес и сервер, затем войдите снова.");}
    @Override public void onClosed(WebSocket ws,int code,String reason){fail("Соединение закрыто. Для входа нужен отпечаток.");}
    @Override public void onClosing(WebSocket ws,int code,String reason){ws.close(code,reason);}
    synchronized void fail(String message){if(closed)return;close();listener.status(message);listener.ended();}
    synchronized void close(){if(closed)return;closed=true;ready=false;if(current==this)current=null;if(socket!=null)socket.cancel();client.dispatcher().executorService().shutdown();client.connectionPool().evictAll();java.util.Arrays.fill(base,(byte)0);if(key!=null)java.util.Arrays.fill(key,(byte)0);}
}
