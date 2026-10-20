package cn.guga.ledger;

import android.app.*;
import android.content.*;
import android.net.*;
import android.net.wifi.WifiManager;
import android.os.*;
import org.json.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class SyncService extends Service {
    private static final ExecutorService requests = Executors.newSingleThreadExecutor();
    private ScheduledExecutorService timer;
    private volatile boolean running;
    private DatagramSocket socket;
    private WifiManager.MulticastLock multicast;
    private Thread listener;
    public static void validateHost(String host) throws Exception {
        if (!host.matches("\\d{1,3}(\\.\\d{1,3}){3}")) throw new Exception("IPv4 required");
        InetAddress a = InetAddress.getByName(host);
        if (!a.isSiteLocalAddress() || a.isLoopbackAddress()) throw new Exception("LAN only");
    }
    public static String sign(String key,String body) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8),"HmacSHA256"));
        StringBuilder s = new StringBuilder();
        for (byte b : mac.doFinal(body.getBytes(StandardCharsets.UTF_8))) s.append(String.format("%02x",b & 255));
        return s.toString();
    }
    public static void request(Context context) {
        Context c = context.getApplicationContext();
        requests.execute(() -> synchronize(c));
    }
    private static void synchronize(Context c) {
        SharedPreferences p = c.getSharedPreferences("sync",0);
        String key = p.getString("key",""), host = p.getString("host","");
        if (key.isEmpty()) { p.edit().putString("status","请先配对电脑").apply(); return; }
        HttpURLConnection conn = null;
        try {
            ConnectivityManager cm = (ConnectivityManager)c.getSystemService(CONNECTIVITY_SERVICE);
            Network network = cm.getActiveNetwork();
            NetworkCapabilities caps = cm.getNetworkCapabilities(network);
            if (caps==null || (!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) && !caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)))
                throw new Exception("未连接局域网，账目已保存在手机");
            validateHost(host);
            JSONObject snapshot = LedgerDb.get(c).snapshot();
            String body = snapshot.toString();
            String timestamp = Long.toString(System.currentTimeMillis()/1000);
            conn = (HttpURLConnection)network.openConnection(new URL("http://"+host+":47831/sync"));
            conn.setConnectTimeout(3500); conn.setReadTimeout(5000); conn.setInstanceFollowRedirects(false);
            conn.setRequestMethod("POST"); conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type","application/json");
            conn.setRequestProperty("X-Time",timestamp);
            conn.setRequestProperty("X-Signature",sign(key,timestamp+"\n"+body));
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(bytes.length);
            try (java.io.OutputStream out = conn.getOutputStream()) { out.write(bytes); }
            int status = conn.getResponseCode();
            if (status==401) throw new Exception("配对失败：请检查密钥和两端时间");
            if (status!=200) throw new Exception("同步未完成（"+status+"），手机数据保留");
            String reply;
            try (java.io.InputStream in = conn.getInputStream(); java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream()) {
                byte[] buffer = new byte[1024]; int n;
                while ((n=in.read(buffer))!=-1) {
                    if (out.size()+n>4096) throw new Exception("电脑响应过大");
                    out.write(buffer,0,n);
                }
                reply = out.toString("UTF-8");
            }
            if (!sign(key,timestamp+"\n"+reply).equals(conn.getHeaderField("X-Signature"))) throw new Exception("电脑身份校验失败");
            JSONObject result = new JSONObject(reply);
            if (result.getLong("revision")!=snapshot.getLong("revision")) throw new Exception("版本校验失败");
            p.edit().putLong("lastSync",System.currentTimeMillis()).putLong("syncedRevision",snapshot.getLong("revision"))
                .putString("status","已与电脑同步").apply();
        } catch(Exception e) {
            String message = e.getMessage();
            if (e instanceof java.io.IOException) message = "电脑暂时离线，账目已保存在手机";
            p.edit().putString("status",message == null ? "等待电脑上线" : message).apply();
        } finally { if (conn!=null) conn.disconnect(); }
    }
    public void onCreate() {
        super.onCreate(); running = true;
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel("sync","局域网同步",NotificationManager.IMPORTANCE_LOW));
        PendingIntent launch = PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE);
        Notification note = new Notification.Builder(this,"sync").setSmallIcon(cn.guga.ledger.R.drawable.ic_ledger)
            .setContentTitle("小账 · 局域网同步").setContentText("每分钟检查电脑，账目始终保存在手机")
            .setContentIntent(launch).setOngoing(true).build();
        startForeground(1,note);
        timer = Executors.newSingleThreadScheduledExecutor();
        timer.scheduleWithFixedDelay(() -> request(this),60,60,TimeUnit.SECONDS);
        listener = new Thread(this::listen,"ledger-discovery"); listener.start();
    }
    private void listen() {
        try {
            WifiManager wifi = (WifiManager)getApplicationContext().getSystemService(WIFI_SERVICE);
            multicast = wifi.createMulticastLock("ledger-discovery"); multicast.setReferenceCounted(false); multicast.acquire();
            socket = new DatagramSocket(null); socket.setReuseAddress(true); socket.bind(new InetSocketAddress(47832)); socket.setSoTimeout(2000);
            while (running) {
                try {
                    byte[] buffer = new byte[2048]; DatagramPacket packet = new DatagramPacket(buffer,buffer.length); socket.receive(packet);
                    JSONObject message = new JSONObject(new String(packet.getData(),0,packet.getLength(),StandardCharsets.UTF_8));
                    SharedPreferences p = getSharedPreferences("sync",0);
                    String key = p.getString("key",""), body = message.getString("body");
                    if (key.isEmpty() || !sign(key,body).equals(message.getString("signature"))) continue;
                    JSONObject data = new JSONObject(body);
                    if (!data.getString("app").equals("pocket-ledger") || Math.abs(System.currentTimeMillis()/1000-data.getLong("time"))>90) continue;
                    String host = data.getString("host"); validateHost(host);
                    if (!host.equals(packet.getAddress().getHostAddress())) continue;
                    p.edit().putString("host",host).apply();
                    request(this);
                } catch(SocketTimeoutException ignored) {} catch(Exception ignored) {}
            }
        } catch(Exception ignored) {
            // Periodic HTTP polling remains available if UDP is blocked.
        } finally { if (multicast!=null && multicast.isHeld()) multicast.release(); }
    }
    public int onStartCommand(Intent intent,int flags,int id) { request(this); return START_STICKY; }
    public IBinder onBind(Intent i) { return null; }
    public void onDestroy() {
        running=false;
        if (socket!=null) socket.close();
        if (timer!=null) timer.shutdownNow();
        super.onDestroy();
    }
}
