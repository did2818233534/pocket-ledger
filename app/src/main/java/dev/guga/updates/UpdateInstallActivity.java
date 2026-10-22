package dev.guga.updates;

import android.app.*;
import android.content.*;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Bundle;
import android.widget.*;
import java.lang.ref.WeakReference;

public final class UpdateInstallActivity extends Activity {
  static WeakReference<UpdateInstallActivity> foreground=new WeakReference<>(null);
  boolean installing;
  AlertDialog errorDialog;
  public void onCreate(Bundle saved) {
    super.onCreate(saved);
    foreground=new WeakReference<>(this);
    UpdateStyle ui=new UpdateStyle(this);
    LinearLayout panel=new LinearLayout(this); panel.setOrientation(LinearLayout.VERTICAL);
    panel.setPadding(ui.dp(24),ui.dp(24),ui.dp(24),ui.dp(24)); panel.setBackground(ui.shape(UpdateStyle.BACKGROUND,28));
    TextView title=new TextView(this); title.setText("安装更新"); title.setTextSize(22); title.setTextColor(UpdateStyle.INK); panel.addView(title);
    TextView detail=new TextView(this); detail.setText("正在准备系统安装确认…"); detail.setTextSize(15); detail.setTextColor(UpdateStyle.MUTED); detail.setPadding(0,ui.dp(16),0,ui.dp(8)); panel.addView(detail);
    setContentView(panel); getWindow().setBackgroundDrawableResource(android.R.color.transparent);
    getWindow().setLayout(Math.min(getResources().getDisplayMetrics().widthPixels-ui.dp(48),ui.dp(420)),-2);
    installing=saved!=null && saved.getBoolean("installing");
    if (saved!=null) return;
    Intent confirmation=getIntent().getParcelableExtra("confirmation");
    if (confirmation!=null) confirm(confirmation);
    else begin();
  }
  void begin() {
    if (!getPackageManager().canRequestPackageInstalls()) {
      try { startActivityForResult(new Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
        Uri.parse("package:"+getPackageName())),1); }
      catch(Exception e) { showFailure("无法打开安装权限设置，请在系统设置中允许此应用安装更新。"); }
    } else install();
  }
  void install() {
    if (installing) return;
    installing=true;
    new Thread(() -> {
      try { AppUpdates.install(getApplicationContext(),true); }
      catch (Exception e) { runOnUiThread(() -> { installing=false; showFailure(AppUpdates.failure(e)); }); }
      // Keep this foreground Activity alive until PackageInstaller returns its confirmation.
    },"release-update-install").start();
  }
  void confirm(Intent confirmation) {
    if(confirmation==null) { showFailure("系统未提供安装确认界面，请重试。"); return; }
    installing=true;
    try { startActivityForResult(confirmation,2); }
    catch(Exception e) { showFailure("无法打开系统安装界面，请重试或检查系统安装限制。"); }
  }
  static boolean deliver(int status,Intent confirmation) {
    UpdateInstallActivity activity=foreground.get();
    if(activity==null || activity.isFinishing() || activity.isDestroyed()) return false;
    activity.runOnUiThread(() -> {
      if(status==PackageInstaller.STATUS_PENDING_USER_ACTION) activity.confirm(confirmation);
      else if(status==PackageInstaller.STATUS_SUCCESS) activity.finish();
      else {
        activity.installing=false;
        String message=status==PackageInstaller.STATUS_FAILURE_ABORTED ? "安装已取消，可以重新尝试。" :
          status==PackageInstaller.STATUS_FAILURE_STORAGE ? "存储空间不足，请清理后重试。" :
          status==PackageInstaller.STATUS_FAILURE_BLOCKED ? "系统阻止了安装，请检查安装权限或手机安全设置。" :
          "系统未能完成安装（错误代码 " + status + "），请重试。";
        activity.showFailure(message);
      }
    });
    return true;
  }
  void showFailure(String message) {
    if(isFinishing() || isDestroyed()) return;
    installing=false;
    if(errorDialog!=null) errorDialog.dismiss();
    errorDialog=new AlertDialog.Builder(this).setTitle("未完成安装").setMessage(message)
      .setNegativeButton("取消",(d,w)->finish()).setPositiveButton("重试",(d,w)->begin()).create();
    errorDialog.setOnCancelListener(d->finish()); errorDialog.show();
    UpdateStyle ui=new UpdateStyle(this); errorDialog.getWindow().setBackgroundDrawable(ui.shape(UpdateStyle.BACKGROUND,28));
    ui.dialogAction(errorDialog.getButton(AlertDialog.BUTTON_NEGATIVE),false);
    ui.dialogAction(errorDialog.getButton(AlertDialog.BUTTON_POSITIVE),false);
  }
  protected void onActivityResult(int request,int result,Intent data) {
    super.onActivityResult(request,result,data);
    if(request==1) {
      if(getPackageManager().canRequestPackageInstalls()) install();
      else showFailure("尚未允许安装更新，请开启系统中的“允许来自此来源的应用”。");
    }
    if(request==2 && result!=RESULT_OK) new android.os.Handler(getMainLooper()).postDelayed(() -> {
      if(installing && !isFinishing() && !isDestroyed()) showFailure("安装未完成或已取消，可以重试。");
    },800);
    // Detailed installer outcomes arrive through UpdateResultReceiver.
  }
  protected void onSaveInstanceState(Bundle saved) { saved.putBoolean("installing",installing); super.onSaveInstanceState(saved); }
  protected void onDestroy() { if(foreground.get()==this) foreground.clear(); super.onDestroy(); }
}
