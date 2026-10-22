package dev.guga.updates;

import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Bundle;
import java.net.URI;

/** Configuration is read from the host manifest, including after process recreation. */
public final class UpdateConfig {
  public final String repository, manifestUrl, appName;
  public final int notificationIcon;
  public UpdateConfig(String repository,String manifestUrl,String appName,int notificationIcon) {
    this.repository=repository.replaceAll("/+$", "");
    requireHttps(this.repository);
    this.manifestUrl=manifestUrl==null || manifestUrl.isEmpty() ? this.repository+"/releases/latest/download/latest.json" : manifestUrl;
    requireHttps(this.manifestUrl);
    this.appName=appName; this.notificationIcon=notificationIcon;
  }
  private static void requireHttps(String value) {
    URI uri=URI.create(value);
    if(!"https".equals(uri.getScheme()) || uri.getHost()==null || uri.getUserInfo()!=null || uri.getFragment()!=null || uri.getQuery()!=null)
      throw new IllegalArgumentException("Updater endpoints must use HTTPS without credentials, query or fragment");
  }
  public static UpdateConfig read(Context c) {
    try {
      var info=c.getPackageManager().getApplicationInfo(c.getPackageName(),PackageManager.GET_META_DATA);
      Bundle meta=info.metaData==null ? Bundle.EMPTY : info.metaData;
      String repository=meta.getString("dev.guga.updates.REPOSITORY","");
      return new UpdateConfig(repository,meta.getString("dev.guga.updates.MANIFEST_URL",""),
        meta.getString("dev.guga.updates.APP_NAME",c.getPackageManager().getApplicationLabel(info).toString()),
        meta.getInt("dev.guga.updates.NOTIFICATION_ICON",android.R.drawable.stat_sys_download_done));
    } catch(PackageManager.NameNotFoundException e) { throw new IllegalStateException(e); }
  }
}
