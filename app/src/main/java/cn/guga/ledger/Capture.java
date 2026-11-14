package cn.guga.ledger;

import android.app.*;
import android.app.job.*;
import android.content.*;
import android.database.Cursor;
import android.graphics.*;
import android.net.Uri;
import android.os.Build;
import android.provider.MediaStore;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.*;

/**
 * Screenshot capture: a new screenshot from a payment app is sent to the self-hosted OCR service,
 * and the parsed amount becomes a local draft awaiting confirmation. Drafts never sync; only the
 * expense saved from a draft does, through the normal save path.
 */
public final class Capture {
    static final String PREFS="capture",CHANNEL="capture",OPEN_DRAFT="cn.guga.ledger.OPEN_DRAFT",
        SAVE_DRAFT="cn.guga.ledger.SAVE_DRAFT",DISMISS_DRAFT="cn.guga.ledger.DISMISS_DRAFT";
    static final int WATCH_JOB=4201,RUN_JOB=4202,LIST_NOTIFICATION=4203;
    /** HyperOS/MIUI append the screenshot source to the name: a package, or e.g. "lockscreen". */
    private static final Pattern PACKAGE=Pattern.compile("_([a-zA-Z][\\w.]*)\\.(?:jpe?g|png|webp)$");
    static final Map<String,String> PAY_APPS=new LinkedHashMap<>();
    static {
        String[][] apps={{"com.tencent.mm","微信"},{"com.eg.android.AlipayGphone","支付宝"},{"com.unionpay","云闪付"},
            {"com.sankuai.meituan","美团"},{"com.sankuai.meituan.takeoutnew","美团外卖"},{"me.ele","饿了么"},
            {"com.taobao.taobao","淘宝"},{"com.tmall.wireless","天猫"},{"com.jingdong.app.mall","京东"},{"com.xunmeng.pinduoduo","拼多多"},
            {"com.sdu.didi.psnger","滴滴出行"},{"com.MobileTicket","铁路12306"},{"cmb.pb","招商银行"},{"com.icbc","工商银行"},
            {"com.chinamworld.main","建设银行"},{"com.android.bankabc","农业银行"},{"com.chinamworld.bocmbci","中国银行"},
            {"com.bankcomm.Bankcomm","交通银行"},{"com.yitong.mbank.psbc","邮储银行"}};
        for(String[] app:apps)PAY_APPS.put(app[0],app[1]);
    }
    private Capture(){}

    static SharedPreferences prefs(Context c){return c.getSharedPreferences(PREFS,0);}
    static boolean enabled(Context c){return prefs(c).getBoolean("enabled",false);}
    static String imagePermission(){return Build.VERSION.SDK_INT>=33?"android.permission.READ_MEDIA_IMAGES":"android.permission.READ_EXTERNAL_STORAGE";}
    static boolean canReadImages(Context c){return c.checkSelfPermission(imagePermission())==android.content.pm.PackageManager.PERMISSION_GRANTED;}
    static String appName(String pkg){String name=PAY_APPS.get(pkg);return name!=null?name:pkg==null?"":pkg;}

    static JSONObject state(Context c) throws JSONException {
        SharedPreferences p=prefs(c);
        return new JSONObject().put("enabled",p.getBoolean("enabled",false)).put("url",p.getString("url",""))
            .put("hasToken",!p.getString("token","").isEmpty()).put("allApps",p.getBoolean("allApps",false))
            .put("permission",canReadImages(c)).put("deleteAfter",p.getBoolean("deleteAfter",false)).put("canDelete",canDelete())
            .put("unrestricted",c.getSystemService(android.os.PowerManager.class).isIgnoringBatteryOptimizations(c.getPackageName()));
    }

    /** Validates and stores settings; returns an error message or "". */
    /** Deleting screenshots owned by the system screenshot app needs all-files access (Android 11+). */
    static boolean canDelete(){return Build.VERSION.SDK_INT>=30&&android.os.Environment.isExternalStorageManager();}
    static boolean cleanup(Context c){return prefs(c).getBoolean("deleteAfter",false)&&canDelete();}

