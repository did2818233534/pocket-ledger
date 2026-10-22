package dev.guga.updates;

import android.app.*;
import android.content.*;
import android.os.*;
import android.text.*;
import android.util.*;
import android.view.Gravity;
import android.widget.Button;

/** Fixed-size optional UI. Recreating this view always starts in check mode. */
public final class UpdateButton extends Button {
  public interface Details { void show(String message); }
  private final Handler handler=new Handler(Looper.getMainLooper());
  private boolean installAction;
  private int generation;
  private Details details;
  public UpdateButton(Context context) { this(context,null); }
  public UpdateButton(Context context,AttributeSet attrs) {
    super(context,attrs);
    UpdateStyle ui=new UpdateStyle(context);
    setText("检查更新"); setAllCaps(false); setSingleLine(false); setMaxLines(2);
    setGravity(Gravity.CENTER); setIncludeFontPadding(false); setPadding(ui.dp(12),0,ui.dp(12),0);
    setMinWidth(0); setMinimumWidth(0); setMinimumHeight(ui.dp(52)); setMinHeight(ui.dp(52));
    setBackground(ui.surface(UpdateStyle.SURFACE,16)); setTextColor(UpdateStyle.INK);
    setEllipsize(TextUtils.TruncateAt.END);
    setAutoSizeTextTypeUniformWithConfiguration(12,16,1,TypedValue.COMPLEX_UNIT_SP);
    setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_POLITE);
    setOnClickListener(v -> checkOrInstall());
  }
  public void setDetailsHandler(Details details) { this.details=details; }
  private Activity activity() {
    Context c=getContext();
    while(c instanceof ContextWrapper) { if(c instanceof Activity) return (Activity)c; c=((ContextWrapper)c).getBaseContext(); }
    return null;
  }
  private void checkOrInstall() {
    if(installAction && ReleaseUpdater.hasDownloadedUpdate(getContext())) {
      Activity activity=activity();
      if(activity!=null) ReleaseUpdater.installDownloaded(activity); else showDetails("安装更新需要 Activity 界面。");
      return;
    }
    installAction=false; setEnabled(false); setStatusText("检查更新中…");
    int request=++generation;
    final boolean[] finished={false}; final String[] shown={""};
    ReleaseUpdater.checkManually(getContext(),() -> finished[0]=true);
    Runnable refresh=new Runnable() { public void run() {
      if(request!=generation || !isAttachedToWindow()) return;
      boolean complete=finished[0] && !ReleaseUpdater.isRunning();
      installAction=complete && ReleaseUpdater.latestDownloadReady(getContext());
      String message=installAction ? "安装更新" : ReleaseUpdater.statusMessage();
      if(!message.isEmpty() && !message.equals(shown[0])) { shown[0]=message; setStatusText(message); }
      if(complete) setEnabled(true); else handler.postDelayed(this,400);
    }};
    handler.postDelayed(refresh,200);
  }
  /** Render status inside the button; overflow uses the details handler. */
  public void setStatusText(String message) {
    setText(message);
    post(() -> {
      if(!isAttachedToWindow() || !message.contentEquals(getText())) return;
      int width=getWidth()-getCompoundPaddingLeft()-getCompoundPaddingRight();
      int height=getHeight()-getCompoundPaddingTop()-getCompoundPaddingBottom();
      if(width<=0 || height<=0) return;
      TextPaint paint=new TextPaint(getPaint());
      paint.setTextSize(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP,12,getResources().getDisplayMetrics()));
      StaticLayout layout=StaticLayout.Builder.obtain(message,0,message.length(),paint,width)
        .setIncludePad(getIncludeFontPadding()).setLineSpacing(getLineSpacingExtra(),getLineSpacingMultiplier()).build();
      if(layout.getLineCount()>2 || layout.getHeight()>height) { setText("检查更新"); showDetails(message); }
    });
  }
  private void showDetails(String message) {
    if(details!=null) { details.show(message); return; }
    Activity a=activity(); if(a==null || a.isFinishing() || a.isDestroyed()) return;
    AlertDialog dialog=new AlertDialog.Builder(a).setTitle("更新详情").setMessage(message).setPositiveButton("知道了",null).create();
    dialog.show(); UpdateStyle ui=new UpdateStyle(a); dialog.getWindow().setBackgroundDrawable(ui.shape(UpdateStyle.BACKGROUND,28));
    ui.dialogAction(dialog.getButton(AlertDialog.BUTTON_POSITIVE),false);
  }
  protected void onDetachedFromWindow() {
    generation++; handler.removeCallbacksAndMessages(null); installAction=false; setEnabled(true); setText("检查更新");
    super.onDetachedFromWindow();
  }
}
