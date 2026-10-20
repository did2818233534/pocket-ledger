package cn.guga.ledger;

import android.content.*;
import android.database.Cursor;
import android.database.sqlite.*;
import org.json.*;
import java.util.UUID;
import java.time.LocalDateTime;

public final class LedgerDb extends SQLiteOpenHelper {
    public static final String USER_ONE="00000000-0000-4000-8000-000000000001";
    private static LedgerDb instance;
    public static synchronized LedgerDb get(Context c) {
        if (instance == null) instance = new LedgerDb(c.getApplicationContext());
        return instance;
    }
    private LedgerDb(Context c) { super(c, "ledger.db", null, 5); }
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE entries(id TEXT PRIMARY KEY, amount INTEGER NOT NULL, at TEXT NOT NULL, category TEXT NOT NULL, note TEXT NOT NULL)");
        db.execSQL("CREATE TABLE meta(device TEXT NOT NULL, revision INTEGER NOT NULL)");
        db.execSQL("INSERT INTO meta VALUES(?,0)", new Object[]{UUID.randomUUID().toString()});
        onUpgrade(db,1,5);
        String initial=UUID.randomUUID().toString();
        db.execSQL("UPDATE users SET id=?",new Object[]{initial});
        db.execSQL("UPDATE meta SET currentUser=?",new Object[]{initial});
    }
    public void onUpgrade(SQLiteDatabase db, int a, int b) {
        if(a<2){
            db.execSQL("ALTER TABLE entries ADD COLUMN owner TEXT NOT NULL DEFAULT '"+USER_ONE+"'");
            db.execSQL("ALTER TABLE entries ADD COLUMN version INTEGER NOT NULL DEFAULT 1");
            db.execSQL("ALTER TABLE entries ADD COLUMN actor TEXT NOT NULL DEFAULT ''");
            db.execSQL("ALTER TABLE entries ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0");
            db.execSQL("ALTER TABLE meta ADD COLUMN clock INTEGER NOT NULL DEFAULT 1");
            db.execSQL("ALTER TABLE meta ADD COLUMN currentUser TEXT NOT NULL DEFAULT '"+USER_ONE+"'");
            db.execSQL("UPDATE meta SET clock=revision+2");
            db.execSQL("UPDATE entries SET version=(SELECT clock FROM meta),actor=(SELECT device FROM meta)");
            db.execSQL("CREATE TABLE users(id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL, actor TEXT NOT NULL)");
            db.execSQL("INSERT INTO users VALUES(?,?,1,?)",new Object[]{USER_ONE,"用户一",USER_ONE});
        }
        if(a<3){
            db.execSQL("ALTER TABLE users ADD COLUMN avatar TEXT NOT NULL DEFAULT ''");
            db.execSQL("ALTER TABLE users ADD COLUMN avatarAt INTEGER NOT NULL DEFAULT 0");
        }
        if(a<4){
            db.execSQL("CREATE TABLE users_current(id TEXT PRIMARY KEY,name TEXT NOT NULL,nameAt INTEGER NOT NULL,avatar TEXT NOT NULL DEFAULT '',avatarAt INTEGER NOT NULL DEFAULT 0,pending INTEGER NOT NULL DEFAULT 0)");
            db.execSQL("INSERT INTO users_current SELECT id,name,CASE WHEN version=0 THEN 0 ELSE ? END,avatar,avatarAt,CASE WHEN version=0 THEN 1 ELSE 0 END FROM users",new Object[]{System.currentTimeMillis()});
            db.execSQL("DROP TABLE users");db.execSQL("ALTER TABLE users_current RENAME TO users");
        }
        if(a<5)db.execSQL("ALTER TABLE entries ADD COLUMN primaryNote TEXT NOT NULL DEFAULT ''");
    }
    public synchronized JSONObject snapshot() throws JSONException {
        JSONObject result=syncSnapshot(); JSONArray visible=new JSONArray(),rows=result.getJSONArray("records");
        for(int i=0;i<rows.length();i++)if(!rows.getJSONObject(i).getBoolean("deleted"))visible.put(rows.getJSONObject(i));
        result.remove("records");
        try(Cursor c=getReadableDatabase().rawQuery("SELECT currentUser FROM meta",null)){c.moveToFirst();result.put("currentUser",c.getString(0));}
        return result.put("entries",visible).put("users",profiles(true));
    }
    public synchronized JSONObject syncSnapshot() throws JSONException {
        JSONObject result = new JSONObject().put("protocol",4);
        SQLiteDatabase db = getReadableDatabase();
        try (Cursor c = db.rawQuery("SELECT device,revision FROM meta", null)) {
            c.moveToFirst(); result.put("device", c.getString(0)); result.put("revision", c.getLong(1));
        }
        JSONArray records = new JSONArray(),users=new JSONArray();
        try (Cursor c = db.rawQuery("SELECT id,amount,at,category,note,owner,version,actor,deleted,primaryNote FROM entries ORDER BY at DESC,id", null)) {
            while (c.moveToNext()) records.put(new JSONObject().put("id",c.getString(0)).put("amount",c.getLong(1))
                .put("at",c.getString(2)).put("category",c.getString(3)).put("note",c.getString(4))
                .put("owner",c.getString(5)).put("version",c.getLong(6)).put("actor",c.getString(7)).put("deleted",c.getInt(8)!=0).put("primaryNote",c.getString(9)));
        }
        JSONArray subscriptions=new JSONArray();
        try(Cursor c=db.rawQuery("SELECT id FROM users ORDER BY id",null)){while(c.moveToNext())subscriptions.put(c.getString(0));}
        return result.put("records", records).put("users",profiles(false)).put("subscriptions",subscriptions);
    }
    private JSONArray profiles(boolean pending) throws JSONException {
        JSONArray users=new JSONArray();
        try(Cursor c=getReadableDatabase().rawQuery("SELECT id,name,nameAt,avatar,avatarAt,pending FROM users "+(pending?"":"WHERE pending=0 ")+"ORDER BY id",null)){
            while(c.moveToNext()){
                JSONObject u=new JSONObject().put("id",c.getString(0)).put("name",c.getString(1)).put("nameAt",c.getLong(2)).put("avatar",c.getString(3)).put("avatarAt",c.getLong(4));
                if(pending)u.put("pending",c.getInt(5)!=0);users.put(u);
            }
        }
        return users;
    }
    private boolean subscribed(String id){
        try(Cursor c=getReadableDatabase().rawQuery("SELECT id FROM users WHERE id=?",new String[]{id})){return c.moveToFirst();}
    }
    private void validUser(String id){
        UUID.fromString(id);
        try(Cursor c=getReadableDatabase().rawQuery("SELECT id FROM users WHERE id=? AND pending=0",new String[]{id})){
            if(!c.moveToFirst())throw new IllegalArgumentException("请选择记账用户");
        }
    }
    private void validEntry(JSONObject e) throws Exception {
        UUID.fromString(e.getString("id")); validUser(e.getString("owner"));
        LocalDateTime.parse(e.getString("at"));
        long amount=e.getLong("amount");
        if(amount<1||amount>99999999999L||!e.getString("category").matches("daily|extra|claim|giving")||e.getString("note").length()>200||e.optString("primaryNote").length()>60)throw new IllegalArgumentException("无效账单");
    }
    private ContentValues entryValues(JSONObject e) throws Exception {
        validEntry(e); ContentValues v=new ContentValues();
        for(String key:new String[]{"id","at","category","note","owner","actor"})v.put(key,e.getString(key));
        v.put("primaryNote",e.optString("primaryNote",""));v.put("amount",e.getLong("amount"));v.put("version",e.getLong("version"));v.put("deleted",e.getBoolean("deleted")?1:0);return v;
    }
    private void stamp(SQLiteDatabase db,ContentValues v){
        db.execSQL("UPDATE meta SET clock=clock+1,revision=revision+1");
        try(Cursor c=db.rawQuery("SELECT clock,device FROM meta",null)){c.moveToFirst();v.put("version",c.getLong(0));v.put("actor",c.getString(1));}
    }
    public synchronized void save(String raw) throws Exception {
        JSONObject e=new JSONObject(raw);SQLiteDatabase db=getWritableDatabase();
        String id=e.optString("id");if(id.isEmpty())id=UUID.randomUUID().toString();e.put("id",id);
        if(!e.has("owner")){
            try(Cursor c=db.rawQuery("SELECT owner FROM entries WHERE id=?",new String[]{id})){
                if(c.moveToFirst())e.put("owner",c.getString(0));else try(Cursor m=db.rawQuery("SELECT currentUser FROM meta",null)){m.moveToFirst();e.put("owner",m.getString(0));}
            }
        }
        e.put("note",e.optString("note")).put("version",1).put("actor",USER_ONE).put("deleted",false);
        ContentValues v=entryValues(e);db.beginTransaction();
        try{stamp(db,v);db.insertWithOnConflict("entries",null,v,SQLiteDatabase.CONFLICT_REPLACE);db.setTransactionSuccessful();}finally{db.endTransaction();}
    }
    public synchronized void delete(String id) {
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try(Cursor c=db.rawQuery("SELECT id FROM entries WHERE id=? AND deleted=0",new String[]{id})){
            if(c.moveToFirst()){ContentValues v=new ContentValues();v.put("deleted",1);stamp(db,v);db.update("entries",v,"id=?",new String[]{id});}
            db.setTransactionSuccessful();
        }finally{db.endTransaction();}
    }
    public synchronized void selectUser(String id){validUser(id);getWritableDatabase().execSQL("UPDATE meta SET currentUser=?",new Object[]{id});}
    public synchronized void addUser(String name){
        name=name.trim();if(name.isEmpty()||name.length()>24)throw new IllegalArgumentException("名字需为 1–24 个字");
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try{
            try(Cursor c=db.rawQuery("SELECT COUNT(*) FROM users",null)){c.moveToFirst();if(c.getInt(0)>=1000)throw new IllegalArgumentException("用户数量已达上限");}
            String id=UUID.randomUUID().toString();ContentValues v=new ContentValues();v.put("id",id);v.put("name",name);v.put("nameAt",System.currentTimeMillis());db.execSQL("UPDATE meta SET revision=revision+1");
            db.insertOrThrow("users",null,v);db.execSQL("UPDATE meta SET currentUser=?",new Object[]{id});db.setTransactionSuccessful();
        }finally{db.endTransaction();}
    }
    public synchronized void joinUser(String raw){
        String id=UUID.fromString(raw.trim()).toString();if(!id.equalsIgnoreCase(raw.trim()))throw new IllegalArgumentException("请输入完整用户 ID");
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try{
            try(Cursor c=db.rawQuery("SELECT COUNT(*) FROM users",null)){c.moveToFirst();if(c.getInt(0)>=1000)throw new IllegalArgumentException("用户数量已达上限");}
            if(!subscribed(id)){
                db.execSQL("INSERT INTO users(id,name,nameAt,pending) VALUES(?,?,0,1)",new Object[]{id,"等待获取用户"});
                db.execSQL("UPDATE meta SET revision=revision+1");
            }
            db.setTransactionSuccessful();
        }finally{db.endTransaction();}
    }
    public synchronized void leaveUser(String id,long syncedRevision){
        if(!subscribed(id))return;
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try{
            try(Cursor c=db.rawQuery("SELECT COUNT(*) FROM users",null)){c.moveToFirst();if(c.getInt(0)<=1)throw new IllegalArgumentException("请先添加其他用户，再移除这个用户");}
            try(Cursor c=db.rawQuery("SELECT revision FROM meta",null)){c.moveToFirst();if(c.getLong(0)>syncedRevision)throw new IllegalArgumentException("请先同步本地更改，再移除用户");}
            db.delete("entries","owner=?",new String[]{id});db.delete("users","id=?",new String[]{id});
            db.execSQL("UPDATE meta SET revision=revision+1,currentUser=CASE WHEN currentUser=? THEN (SELECT id FROM users ORDER BY pending,id LIMIT 1) ELSE currentUser END",new Object[]{id});
            db.setTransactionSuccessful();
        }finally{db.endTransaction();}
    }
    public synchronized void renameUser(String id,String name){
        validUser(id);name=name.trim();if(name.isEmpty()||name.length()>24)throw new IllegalArgumentException("名字需为 1–24 个字");
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try{
            long previous;try(Cursor c=db.rawQuery("SELECT nameAt FROM users WHERE id=?",new String[]{id})){c.moveToFirst();previous=c.getLong(0);}
            ContentValues v=new ContentValues();v.put("name",name);v.put("nameAt",Math.max(System.currentTimeMillis(),previous+1));db.update("users",v,"id=?",new String[]{id});db.execSQL("UPDATE meta SET revision=revision+1");db.setTransactionSuccessful();}finally{db.endTransaction();}
    }
    public synchronized void setAvatar(String id,String avatar){
        validUser(id);if(avatar.length()>90000)throw new IllegalArgumentException("头像太大");
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try{
            long previous;try(Cursor c=db.rawQuery("SELECT avatarAt FROM users WHERE id=?",new String[]{id})){c.moveToFirst();previous=c.getLong(0);}
            ContentValues v=new ContentValues();v.put("avatar",avatar);v.put("avatarAt",Math.max(System.currentTimeMillis(),previous+1));
            db.update("users",v,"id=?",new String[]{id});db.execSQL("UPDATE meta SET revision=revision+1");db.setTransactionSuccessful();
        }finally{db.endTransaction();}
    }
    private void mergeAvatar(SQLiteDatabase db,JSONObject u)throws Exception{
        String image=u.optString("avatar","");long at=u.optLong("avatarAt",0);
        if(image.length()>90000||at<0||at>=9007199254740991L)throw new IllegalArgumentException("无效头像");
        if(!image.isEmpty()){
            byte[] raw=android.util.Base64.decode(image,android.util.Base64.DEFAULT);
            if(raw.length>65536||raw.length<4||raw[0]!=(byte)255||raw[1]!=(byte)216||raw[raw.length-2]!=(byte)255||raw[raw.length-1]!=(byte)217||at==0)throw new IllegalArgumentException("无效头像");
        }
        try(Cursor c=db.rawQuery("SELECT avatarAt,avatar FROM users WHERE id=?",new String[]{u.getString("id")})){
            c.moveToFirst();if(at>c.getLong(0)||(at==c.getLong(0)&&image.compareTo(c.getString(1))>0)){
                ContentValues v=new ContentValues();v.put("avatar",image);v.put("avatarAt",at);db.update("users",v,"id=?",new String[]{u.getString("id")});
            }
        }
    }
    private boolean newer(SQLiteDatabase db,String table,JSONObject row) throws Exception {
        long version=row.getLong("version");String actor=row.getString("actor");UUID.fromString(actor);
        if(version<1||version>=9007199254740991L)throw new IllegalArgumentException("无效同步版本");
        db.execSQL("UPDATE meta SET clock=MAX(clock,?)",new Object[]{version});
        try(Cursor c=db.rawQuery("SELECT version,actor FROM "+table+" WHERE id=?",new String[]{row.getString("id")})){
            return !c.moveToFirst()||version>c.getLong(0)||(version==c.getLong(0)&&actor.compareTo(c.getString(1))>0);
        }
    }
    public synchronized void merge(JSONObject reply) throws Exception {
        if(reply.getInt("protocol")!=4)throw new IllegalArgumentException("请升级电脑同步服务");
        JSONArray users=reply.getJSONArray("users"),records=reply.getJSONArray("records");
        if(users.length()>1000)throw new IllegalArgumentException("无效用户数据");
        java.util.HashSet<String> seen=new java.util.HashSet<>();SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try{
            for(int i=0;i<users.length();i++){
                JSONObject u=users.getJSONObject(i);String id=u.getString("id"),name=u.getString("name");UUID.fromString(id);
                if(!seen.add(id)||name.trim().isEmpty()||name.length()>24)throw new IllegalArgumentException("无效用户数据");
                if(subscribed(id)){
                    long at=u.getLong("nameAt");if(at<0||at>=9007199254740991L)throw new IllegalArgumentException("无效名字时间");
                    try(Cursor c=db.rawQuery("SELECT nameAt,name,pending FROM users WHERE id=?",new String[]{id})){
                        c.moveToFirst();if(c.getInt(2)!=0||at>c.getLong(0)||(at==c.getLong(0)&&name.compareTo(c.getString(1))>0)){
                            ContentValues v=new ContentValues();v.put("name",name);v.put("nameAt",at);v.put("pending",0);db.update("users",v,"id=?",new String[]{id});
                        }
                    }
                    mergeAvatar(db,u);
                }
            }
            seen.clear();
            for(int i=0;i<records.length();i++){
                JSONObject e=records.getJSONObject(i);if(!subscribed(e.getString("owner")))continue;ContentValues v=entryValues(e);
                if(!seen.add(e.getString("id")))throw new IllegalArgumentException("重复账单");
                if(newer(db,"entries",e))db.insertWithOnConflict("entries",null,v,SQLiteDatabase.CONFLICT_REPLACE);
            }
            JSONArray excluded=reply.optJSONArray("outOfScope");
            if(excluded!=null)for(int i=0;i<excluded.length();i++){
                JSONObject e=excluded.getJSONObject(i);
                if(newer(db,"entries",e))db.delete("entries","id=?",new String[]{e.getString("id")});
            }
            db.setTransactionSuccessful();
        }finally{db.endTransaction();}
    }
}
