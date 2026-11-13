package cn.guga.ledger;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

/** Handles the "记账" and "忽略" buttons on a recognized-expense notification without opening the app. */
public class CaptureAction extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){
        String id=intent.getStringExtra("draft");if(id==null)return;
        Context c=context.getApplicationContext();PendingResult result=goAsync();
        new Thread(()->{
            try{
                if(Capture.SAVE_DRAFT.equals(intent.getAction())){
                    String error=Capture.saveDraft(c,id);
                    toast(c,error.isEmpty()?"已记账":error+"，请打开小账确认");
                }else if(Capture.DISMISS_DRAFT.equals(intent.getAction()))Capture.forget(c,id);
            }finally{result.finish();}
        },"ledger-capture-action").start();
    }

    private static void toast(Context c,String text){new Handler(Looper.getMainLooper()).post(()->Toast.makeText(c,text,Toast.LENGTH_SHORT).show());}
}
