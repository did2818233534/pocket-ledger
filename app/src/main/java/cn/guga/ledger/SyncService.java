package cn.guga.ledger;

import android.app.*;
import android.content.*;
import android.net.*;
import android.net.wifi.WifiManager;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
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
    private NsdManager nsd;
    private NsdManager.DiscoveryListener discovery;
    private final Handler main = new Handler(Looper.getMainLooper());
    private WifiManager.MulticastLock multicast;

    public static void validateHost(String host) throws Exception {
        if (!host.matches("\\d{1,3}(\\.\\d{1,3}){3}")) throw new Exception("IPv4 required");
        InetAddress a = InetAddress.getByName(host);
        if (!a.isSiteLocalAddress() || a.isLoopbackAddress()) throw new Exception("LAN only");
    }
    public static void validateEndpoint(String host) throws Exception {
        if (host.matches("(?i)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.local")) return;
        validateHost(host);
    }
    public static String sign(String key,String body) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8),"HmacSHA256"));
        StringBuilder s = new StringBuilder();
        for (byte b : mac.doFinal(body.getBytes(StandardCharsets.UTF_8))) s.append(String.format("%02x",b & 255));
        return s.toString();
    }
    public static void request(Context context) {
        submit(context, false);
    }
    public static void requestQuietly(Context context) { submit(context, true); }
    private static void submit(Context context, boolean quiet) {
        Context c = context.getApplicationContext();
        requests.execute(() -> synchronize(c, quiet));
    }
    private static void synchronize(Context c, boolean quiet) {
        SharedPreferences p = c.getSharedPreferences("sync",0);
        String key = p.getString("key",""), host = p.getString("host","");
        if (key.isEmpty()) { if (!quiet) p.edit().putString("status","请先配对电脑").apply(); return; }
        HttpURLConnection conn = null;
        try {
            ConnectivityManager cm = (ConnectivityManager)c.getSystemService(CONNECTIVITY_SERVICE);
            Network network = cm.getActiveNetwork();
            NetworkCapabilities caps = cm.getNetworkCapabilities(network);
            if (caps==null || (!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) && !caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET))) {
                network = null;
                for (Network candidate : cm.getAllNetworks()) {
                    NetworkCapabilities candidateCaps = cm.getNetworkCapabilities(candidate);
                    if (candidateCaps != null && (candidateCaps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) || candidateCaps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET))) {
                        network = candidate; break;
                    }
                }
                if (network == null) throw new Exception("未连接局域网，账目已保存在手机");
            }
            validateEndpoint(host);
            if (host.toLowerCase(java.util.Locale.ROOT).endsWith(".local")) {
                String resolved = null;
                for (InetAddress address : network.getAllByName(host)) {
                    if (address instanceof Inet4Address && address.isSiteLocalAddress()) {
                        resolved = address.getHostAddress(); break;
                    }
                }
                if (resolved == null) throw new Exception("等待电脑上线");
                host = resolved;
            }
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
            p.edit().putString("status",quiet ? "账目已保存，等待下次同步" : message == null ? "等待电脑上线" : message).apply();
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
        timer.scheduleWithFixedDelay(() -> {
            requestQuietly(this);
            main.post(this::refreshDiscovery);
        },60,60,TimeUnit.SECONDS);
        nsd = (NsdManager)getSystemService(NSD_SERVICE);
        WifiManager wifi = (WifiManager)getApplicationContext().getSystemService(WIFI_SERVICE);
        multicast = wifi.createMulticastLock("ledger-mdns");
        multicast.setReferenceCounted(false); multicast.acquire();
    }
    private void startDiscovery() {
        if (!running || discovery != null) return;
        NsdManager.DiscoveryListener listener = new NsdManager.DiscoveryListener() {
            public void onDiscoveryStarted(String type) {}
            public void onServiceFound(NsdServiceInfo service) {
                main.post(() -> { if (running) resolve(service); });
            }
            public void onServiceLost(NsdServiceInfo service) {}
            public void onDiscoveryStopped(String type) {
                main.post(() -> { if (discovery == this) discovery = null; startDiscovery(); });
            }
            public void onStartDiscoveryFailed(String type,int code) {
                main.post(() -> { if (discovery == this) discovery = null; });
            }
            public void onStopDiscoveryFailed(String type,int code) {
                main.post(() -> { if (discovery == this) discovery = null; });
            }
        };
        discovery = listener;
        try { nsd.discoverServices("_pocket-ledger._tcp.",NsdManager.PROTOCOL_DNS_SD,listener); }
        catch (Exception ignored) { discovery = null; }
    }
    private void refreshDiscovery() {
        if (!running) return;
        if (discovery == null) { startDiscovery(); return; }
        try { nsd.stopServiceDiscovery(discovery); }
        catch (Exception ignored) { discovery = null; startDiscovery(); }
    }
    private void resolve(NsdServiceInfo service) {
        try {
            nsd.resolveService(service,new NsdManager.ResolveListener() {
                public void onResolveFailed(NsdServiceInfo info,int code) {}
                public void onServiceResolved(NsdServiceInfo info) {
                    if (!running) return;
                    try {
                        SharedPreferences p = getSharedPreferences("sync",0);
                        String key = p.getString("key","");
                        if (key.isEmpty() || info.getPort()!=47831 || info.getHost()==null) return;
                        String host = info.getHost().getHostAddress(); validateHost(host);
                        byte[] hostsBytes=info.getAttributes().get("hosts"), proofBytes=info.getAttributes().get("proof");
                        if (hostsBytes==null || proofBytes==null) return;
                        String hosts=new String(hostsBytes,StandardCharsets.UTF_8),proof=new String(proofBytes,StandardCharsets.UTF_8);
                        if (!java.util.Arrays.asList(hosts.split(",")).contains(host)) return;
                        if (!sign(key,"mdns\n"+hosts+"\n47831").equals(proof)) return;
                        p.edit().putString("host",host).putLong("lastDiscovery",System.currentTimeMillis()).apply();
                        requestQuietly(SyncService.this);
                    } catch (Exception ignored) {}
                }
            });
        } catch (Exception ignored) {}
    }
    public int onStartCommand(Intent intent,int flags,int id) {
        requestQuietly(this); refreshDiscovery(); return START_STICKY;
    }
    public IBinder onBind(Intent i) { return null; }
    public void onDestroy() {
        running=false;
        main.removeCallbacksAndMessages(null);
        if (discovery!=null) {
            try { nsd.stopServiceDiscovery(discovery); } catch (Exception ignored) {}
            discovery=null;
        }
        if (multicast!=null && multicast.isHeld()) multicast.release();
        if (timer!=null) timer.shutdownNow();
        super.onDestroy();
    }
}