    static String configure(Context c,boolean enable,String url,String token,boolean allApps,boolean deleteAfter){
        url=url.trim().replaceAll("/+$","");
        if(enable||!url.isEmpty()){
            try{URL u=new URL(url);if(!u.getProtocol().matches("https?")||u.getHost().isEmpty())throw new MalformedURLException();}
            catch(MalformedURLException e){return "请填写识别服务地址，例如 http://192.168.1.10:18086";}
        }
        SharedPreferences p=prefs(c);SharedPreferences.Editor edit=p.edit().putString("url",url).putBoolean("allApps",allApps).putBoolean("enabled",enable).putBoolean("deleteAfter",deleteAfter);
        if(token!=null&&!token.isEmpty())edit.putString("token",token.trim());
        // Only screenshots taken after switching on are read; older ones are never uploaded.
        if(enable&&!p.getBoolean("enabled",false))edit.putLong("lastSeen",System.currentTimeMillis()/1000);
        edit.commit();schedule(c);return "";
    }

    static void schedule(Context c){
        JobScheduler jobs=c.getSystemService(JobScheduler.class);
        if(!enabled(c)){jobs.cancel(WATCH_JOB);return;}
        jobs.schedule(new JobInfo.Builder(WATCH_JOB,new ComponentName(c,CaptureJob.class))
            .addTriggerContentUri(new JobInfo.TriggerContentUri(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,JobInfo.TriggerContentUri.FLAG_NOTIFY_FOR_DESCENDANTS))
            .setTriggerContentUpdateDelay(300).setTriggerContentMaxDelay(2000).build());
    }

    static void runNow(Context c){
        c.getSystemService(JobScheduler.class).schedule(new JobInfo.Builder(RUN_JOB,new ComponentName(c,CaptureJob.class))
            .setOverrideDeadline(0).build());
    }

    static String packageOf(String fileName){Matcher m=PACKAGE.matcher(fileName==null?"":fileName);return m.find()?m.group(1):"";}

