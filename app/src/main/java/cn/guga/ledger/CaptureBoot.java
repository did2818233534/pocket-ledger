package cn.guga.ledger;

import android.content.*;

/**
 * JobScheduler forgets content-trigger jobs on reboot and app update; watch again, and catch up on
 * screenshots taken while nothing was watching (the scan only reads ones newer than the last seen).
 */
public class CaptureBoot extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if ((Intent.ACTION_BOOT_COMPLETED.equals(action) || Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) && Capture.enabled(context)) {
            Capture.schedule(context);
            Capture.runNow(context);
        }
    }
}
