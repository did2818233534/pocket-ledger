package cn.guga.ledger;

import android.app.*;
import android.os.*;
import android.content.*;
import android.webkit.*;
import android.view.*;
import org.json.*;

public class MainActivity extends Activity {
    /** One rounded surface for all app-owned native dialogs. */
    private static final class LedgerDialogBuilder extends AlertDialog.Builder {
        LedgerDialogBuilder(Context context){super(context);}
        @Override public AlertDialog show(){
            AlertDialog dialog=super.show();
            android.view.Window window=dialog.getWindow();
            if(window!=null){
                float density=getContext().getResources().getDisplayMetrics().density;
                android.graphics.drawable.GradientDrawable surface=new android.graphics.drawable.GradientDrawable();
                surface.setColor(0xfffcfdf9);surface.setCornerRadius(24*density);
                window.setBackgroundDrawable(surface);
                window.getDecorView().setClipToOutline(true);
                int width=Math.min((int)(520*density),getContext().getResources().getDisplayMetrics().widthPixels-(int)(48*density));
                window.setLayout(width,android.view.ViewGroup.LayoutParams.WRAP_CONTENT);
            }
            for(int which:new int[]{AlertDialog.BUTTON_POSITIVE,AlertDialog.BUTTON_NEGATIVE,AlertDialog.BUTTON_NEUTRAL}){
                android.widget.Button button=dialog.getButton(which);if(button!=null)button.setTextColor(0xff257d61);
            }
            return dialog;
        }
    }
    private WebView web;
    private String avatarUser;
    private boolean handlingBack;
    private android.window.OnBackInvokedCallback backCallback;
    public void onCreate(Bundle state) {
        super.onCreate(state);
        avatarUser=state==null?null:state.getString("avatarUser");
        Tailnet.init(this);
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
                new LedgerDialogBuilder(MainActivity.this).setMessage(message)
                    .setPositiveButton(message.startsWith("确定删除") ? "删除" : message.startsWith("退出 Tailscale") ? "退出账号" : "放弃修改",(d,w)->result.confirm())
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
    }
    @Override protected void onStart() {
        super.onStart();web.onResume();web.resumeTimers();
        SyncService.resumeSession();Tailnet.resume(this);
        if(getSharedPreferences("sync",0).getBoolean("enabled",false))startForegroundService(new Intent(this,SyncService.class));
        else SyncService.requestQuietly(this);
    }
    @Override protected void onStop() {
        SyncService.pauseSession();stopService(new Intent(this,SyncService.class));Tailnet.suspend();
        web.onPause();web.pauseTimers();super.onStop();
    }
    @Override protected void onResume() { super.onResume(); Tailnet.foreground=true; }
    @Override protected void onPause() { Tailnet.foreground=false; super.onPause(); }
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
            new LedgerDialogBuilder(this).setTitle("退出小账？")
                .setMessage("账目已保存在手机。退出后停止同步和远程连接，下次打开立即同步。")
                .setNegativeButton("留在小账",(d,w)->{})
                .setPositiveButton("退出小账",(d,w)->finishAndRemoveTask())
                .setOnDismissListener(d->handlingBack=false).show();
        });
    }
    class Bridge {
        @JavascriptInterface public void chooseDate(String raw) {
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed())return;
                java.time.LocalDate initial;
                try{initial=java.time.LocalDate.parse(raw);}catch(Exception e){initial=java.time.LocalDate.now();}
                android.widget.LinearLayout row=new android.widget.LinearLayout(MainActivity.this);
                row.setPadding(24,16,24,8);
                android.widget.NumberPicker year=new android.widget.NumberPicker(MainActivity.this),month=new android.widget.NumberPicker(MainActivity.this),day=new android.widget.NumberPicker(MainActivity.this);
                year.setMinValue(1900);year.setMaxValue(9999);year.setValue(initial.getYear());
                month.setMinValue(1);month.setMaxValue(12);month.setValue(initial.getMonthValue());
                day.setMinValue(1);day.setMaxValue(initial.lengthOfMonth());day.setValue(initial.getDayOfMonth());
                android.widget.NumberPicker[] wheels={year,month,day};String[] labels={"年","月","日"};
                for(int i=0;i<wheels.length;i++){
                    android.widget.NumberPicker wheel=wheels[i];final String unit=labels[i];wheel.setFormatter(v->v+unit);wheel.setContentDescription(unit);wheel.setWrapSelectorWheel(false);wheel.setDescendantFocusability(android.view.ViewGroup.FOCUS_BLOCK_DESCENDANTS);
                    row.addView(wheel,new android.widget.LinearLayout.LayoutParams(0,-2,1));
                }
                android.widget.NumberPicker.OnValueChangeListener changed=(picker,oldValue,newValue)->{int maximum=java.time.YearMonth.of(year.getValue(),month.getValue()).lengthOfMonth();day.setValue(Math.min(day.getValue(),maximum));day.setMaxValue(maximum);};
                year.setOnValueChangedListener(changed);month.setOnValueChangedListener(changed);
                new LedgerDialogBuilder(MainActivity.this).setTitle("选择日期").setView(row)
                    .setNegativeButton("取消",null).setPositiveButton("确定",(dialog,which)->{
                        String value=java.time.LocalDate.of(year.getValue(),month.getValue(),day.getValue()).toString();
                        web.evaluateJavascript("window.setExpenseDate("+JSONObject.quote(value)+")",null);
                    }).show();
            });
        }
        @JavascriptInterface public void hideKeyboard() {
            runOnUiThread(() -> {
                if (Build.VERSION.SDK_INT >= 30)
                    getWindow().getInsetsController().hide(WindowInsets.Type.ime());
                else ((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE))
                    .hideSoftInputFromWindow(web.getWindowToken(),0);
            });
        }
        @JavascriptInterface public String load() {
            try {
                JSONObject data = LedgerDb.get(MainActivity.this).snapshot();
                android.content.SharedPreferences p = getSharedPreferences("sync",0);
                return data.put("host",p.getString("host","")).put("paired",!p.getString("key","").isEmpty())
                    .put("enabled",p.getBoolean("enabled",false)).put("status",p.getString("status","尚未连接电脑"))
                    .put("lastSync",p.getLong("lastSync",0)).put("lastDiscovery",p.getLong("lastDiscovery",0))
                    .put("syncedRevision",p.getLong("syncedRevision",-1))
                    .put("remoteEnabled",p.getBoolean("remoteEnabled",false)).put("remoteHost",p.getString("remoteHost",""))
                    .put("lastRoute",p.getString("lastRoute",""))
                    .put("tailnet",new JSONObject(Tailnet.status())).toString();
            } catch(Exception e) { return "{\"error\":\"读取账本失败\"}"; }
        }
        @JavascriptInterface public String save(String data) {
            try { LedgerDb.get(MainActivity.this).save(data); autoSync(); return ""; }
            catch(Exception e) { return "保存失败，请检查输入"; }
        }
        @JavascriptInterface public String selectUser(String id) {
            try { LedgerDb.get(MainActivity.this).selectUser(id); return ""; } catch(Exception e) { return "切换用户失败"; }
        }
        @JavascriptInterface public String addUser(String name) {
            try { LedgerDb.get(MainActivity.this).addUser(name); autoSync(); return ""; } catch(Exception e) { return "添加失败，请输入 1–24 个字的名字"; }
        }
        @JavascriptInterface public void chooseAvatar(String id) {
            runOnUiThread(()->{
                avatarUser=id;
                Intent pick=new Intent(Intent.ACTION_GET_CONTENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE);
                try{startActivityForResult(pick,11);}catch(Exception e){android.widget.Toast.makeText(MainActivity.this,"无法打开图片选择器",0).show();}
            });
        }
        @JavascriptInterface public String clearAvatar(String id) {
            try{LedgerDb.get(MainActivity.this).setAvatar(id,"");autoSync();return "";}catch(Exception e){return "请先等待用户资料同步";}
        }
        @JavascriptInterface public String joinUser(String id) {
            try { LedgerDb.get(MainActivity.this).joinUser(id); autoSync(); return ""; } catch(Exception e) { return "请检查用户 ID 是否完整、正确"; }
        }
        @JavascriptInterface public String leaveUser(String id) {
            try { LedgerDb.get(MainActivity.this).leaveUser(id,getSharedPreferences("sync",0).getLong("syncedRevision",-1)); autoSync(); return ""; } catch(Exception e) { return e.getMessage(); }
        }
        @JavascriptInterface public void copyUserId(String id) {
            try { java.util.UUID.fromString(id); runOnUiThread(()->((android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(android.content.ClipData.newPlainText("小账用户 ID",id))); } catch(Exception ignored) {}
        }
        @JavascriptInterface public String renameUser(String id,String name) {
            try { LedgerDb.get(MainActivity.this).renameUser(id,name); autoSync(); return ""; } catch(Exception e) { return "名字需为 1–24 个字"; }
        }
        @JavascriptInterface public String toggleReimbursed(String id) {
            try{LedgerDb.get(MainActivity.this).toggleReimbursed(id);autoSync();return "";}catch(Exception e){return "报销状态更新失败，请重试";}
        }
        @JavascriptInterface public void remove(String id) { LedgerDb.get(MainActivity.this).delete(id); autoSync(); }
        private void autoSync() {
            if (!getSharedPreferences("sync",0).getString("key","").isEmpty()) SyncService.requestQuietly(MainActivity.this);
        }
        @JavascriptInterface public String configure(String host, String key) {
            try {
                if (!host.isEmpty() || !Tailnet.validHost(getSharedPreferences("sync",0).getString("remoteHost","")))
                    SyncService.validateEndpoint(host);
                if (key.isEmpty()) key = getSharedPreferences("sync",0).getString("key","");
                if (!key.matches("[a-f0-9]{64}")) return "请输入电脑生成的 64 位配对密钥";
                getSharedPreferences("sync",0).edit().putString("host",host).putString("key",key).putBoolean("enabled",true).commit();
                runOnUiThread(() -> {
                    if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED)
                        requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},7);
                    startForegroundService(new Intent(MainActivity.this,SyncService.class));
                });
                return "";
            } catch(Exception e) { return "请输入 .local 主机名或局域网 IPv4 地址，例如 guga.local"; }
        }
        @JavascriptInterface public void showLicenses() {
            runOnUiThread(() -> {
                try (java.io.InputStream input=getAssets().open("tailscale-notices.txt")) {
                    java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();byte[] buffer=new byte[4096];int n;
                    while((n=input.read(buffer))!=-1)out.write(buffer,0,n);
                    android.widget.TextView text=new android.widget.TextView(MainActivity.this);
                    text.setText(out.toString("UTF-8"));text.setTextSize(12);text.setPadding(24,16,24,16);text.setTextIsSelectable(true);
                    android.widget.ScrollView scroll=new android.widget.ScrollView(MainActivity.this);scroll.addView(text);
                    new LedgerDialogBuilder(MainActivity.this).setTitle("开源许可").setView(scroll).setPositiveButton("关闭",null).show();
                } catch(Exception ignored) {}
            });
        }
        @JavascriptInterface public void enableRemote() { Tailnet.enable(MainActivity.this); }
        @JavascriptInterface public void loginRemote() { Tailnet.login(MainActivity.this); }
        @JavascriptInterface public String openRemoteLogin() {
            String url=Tailnet.loginURL();
            if(url.isEmpty()) return "登录链接正在准备，请稍候重试";
            runOnUiThread(() -> {
                try { startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(url))); }
                catch(Exception e) { android.widget.Toast.makeText(MainActivity.this,"请先安装手机浏览器",0).show(); }
            });
            return "";
        }
        @JavascriptInterface public void disableRemote(boolean logout) { Tailnet.disable(MainActivity.this,logout); }
        @JavascriptInterface public String selectRemote(String host) {
            if(!Tailnet.validHost(host)) return "请选择 Tailscale 网络中的电脑";
            getSharedPreferences("sync",0).edit().putString("remoteHost",host).apply();
            SyncService.requestQuietly(MainActivity.this);return "";
        }
        @JavascriptInterface public void sync() { SyncService.request(MainActivity.this); }
        @JavascriptInterface public void stop() {
            getSharedPreferences("sync",0).edit().putBoolean("enabled",false).putString("status","定时同步已暂停，打开应用或保存更改时仍会同步").apply();
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
        if(request==11){
            String id=avatarUser;avatarUser=null;
            if(result==RESULT_OK&&data!=null&&data.getData()!=null&&id!=null){
                android.net.Uri uri=data.getData();
                new Thread(()->{
                    try{
                        String image=AvatarCodec.read(this,uri);LedgerDb.get(this).setAvatar(id,image);SyncService.requestQuietly(this);
                        runOnUiThread(()->{if(!isDestroyed()){web.evaluateJavascript("refreshProfileView()",null);android.widget.Toast.makeText(this,"头像已更新，等待同步",0).show();}});
                    }catch(Exception e){runOnUiThread(()->android.widget.Toast.makeText(this,"图片读取失败，请换一张图片",0).show());}
                },"ledger-avatar").start();
            }
            return;
        }
        if (request==10 && result==RESULT_OK && data!=null) {
            try (java.io.OutputStream out = getContentResolver().openOutputStream(data.getData())) {
                out.write(LedgerDb.get(this).snapshot().toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));
                android.widget.Toast.makeText(this,"备份已导出",0).show();
            } catch(Exception e) { android.widget.Toast.makeText(this,"导出失败",0).show(); }
        }
    }
    protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);state.putString("avatarUser",avatarUser);}
    public void onDestroy() {
        if (Build.VERSION.SDK_INT >= 33 && backCallback != null)
            getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(backCallback);
        web.destroy(); super.onDestroy();
    }
}
