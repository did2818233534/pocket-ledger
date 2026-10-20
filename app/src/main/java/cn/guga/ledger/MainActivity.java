package cn.guga.ledger;

import android.app.*;
import android.os.*;
import android.content.*;
import android.webkit.*;
import android.view.*;
import org.json.*;

public class MainActivity extends Activity {
    private WebView web;
    private boolean handlingBack;
    private android.window.OnBackInvokedCallback backCallback;
    public void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE)!=0)
            WebView.setWebContentsDebuggingEnabled(true);
        web.setBackgroundColor(0xfff6f7f3);
        android.widget.FrameLayout root = new android.widget.FrameLayout(this);
        root.setBackgroundColor(android.graphics.Color.WHITE);
        root.addView(web,new android.widget.FrameLayout.LayoutParams(-1,-1));
        getWindow().setNavigationBarColor(android.graphics.Color.WHITE);
        getWindow().setStatusBarColor(0xfff6f7f3);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        if (Build.VERSION.SDK_INT >= 29) getWindow().setNavigationBarContrastEnforced(false);
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            getWindow().getInsetsController().setSystemBarsAppearance(
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
            root.setOnApplyWindowInsetsListener((v,insets) -> {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                android.graphics.Insets keyboard = insets.getInsets(WindowInsets.Type.ime());
                android.widget.FrameLayout.LayoutParams layout = (android.widget.FrameLayout.LayoutParams)web.getLayoutParams();
                layout.setMargins(bars.left,bars.top,bars.right,Math.max(bars.bottom,keyboard.bottom));
                web.setLayoutParams(layout);
                return WindowInsets.CONSUMED;
            });
        }
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setDomStorageEnabled(false);
        web.addJavascriptInterface(new Bridge(), "Native");
        web.setWebChromeClient(new WebChromeClient() {
            public boolean onJsConfirm(WebView view,String url,String message,JsResult result) {
                new AlertDialog.Builder(MainActivity.this).setMessage(message)
                    .setPositiveButton(message.startsWith("确定删除") ? "删除" : "放弃修改",(d,w)->result.confirm())
                    .setNegativeButton("取消",(d,w)->result.cancel())
                    .setOnCancelListener(d->result.cancel()).show();
                return true;
            }
        });
        web.setWebViewClient(new WebViewClient() {
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) { return true; }
            public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
                if (!r.getUrl().toString().startsWith("https://ledger.local/")) return new WebResourceResponse("text/plain","UTF-8",null);
                String path = r.getUrl().getPath().substring(1);
                if (!path.matches("[a-zA-Z0-9.-]+")) path = "index.html";
                try { return new WebResourceResponse(path.endsWith(".js") ? "text/javascript" : path.endsWith(".css") ? "text/css" : "text/html","UTF-8",getAssets().open(path)); }
                catch(Exception e) { return new WebResourceResponse("text/plain","UTF-8",null); }
            }
        });
        setContentView(root);
        root.requestApplyInsets();
        web.loadUrl("https://ledger.local/index.html");
        if (Build.VERSION.SDK_INT >= 33) {
            backCallback = this::handleBack;
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,backCallback);
        }
        if (getSharedPreferences("sync",0).getBoolean("enabled",false)) startForegroundService(new Intent(this,SyncService.class));
    }
    @Override public void onBackPressed() { handleBack(); }
    private void handleBack() {
        if (handlingBack) return;
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsets insets = web.getRootWindowInsets();
            if (insets != null && insets.isVisible(WindowInsets.Type.ime())) {
                getWindow().getInsetsController().hide(WindowInsets.Type.ime());
                return;
            }
        }
        handlingBack = true;
        web.evaluateJavascript("typeof window.handleAppBack === 'function' ? window.handleAppBack() : 'loading'", value -> {
            if (isFinishing() || isDestroyed()) { handlingBack=false; return; }
            if (!"\"root\"".equals(value)) { handlingBack=false; return; }
            boolean enabled = getSharedPreferences("sync",0).getBoolean("enabled",false);
            new AlertDialog.Builder(this).setTitle("返回桌面？")
                .setMessage(enabled ? "账目已保存在手机，自动同步会继续在后台运行。" : "账目已保存在手机。")
                .setNegativeButton("留在小账",(d,w)->{})
                .setPositiveButton("返回桌面",(d,w)->moveTaskToBack(true))
                .setOnDismissListener(d->handlingBack=false).show();
        });
    }
    class Bridge {
        @JavascriptInterface public String load() {
            try {
                JSONObject data = LedgerDb.get(MainActivity.this).snapshot();
                android.content.SharedPreferences p = getSharedPreferences("sync",0);
                return data.put("host",p.getString("host","")).put("paired",!p.getString("key","").isEmpty())
                    .put("enabled",p.getBoolean("enabled",false)).put("status",p.getString("status","尚未连接电脑"))
                    .put("lastSync",p.getLong("lastSync",0)).put("syncedRevision",p.getLong("syncedRevision",-1)).toString();
            } catch(Exception e) { return "{\"error\":\"读取账本失败\"}"; }
        }
        @JavascriptInterface public String save(String data) {
            try { LedgerDb.get(MainActivity.this).save(data); autoSync(); return ""; }
            catch(Exception e) { return "保存失败，请检查输入"; }
        }
        @JavascriptInterface public void remove(String id) { LedgerDb.get(MainActivity.this).delete(id); autoSync(); }
        private void autoSync() {
            if (getSharedPreferences("sync",0).getBoolean("enabled",false)) SyncService.request(MainActivity.this);
        }
        @JavascriptInterface public String configure(String host, String key) {
            try {
                SyncService.validateHost(host);
                if (key.isEmpty()) key = getSharedPreferences("sync",0).getString("key","");
                if (!key.matches("[a-f0-9]{64}")) return "请输入电脑生成的 64 位配对密钥";
                getSharedPreferences("sync",0).edit().putString("host",host).putString("key",key).putBoolean("enabled",true).commit();
                runOnUiThread(() -> {
                    if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED)
                        requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},7);
                    startForegroundService(new Intent(MainActivity.this,SyncService.class));
                });
                return "";
            } catch(Exception e) { return "请输入局域网 IPv4 地址，例如 192.168.1.8"; }
        }
        @JavascriptInterface public void sync() { SyncService.request(MainActivity.this); }
        @JavascriptInterface public void stop() {
            getSharedPreferences("sync",0).edit().putBoolean("enabled",false).putString("status","自动同步已暂停").apply();
            stopService(new Intent(MainActivity.this,SyncService.class));
        }
        @JavascriptInterface public void exportData() {
            runOnUiThread(() -> {
                Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,"小账备份.json");
                startActivityForResult(i,10);
            });
        }
    }
    protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if (request==10 && result==RESULT_OK && data!=null) {
            try (java.io.OutputStream out = getContentResolver().openOutputStream(data.getData())) {
                out.write(LedgerDb.get(this).snapshot().toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));
                android.widget.Toast.makeText(this,"备份已导出",0).show();
            } catch(Exception e) { android.widget.Toast.makeText(this,"导出失败",0).show(); }
        }
    }
    public void onDestroy() {
        if (Build.VERSION.SDK_INT >= 33 && backCallback != null)
            getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(backCallback);
        web.destroy(); super.onDestroy();
    }
}
