package cn.guga.ledger;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.widget.Toast;

/** "Share to 小账" for any screenshot: queue it for recognition and get out of the way. */
public class ShareActivity extends Activity {
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        Uri uri = android.os.Build.VERSION.SDK_INT >= 33
            ? getIntent().getParcelableExtra(Intent.EXTRA_STREAM, Uri.class)
            : getIntent().getParcelableExtra(Intent.EXTRA_STREAM);
        String message;
        if (uri == null) message = "没有收到图片";
        else if (Capture.prefs(this).getString("url","").isEmpty()) message = "请先在 设置 → 截图记账 填写识别服务地址";
        else {
            // Copy now: the read grant from the sharing app ends with this activity.
            try { Capture.queueShared(getApplicationContext(), uri); message = "正在识别，完成后通知你确认"; }
            catch (Exception e) { message = "图片读取失败"; }
        }
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
        finish();
    }
}