    /** Queues screenshots added since the last scan. */
    static void scan(Context c){
        if(!enabled(c)||!canReadImages(c))return;
        SharedPreferences p=prefs(c);long last=p.getLong("lastSeen",System.currentTimeMillis()/1000),newest=last;boolean all=p.getBoolean("allApps",false);
        String pathColumn=Build.VERSION.SDK_INT>=29?MediaStore.Images.Media.RELATIVE_PATH:MediaStore.Images.Media.DATA;
        String[] projection={MediaStore.Images.Media._ID,MediaStore.Images.Media.DISPLAY_NAME,MediaStore.Images.Media.DATE_ADDED,MediaStore.Images.Media.DATE_TAKEN};
        try(Cursor cursor=c.getContentResolver().query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,projection,
                MediaStore.Images.Media.DATE_ADDED+">? AND "+pathColumn+" LIKE ?",new String[]{String.valueOf(last),"%Screenshot%"},
                MediaStore.Images.Media.DATE_ADDED+" ASC")){
            if(cursor==null)return;
            LedgerDb db=LedgerDb.get(c);
            while(cursor.moveToNext()){
                long id=cursor.getLong(0),added=cursor.getLong(2),taken=cursor.getLong(3);String name=cursor.getString(1),app=packageOf(name);
                newest=Math.max(newest,added);
                // Names without a package suffix cannot be filtered, so they are tried rather than missed.
                if(!all&&!app.isEmpty()&&!PAY_APPS.containsKey(app))continue;
                db.queueDraft("media:"+id,ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,id).toString(),app,taken>0?taken:added*1000);
            }
        }
        if(newest>last)p.edit().putLong("lastSeen",newest).apply();
    }

    /** Copies a shared or picked image into private storage so it outlives the caller's grant. */
    static void queueShared(Context c,Uri uri) throws IOException {
        File dir=new File(c.getFilesDir(),"capture");if(!dir.isDirectory()&&!dir.mkdirs())throw new IOException("无法保存截图");
        String id=UUID.randomUUID().toString();File file=new File(dir,id+".img");
        try(InputStream in=c.getContentResolver().openInputStream(uri);OutputStream out=new FileOutputStream(file)){
            if(in==null)throw new FileNotFoundException();
            byte[] buffer=new byte[16384];int n;long total=0;
            while((n=in.read(buffer))!=-1){total+=n;if(total>40L<<20)throw new IOException("图片太大");out.write(buffer,0,n);}
        }
        LedgerDb.get(c).queueDraft("share:"+id,file.getAbsolutePath(),"",System.currentTimeMillis());
        runNow(c);
    }

    static void processPending(Context c){
        LedgerDb db=LedgerDb.get(c);
        for(String[] draft:db.pendingDrafts()){
            String id=draft[0],uri=draft[1];boolean automatic=draft[2].startsWith("media:");
            try{
                JSONObject result=post(c,"/parse",upload(c,uri),day(Long.parseLong(draft[4])));
                // A bill list (often a long screenshot of 账单) becomes one draft per expense row.
                if(result.optJSONArray("entries")!=null){importList(c,db,draft,automatic,result.getJSONArray("entries"),result.optInt("skipped"));continue;}
                JSONObject fields=result.getJSONObject("fields");
                Object amount=fields.opt("amount");boolean found=amount!=null&&amount!=JSONObject.NULL;
                // A screenshot the user did not hand over explicitly only counts when it clearly shows a payment.
                if(automatic&&(!found||!fields.optBoolean("confident"))){forget(c,id);continue;}
                // The same bill captured twice (screenshot, then shared) keeps the first draft.
                if(found&&duplicate(db,id,fields)){if(automatic&&cleanup(c))deleteMedia(c,uri);forget(c,id);continue;}
                String kind=fields.optString("kind");
                String status=!found?"error":"income".equals(kind)?"income":"transfer".equals(kind)?"transfer":"ready";
                // Keep a private copy for checking the draft, then clear the bill out of the gallery.
                if(automatic&&found&&cleanup(c)){String kept=keepCopy(c,id,uri);if(kept!=null){db.moveDraft(id,kept);deleteMedia(c,uri);}}
                db.finishDraft(id,status,"error".equals(status)?"截图里没有找到金额":"",fields);
                if("ready".equals(status)||"income".equals(status))notifyDraft(c,db.draft(id));
            }catch(FileNotFoundException e){db.finishDraft(id,"error","截图已被删除",null);}
            catch(TooLarge e){db.finishDraft(id,"error","长截图太大，请分段截取",null);}
            catch(HttpStatus e){db.finishDraft(id,"error",e.code==401?"识别服务口令不对":"识别服务出错（"+e.code+"）",null);}
            catch(IOException e){db.finishDraft(id,"error","连不上识别服务，稍后自动重试",null);}
            catch(Exception e){db.finishDraft(id,"error","识别失败",null);}
        }
    }

    private static void importList(Context c,LedgerDb db,String[] draft,boolean automatic,JSONArray entries,int skipped) throws JSONException {
        String id=draft[0],uri=draft[1],source=draft[2],app=draft[3];long takenAt=Long.parseLong(draft[4]);
        boolean clean=automatic&&cleanup(c);String kept=uri;
        if(clean){String copy=keepCopy(c,id,uri);if(copy!=null)kept=copy;}
        // Rows imported before (even if dismissed since), already in the ledger, or waiting as another
        // draft are not offered again, so overlapping long screenshots only add the new rows.
        List<String> imported=importedKeys(c),added=new ArrayList<>();
        JSONArray pending=db.drafts();int fresh=0,known=0;long total=0;
        for(int i=0;i<entries.length();i++){
            JSONObject f=entries.getJSONObject(i);long amount=f.optLong("amount");String date=str(f,"date"),time=str(f,"time");
            boolean income="income".equals(str(f,"kind"));
            String key=(income?"income|":"")+amount+"|"+date+"|"+(time.length()>=5?time.substring(0,5):time);
            if(imported.contains(key)||added.contains(key)||(!date.isEmpty()&&db.hasEntry(amount,date,income))||waiting(pending,f)){known++;continue;}
            added.add(key);
            if(db.addDraft(source+"#"+i,kept,app,takenAt,income?"income":"ready",f)!=null){fresh++;total+=amount;}
        }
        rememberKeys(c,imported,added);
        db.removeDraft(id);
        if(kept.startsWith(c.getFilesDir().getAbsolutePath())&&db.draftsUsing(kept)==0)new File(kept).delete();
        if(clean&&(!kept.equals(uri)||fresh==0))deleteMedia(c,uri);
        notifyList(c,fresh,total,known,skipped);
    }

    /** Another draft for the same payment: same amount and day, and the same minute when both have a time. */
    private static boolean waiting(JSONArray drafts,JSONObject f){
        String date=str(f,"date"),time=str(f,"time");
        for(int i=0;i<drafts.length();i++){
            JSONObject other=drafts.optJSONObject(i),g=other==null?null:other.optJSONObject("fields");
            if(g==null||!str(g,"kind").equals(str(f,"kind"))||g.optLong("amount",-1)!=f.optLong("amount",-2)||!str(g,"date").equals(date))continue;
            String when=str(g,"time");
            if(time.length()<5||when.length()<5||when.substring(0,5).equals(time.substring(0,5)))return true;
        }
        return false;
    }

    private static List<String> importedKeys(Context c){
        List<String> keys=new ArrayList<>();
        try{JSONArray a=new JSONArray(prefs(c).getString("imported","[]"));for(int i=0;i<a.length();i++)keys.add(a.getString(i));}catch(JSONException ignored){}
        return keys;
    }
    private static void rememberKeys(Context c,List<String> keys,List<String> added){
        if(added.isEmpty())return;
        keys.addAll(added);List<String> recent=keys.subList(Math.max(0,keys.size()-1000),keys.size());
        prefs(c).edit().putString("imported",new JSONArray(recent).toString()).apply();
    }

    private static void notifyList(Context c,int added,long total,int known,int skipped){
        NotificationManager nm=c.getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL,"截图记账",NotificationManager.IMPORTANCE_HIGH));
        String title=added>0?String.format(Locale.ROOT,"账单截图里有 %d 笔新收支",added):"账单截图里没有新的记录";
        List<String> parts=new ArrayList<>();
        if(known>0)parts.add(known+" 笔已记过或已导入");
        if(skipped>0)parts.add(skipped+" 笔收入、理财转账或已关闭的订单");
        String text=(parts.isEmpty()?"":"已跳过 "+String.join("，",parts)+"。")+(added>0?"点按逐条确认，或在小账里“全部记账”":"");
        Intent open=new Intent(c,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent tap=PendingIntent.getActivity(c,LIST_NOTIFICATION,open,PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        nm.notify(LIST_NOTIFICATION,new Notification.Builder(c,CHANNEL).setSmallIcon(R.drawable.ic_ledger).setContentTitle(title)
            .setContentText(text).setStyle(new Notification.BigTextStyle().bigText(text))
            .setContentIntent(tap).setAutoCancel(true).setCategory(Notification.CATEGORY_REMINDER).build());
    }

    private static String day(long millis){return new java.text.SimpleDateFormat("yyyy-MM-dd",Locale.ROOT).format(new Date(millis));}

    private static String keepCopy(Context c,String id,String uri){
        File dir=new File(c.getFilesDir(),"capture");if(!dir.isDirectory()&&!dir.mkdirs())return null;
        File file=new File(dir,id+".img");
        try(InputStream in=open(c,uri);OutputStream out=new FileOutputStream(file)){
            byte[] buffer=new byte[16384];int n;while((n=in.read(buffer))!=-1)out.write(buffer,0,n);
            return file.getAbsolutePath();
        }catch(IOException e){file.delete();return null;}
    }

    static boolean deleteMedia(Context c,String uri){
        if(!uri.startsWith("content://media/"))return false;
        try{if(c.getContentResolver().delete(Uri.parse(uri),null,null)>0)return true;}catch(Exception ignored){}
        // Some ROMs refuse MediaStore deletes even with all-files access; fall back to the file itself.
        try(Cursor cursor=c.getContentResolver().query(Uri.parse(uri),new String[]{MediaStore.Images.Media.DATA},null,null,null)){
            if(cursor!=null&&cursor.moveToFirst()){
                File file=new File(cursor.getString(0));
                if(file.delete()){android.media.MediaScannerConnection.scanFile(c,new String[]{file.getAbsolutePath()},null,null);return true;}
            }
        }catch(Exception ignored){}
        return false;
    }

    /** Decodes a draft's screenshot scaled to the given width for on-screen checking. */
    static Bitmap preview(Context c,String id,int width) throws IOException {
        LedgerDb db=LedgerDb.get(c);String uri=db.draftUri(id);if(uri==null)throw new FileNotFoundException();
        JSONObject draft=db.draft(id),fields=draft==null?null:draft.optJSONObject("fields");
        JSONArray region=fields==null?null:fields.optJSONArray("region");
        BitmapFactory.Options bounds=new BitmapFactory.Options();bounds.inJustDecodeBounds=true;
        try(InputStream in=open(c,uri)){BitmapFactory.decodeStream(in,null,bounds);}
        int w=bounds.outWidth,h=bounds.outHeight;
        if(w>0&&(region!=null||h>w*TALL)){
            // A long screenshot is decoded only around the row (or its first screen), never whole.
            float scale=region!=null&&region.optInt(2)>0?(float)w/region.optInt(2):1f;
            int top=region==null?0:Math.round(region.optInt(0)*scale)-w/10,bottom=region==null?Math.round(w*2.2f):Math.round(region.optInt(1)*scale)+w/20;
            Rect rect=new Rect(0,Math.max(0,top),w,Math.min(h,Math.max(top+1,bottom)));
            BitmapFactory.Options options=new BitmapFactory.Options();options.inSampleSize=1;
            while(w/(options.inSampleSize*2)>=width)options.inSampleSize*=2;
            try(InputStream in=open(c,uri)){
                BitmapRegionDecoder decoder=Build.VERSION.SDK_INT>=31?BitmapRegionDecoder.newInstance(in):BitmapRegionDecoder.newInstance(in,false);
                if(decoder==null)throw new IOException("不是图片");
                try{Bitmap part=decoder.decodeRegion(rect,options);if(part==null)throw new IOException("不是图片");return part;}finally{decoder.recycle();}
            }
        }
        byte[] data=jpeg(c,uri);Bitmap bitmap=BitmapFactory.decodeByteArray(data,0,data.length);
        if(bitmap==null)throw new IOException("不是图片");
        if(bitmap.getWidth()>width){Bitmap scaled=Bitmap.createScaledBitmap(bitmap,width,Math.round(bitmap.getHeight()*(float)width/bitmap.getWidth()),true);bitmap.recycle();bitmap=scaled;}
        return bitmap;
    }

    private static boolean duplicate(LedgerDb db,String id,JSONObject f){
        try{
            JSONArray drafts=db.drafts();
            for(int i=0;i<drafts.length();i++){
                JSONObject other=drafts.getJSONObject(i),g=other.getJSONObject("fields");
                if(other.getString("id").equals(id)||!str(g,"kind").equals(str(f,"kind"))||g.optLong("amount",-1)!=f.optLong("amount",-2))continue;
                if(g.optString("date").equals(f.optString("date"))&&g.optString("time").equals(f.optString("time"))
                    &&g.optString("merchant").equals(f.optString("merchant")))return true;
            }
        }catch(JSONException ignored){}
        return false;
    }

    /** Decodes the screenshot and re-encodes it at most 1080 px wide: enough for UI text, a fraction of the upload. */
    static byte[] jpeg(Context c,String uri) throws IOException {
        BitmapFactory.Options bounds=new BitmapFactory.Options();bounds.inJustDecodeBounds=true;
        try(InputStream in=open(c,uri)){BitmapFactory.decodeStream(in,null,bounds);}
        if(bounds.outWidth<=0)throw new IOException("不是图片");
        BitmapFactory.Options options=new BitmapFactory.Options();options.inSampleSize=1;
        while(bounds.outWidth/(options.inSampleSize*2)>=1080)options.inSampleSize*=2;
        Bitmap bitmap;try(InputStream in=open(c,uri)){bitmap=BitmapFactory.decodeStream(in,null,options);}
        if(bitmap==null)throw new IOException("不是图片");
        if(bitmap.getWidth()>1080){Bitmap scaled=Bitmap.createScaledBitmap(bitmap,1080,Math.round(bitmap.getHeight()*1080f/bitmap.getWidth()),true);bitmap.recycle();bitmap=scaled;}
        ByteArrayOutputStream out=new ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.JPEG,88,out);bitmap.recycle();
        return out.toByteArray();
    }

    private static InputStream open(Context c,String uri) throws IOException {
        if(uri.startsWith("/"))return new FileInputStream(uri);
        InputStream in=c.getContentResolver().openInputStream(Uri.parse(uri));
        if(in==null)throw new FileNotFoundException(uri);
        return in;
    }

    static final class HttpStatus extends IOException {final int code;HttpStatus(int code){super("HTTP "+code);this.code=code;}}

    /** Phone screens are about 2.2:1; anything taller is a scrolling (long) screenshot. */
    private static final float TALL=2.4f;
    private static final class TooLarge extends IOException {TooLarge(){super("too large");}}

    /** Long screenshots go up as the original file: decoding ten screens at once can exhaust memory, and the service tiles them. */
    static byte[] upload(Context c,String uri) throws IOException {
        BitmapFactory.Options bounds=new BitmapFactory.Options();bounds.inJustDecodeBounds=true;
        try(InputStream in=open(c,uri)){BitmapFactory.decodeStream(in,null,bounds);}
        if(bounds.outWidth<=0)throw new IOException("不是图片");
        if(bounds.outHeight<=bounds.outWidth*TALL)return jpeg(c,uri);
        try(InputStream in=open(c,uri)){return readAll(in,15<<20);}
        catch(IOException e){if("响应太大".equals(e.getMessage()))throw new TooLarge();throw e;}
    }

    static JSONObject post(Context c,String path,byte[] body) throws IOException, JSONException {return post(c,path,body,null);}
    static JSONObject post(Context c,String path,byte[] body,String day) throws IOException, JSONException {
        SharedPreferences p=prefs(c);
        HttpURLConnection conn=(HttpURLConnection)new URL(p.getString("url","")+path).openConnection();
        try{
            conn.setConnectTimeout(6000);conn.setReadTimeout(60000);conn.setDoOutput(true);conn.setFixedLengthStreamingMode(body.length);
            conn.setRequestProperty("Content-Type","image/jpeg");
            String token=p.getString("token","");if(!token.isEmpty())conn.setRequestProperty("X-Token",token);
            if(day!=null)conn.setRequestProperty("X-Date",day);
            conn.setRequestProperty("X-Cashflow","1");
            try(OutputStream out=conn.getOutputStream()){out.write(body);}
            if(conn.getResponseCode()!=200)throw new HttpStatus(conn.getResponseCode());
            try(InputStream in=conn.getInputStream()){return new JSONObject(new String(readAll(in,4<<20),StandardCharsets.UTF_8));}
        }finally{conn.disconnect();}
    }

    /** Returns "" when the service answers, otherwise a short reason. */
    static String health(Context c){
        try{
            HttpURLConnection conn=(HttpURLConnection)new URL(prefs(c).getString("url","")+"/health").openConnection();
            conn.setConnectTimeout(5000);conn.setReadTimeout(5000);
            try{return conn.getResponseCode()==200?"":"识别服务返回 "+conn.getResponseCode();}finally{conn.disconnect();}
        }catch(MalformedURLException e){return "请先填写识别服务地址";}
        catch(IOException e){return "连不上识别服务："+e.getClass().getSimpleName();}
    }

    private static byte[] readAll(InputStream in,int max) throws IOException {
        ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buffer=new byte[8192];int n;
        while((n=in.read(buffer))!=-1){out.write(buffer,0,n);if(out.size()>max)throw new IOException("响应太大");}
        return out.toByteArray();
    }

    static void notifyDraft(Context c,JSONObject draft){
        if(draft==null)return;
        NotificationManager nm=c.getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL,"截图记账",NotificationManager.IMPORTANCE_HIGH));
        JSONObject f=draft.optJSONObject("fields");if(f==null)return;
        String id=draft.optString("id"),merchant=str(f,"merchant"),app=appName(draft.optString("app"));
        Intent open=new Intent(c,MainActivity.class).setAction(OPEN_DRAFT).putExtra("draft",id)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent tap=PendingIntent.getActivity(c,id.hashCode(),open,PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        // One-tap saving only when nothing needs checking: a CNY amount with no same-day expense of that amount.
        boolean direct=cny(f)&&!LedgerDb.get(c).hasEntry(f.optLong("amount"),draftDate(draft),"income".equals(draft.optString("status")));
        String text=(merchant.isEmpty()?"":merchant+" · ")+(app.isEmpty()?"":app+" · ")+(direct?"点“记账”直接保存":"点按打开核对");
        Notification.Builder builder=new Notification.Builder(c,CHANNEL).setSmallIcon(R.drawable.ic_ledger)
            .setContentTitle(String.format(Locale.ROOT,"识别到%s ¥%.2f","income".equals(draft.optString("status"))?"收入":"支出",f.optLong("amount")/100.0)).setContentText(text)
            .setContentIntent(tap).setAutoCancel(true).setCategory(Notification.CATEGORY_REMINDER);
        if(direct)builder.addAction(new Notification.Action.Builder(null,"记账",action(c,id,SAVE_DRAFT)).build());
        builder.addAction(new Notification.Action.Builder(null,"忽略",action(c,id,DISMISS_DRAFT)).build());
        nm.notify(id.hashCode(),builder.build());
    }

    private static PendingIntent action(Context c,String id,String action){
        Intent intent=new Intent(c,CaptureAction.class).setAction(action).putExtra("draft",id);
        return PendingIntent.getBroadcast(c,(action+id).hashCode(),intent,PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
    }

    /** Saves a ready draft as a daily expense of the current user; returns an error message or "". */
    static String saveDraft(Context c,String id){
        LedgerDb db=LedgerDb.get(c);JSONObject d=db.draft(id);
        if(d==null)return "这条识别记录已处理";
        JSONObject f=d.optJSONObject("fields");
        if((!"ready".equals(d.optString("status"))&&!"income".equals(d.optString("status")))||f==null||f.optLong("amount")<=0)return "这条记录需要打开核对";
        if(!cny(f))return "外币账单请打开核对金额";
        String merchant=str(f,"merchant"),detail=str(f,"detail");
        String note=merchant.isEmpty()?detail:detail.isEmpty()?merchant:merchant+" · "+detail;
        try{
            db.save(new JSONObject().put("amount",f.getLong("amount")).put("at",draftDate(d)).put("category","income".equals(d.optString("status"))?"income":"daily")
                .put("primaryNote",clip(str(f,"primaryNote"),60)).put("note",clip(note,200)).toString());
        }catch(Exception e){return "保存失败";}
        forget(c,id);
        if(!c.getSharedPreferences("sync",0).getString("key","").isEmpty())SyncService.requestQuietly(c);
        return "";
    }

    static String draftDate(JSONObject draft){
        JSONObject f=draft.optJSONObject("fields");String date=f==null?"":str(f,"date");
        if(date.matches("\\d{4}-\\d{2}-\\d{2}"))return date;
        return new java.text.SimpleDateFormat("yyyy-MM-dd",Locale.ROOT).format(new Date(draft.optLong("takenAt",System.currentTimeMillis())));
    }
    private static boolean cny(JSONObject f){String currency=str(f,"currency");return currency.isEmpty()||"CNY".equals(currency);}
    /** optString turns JSON null into "null"; parsed fields use null for "not found". */
    private static String str(JSONObject f,String key){return f.isNull(key)?"":f.optString(key).trim();}
    private static String clip(String s,int max){return s.length()>max?s.substring(0,max):s;}

    static void forget(Context c,String id){
        c.getSystemService(NotificationManager.class).cancel(id.hashCode());
        LedgerDb db=LedgerDb.get(c);String uri=db.removeDraft(id);
        // Rows imported from one long screenshot share its private copy; it goes with the last of them.
        if(uri!=null&&uri.startsWith(c.getFilesDir().getAbsolutePath())&&db.draftsUsing(uri)==0)new File(uri).delete();
    }
}
