package dev.guga.updates;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.drawable.*;
import android.view.*;
import android.widget.*;

final class UpdateStyle {
  static final int INK = 0xFF243D35, MUTED = 0xFF85928A, ACCENT = 0xFF257D61;
  static final int BACKGROUND = 0xFFF6F7F3, SURFACE = 0xFFE9F2EB, LOW = 0xFFF1F6EF;
  static final int DANGER = 0xFFC64040, GAP = 12, CONTROL = 48, CARD = 24;
  final Context context;
  UpdateStyle(Context context) { this.context = context; }
  int dp(int n) { return Math.round(n * context.getResources().getDisplayMetrics().density); }
  GradientDrawable shape(int color, int radius) {
    GradientDrawable d = new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(radius)); return d;
  }
  RippleDrawable surface(int color, int radius) {
    return new RippleDrawable(ColorStateList.valueOf(0x22257D61), shape(color, radius), null);
  }
  void action(Button button, boolean primary) {
    button.setAllCaps(false); button.setTextSize(15);
    button.setTextColor(primary ? Color.WHITE : INK);
    button.setMinimumHeight(dp(CONTROL)); button.setMinHeight(dp(CONTROL));
    button.setPadding(dp(20), dp(8), dp(20), dp(8));
    button.setBackground(surface(primary ? ACCENT : SURFACE, CARD));
  }
  void dialogAction(Button button, boolean destructive) {
    button.setAllCaps(false); button.setTextSize(15);
    button.setTextColor(destructive ? DANGER : ACCENT);
    button.setMinimumHeight(dp(CONTROL)); button.setMinHeight(dp(CONTROL));
    button.setPadding(dp(16), dp(8), dp(16), dp(8));
    button.setBackground(new RippleDrawable(ColorStateList.valueOf(0x22257D61),
      null, shape(Color.WHITE, 24)));
  }
}
