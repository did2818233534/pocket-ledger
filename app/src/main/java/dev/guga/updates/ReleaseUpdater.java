package dev.guga.updates;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;

/** Public update API. Storage, sessions, downloads and certificates remain internal. */
public final class ReleaseUpdater {
  private ReleaseUpdater() {}
  public static void resume() { AppUpdates.foreground=true; }
  public static void suspend() {
    AppUpdates.foreground=false; AppUpdates.cancelled=true;
    okhttp3.OkHttpClient client=AppUpdates.activeClient;
    if(client!=null) client.dispatcher().cancelAll();
  }
  public static boolean isAutomaticEnabled(Context context) { return AppUpdates.enabled(context); }
  public static void setAutomaticEnabled(Context context,boolean enabled) { AppUpdates.setEnabled(context.getApplicationContext(),enabled); }
  /** Call on foreground entry. At most one automatic attempt per local calendar day. */
  public static void checkAutomatically(Context context) { AppUpdates.checkAsync(context,false,null); }
  /** Manual checks ignore the daily gate; an existing request is reused. Callback runs on main. */
  public static void checkManually(Context context,Runnable finished) {
    AppUpdates.checkAsync(context,true,() -> {
      if(finished==null) return;
      Handler main=new Handler(Looper.getMainLooper());
      main.post(new Runnable() { public void run() {
        if(isRunning()) main.postDelayed(this,100); else finished.run();
      }});
    });
  }
  public static boolean isRunning() { return AppUpdates.running.get(); }
  public static String statusMessage() { return AppUpdates.status; }
  public static boolean latestDownloadReady(Context context) { return AppUpdates.readyResult && hasDownloadedUpdate(context); }
  public static boolean hasDownloadedUpdate(Context context) {
    try { return AppUpdates.prefs(context).getLong("ready",0)>context.getPackageManager().getPackageInfo(context.getPackageName(),0).getLongVersionCode()
      && AppUpdates.apk(context).exists(); } catch(Exception ignored) { return false; }
  }
  public static void installDownloaded(Activity activity) { activity.startActivity(new Intent(activity,UpdateInstallActivity.class)); }
}
