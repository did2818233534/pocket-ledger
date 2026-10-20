package cn.guga.ledger;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONObject;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import mobile.Mobile;

/** Optional embedded Tailscale client. No system VPN, external daemon or local proxy. */
final class Tailnet {
    private static final ScheduledExecutorService worker = Executors.newSingleThreadScheduledExecutor();
    private static volatile String state = "{\"state\":\"Off\",\"peers\":[]}";
    private static boolean initialized;
    static volatile boolean foreground;
    private static long lastRefresh;
    private static volatile String authURL = "";
    private static String lastNetwork = "";
    private static boolean binderReady;
    private static Context app;
    static synchronized void init(Context context) {
        if (initialized) return;
        initialized = true; app = context.getApplicationContext();
        worker.scheduleWithFixedDelay(() -> {
            if (prefs().getBoolean("remoteEnabled",false) && (foreground || android.os.SystemClock.elapsedRealtime()-lastRefresh>=60000)) refresh();
        },0,3,TimeUnit.SECONDS);
    }
    private static SharedPreferences prefs() { return app.getSharedPreferences("sync",0); }
    private static synchronized void start() throws Exception {
        if(!prefs().getBoolean("remoteEnabled",false)) throw new Exception("远程同步已关闭");
        if(!binderReady) {
            Mobile.setNetworkBinder(fd -> {
                android.net.ConnectivityManager cm=(android.net.ConnectivityManager)app.getSystemService(Context.CONNECTIVITY_SERVICE);
                android.net.Network network=cm.getActiveNetwork();
                if(network==null)throw new java.io.IOException("没有可用网络");
                try(android.os.ParcelFileDescriptor duplicate=android.os.ParcelFileDescriptor.fromFd((int)fd)) {
                    network.bindSocket(duplicate.getFileDescriptor());
                }
            });
            binderReady=true;
        }
        updateNetwork();
        Mobile.start(new java.io.File(app.getNoBackupFilesDir(),"tailscale").getAbsolutePath());
    }
    private static void updateNetwork() throws Exception {
        android.net.ConnectivityManager cm=(android.net.ConnectivityManager)app.getSystemService(Context.CONNECTIVITY_SERVICE);
        org.json.JSONArray list=new org.json.JSONArray();String defaultName="";
        android.net.Network active=cm.getActiveNetwork();
        for(android.net.Network network:cm.getAllNetworks()) {
            android.net.LinkProperties link=cm.getLinkProperties(network);
            if(link==null||link.getInterfaceName()==null)continue;
            org.json.JSONArray addresses=new org.json.JSONArray();
            for(android.net.LinkAddress address:link.getLinkAddresses())addresses.put(address.getAddress().getHostAddress()+"/"+address.getPrefixLength());
            list.put(new JSONObject().put("name",link.getInterfaceName()).put("mtu",link.getMtu()).put("addresses",addresses));
            if(network.equals(active))defaultName=link.getInterfaceName();
        }
        String raw=new JSONObject().put("default",defaultName).put("interfaces",list).toString();
        if(!raw.equals(lastNetwork)){Mobile.updateNetwork(raw);lastNetwork=raw;}
    }
    private static void refresh() {
        lastRefresh=android.os.SystemClock.elapsedRealtime();
        try { start(); state = Mobile.status(); authURL = new JSONObject(state).optString("authURL",""); }
        catch (Exception e) { state = "{\"state\":\"Error\",\"peers\":[]}"; }
    }
    static String status() { return state; }
    static void enable(Context c) {
        init(c); prefs().edit().putBoolean("remoteEnabled",true).apply();
        state = "{\"state\":\"Starting\",\"peers\":[]}";
        worker.execute(Tailnet::refresh);
    }
    static void login(Context c) {
        enable(c);
        worker.execute(() -> { try { start(); Mobile.login(); refresh(); } catch (Exception e) { state="{\"state\":\"Error\",\"peers\":[]}"; } });
    }
    static String loginURL() {
        // Only the official authentication site may open in the phone browser.
        String url = authURL;
        try {
            java.net.URI uri = new java.net.URI(url);
            if ("https".equals(uri.getScheme()) && "login.tailscale.com".equals(uri.getHost()) && uri.getUserInfo()==null && (uri.getPort()==-1||uri.getPort()==443)) return url;
        } catch(Exception ignored) {}
        return "";
    }
    static void disable(Context c, boolean logout) {
        init(c); prefs().edit().putBoolean("remoteEnabled",false).apply();
        worker.execute(() -> {
            try {
                if (logout) { Mobile.start(new java.io.File(app.getNoBackupFilesDir(),"tailscale").getAbsolutePath()); Mobile.logout(); }
                else Mobile.stop();
                authURL="";state="{\"state\":\"Off\",\"peers\":[]}";
            } catch(Exception e) {
                try { Mobile.stop(); } catch(Exception ignored) {}
                authURL="";state="{\"state\":\"LogoutFailed\",\"peers\":[]}";
            }
        });
    }
    static boolean validHost(String host) {
        if (!host.matches("100\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}")) return false;
        String[] parts = host.split("\\.");
        try { return Integer.parseInt(parts[1])>=64 && Integer.parseInt(parts[1])<=127 && Integer.parseInt(parts[2])<=255 && Integer.parseInt(parts[3])<=255; }
        catch(Exception e) { return false; }
    }
    static JSONObject exchange(String host,String body,String time,String signature,String key) throws Exception {
        if (!prefs().getBoolean("remoteEnabled",false) || !validHost(host)) throw new Exception("远程同步未开启或尚未选择电脑");
        start();
        String challenge=java.util.UUID.randomUUID().toString().replace("-","");
        String proofTime=Long.toString(System.currentTimeMillis()/1000);
        String proofBody=new JSONObject().put("challenge",challenge).toString();
        JSONObject proof=new JSONObject(Mobile.probe(host,proofBody,proofTime,SyncService.sign(key,proofTime+"\n"+proofBody)));
        if(proof.getInt("code")!=200 || !SyncService.sign(key,proofTime+"\n"+proof.getString("body")).equals(proof.optString("signature")) ||
            !challenge.equals(new JSONObject(proof.getString("body")).optString("challenge")))
            throw new Exception("远程电脑身份验证失败，请检查配对密钥与电脑服务版本");
        if(!prefs().getBoolean("remoteEnabled",false))throw new Exception("远程同步已关闭");
        return new JSONObject(Mobile.exchange(host,body,time,signature));
    }
}
