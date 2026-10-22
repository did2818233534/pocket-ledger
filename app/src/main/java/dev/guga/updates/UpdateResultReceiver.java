package dev.guga.updates;
import android.content.*;
import android.content.pm.PackageInstaller;
public final class UpdateResultReceiver extends BroadcastReceiver {
  public void onReceive(Context c, Intent intent) {
    int session=intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID,-1);
    if (session>=0 && session!=AppUpdates.prefs(c).getInt("session",-1)) return;
    int status=intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
    if (status==PackageInstaller.STATUS_PENDING_USER_ACTION) {
      Intent confirmation=intent.getParcelableExtra(Intent.EXTRA_INTENT);
      if (!UpdateInstallActivity.deliver(status,confirmation))
        AppUpdates.notifyReady(c, AppUpdates.prefs(c).getString("name",""),confirmation);
    } else {
      UpdateInstallActivity.deliver(status,null);
      AppUpdates.prefs(c).edit().remove("session").apply();
      if (status==PackageInstaller.STATUS_SUCCESS) {
        AppUpdates.apk(c).delete();
        AppUpdates.prefs(c).edit().remove("ready").apply();
        c.getSystemService(android.app.NotificationManager.class).cancel(AppUpdates.NOTICE);
      }
    }
  }
}
