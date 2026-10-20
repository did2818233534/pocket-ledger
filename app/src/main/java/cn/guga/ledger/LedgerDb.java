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
    private LedgerDb(Context c) { super(c, "ledger.db", null, 2); }
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE entries(id TEXT PRIMARY KEY, amount INTEGER NOT NULL, at TEXT NOT NULL, category TEXT NOT NULL, note TEXT NOT NULL)");
        db.execSQL("CREATE TABLE meta(device TEXT NOT NULL, revision INTEGER NOT NULL)");
        db.execSQL("INSERT INTO meta VALUES(?,0)", new Object[]{UUID.randomUUID().toString()});
        onUpgrade(db,1,2);
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
    }
    public synchronized JSONObject snapshot() throws JSONException {
        JSONObject result=syncSnapshot(); JSONArray visible=new JSONArray(),rows=result.getJSONArray("records");
        for(int i=0;i<rows.length();i++)if(!rows.getJSONObject(i).getBoolean("deleted"))visible.put(rows.getJSONObject(i));
        result.remove("records");
        try(Cursor c=getReadableDatabase().rawQuery("SELECT currentUser FROM meta",null)){c.moveToFirst();result.put("currentUser",c.getString(0));}
        return result.put("entries",visible);
    }
    public synchronized JSONObject syncSnapshot() throws JSONException {
        JSONObject result = new JSONObject().put("protocol",2);
        SQLiteDatabase db = getReadableDatabase();
        try (Cursor c = db.rawQuery("SELECT device,revision FROM meta", null)) {
            c.moveToFirst(); result.put("device", c.getString(0)); result.put("revision", c.getLong(1));
        }
        JSONArray records = new JSONArray(),users=new JSONArray();
        try (Cursor c = db.rawQuery("SELECT id,amount,at,category,note,owner,version,actor,deleted FROM entries ORDER BY at DESC,id", null)) {
            while (c.moveToNext()) records.put(new JSONObject().put("id",c.getString(0)).put("amount",c.getLong(1))
                .put("at",c.getString(2)).put("category",c.getString(3)).put("note",c.getString(4))
                .put("owner",c.getString(5)).put("version",c.getLong(6)).put("actor",c.getString(7)).put("deleted",c.getInt(8)!=0));
        }
        try(Cursor c=db.rawQuery("SELECT id,name,version,actor FROM users ORDER BY id",null)){
            while(c.moveToNext())users.put(new JSONObject().put("id",c.getString(0)).put("name",c.getString(1)).put("version",c.getLong(2)).put("actor",c.getString(3)));
        }
        return result.put("records", records).put("users",users);
    }
    private void validUser(String id){
        UUID.fromString(id);
        try(Cursor c=getReadableDatabase().rawQuery("SELECT id FROM users WHERE id=?",new String[]{id})){
            if(!c.moveToFirst())throw new IllegalArgumentException("请选择记账用户");
        }
    }
    private void validEntry(JSONObject e) throws Exception {
        UUID.fromString(e.getString("id")); validUser(e.getString("owner"));
        LocalDateTime.parse(e.getString("at"));
        long amount=e.getLong("amount");
        if(amount<1||amount>99999999999L||!e.getString("category").matches("daily|extra|claim|giving")||e.getString("note").length()>200)throw new IllegalArgumentException("无效账单");
    }
    private ContentValues entryValues(JSONObject e) throws Exception {
        validEntry(e); ContentValues v=new ContentValues();
        for(String key:new String[]{"id","at","category","note","owner","actor"})v.put(key,e.getString(key));
        v.put("amount",e.getLong("amount"));v.put("version",e.getLong("version"));v.put("deleted",e.getBoolean("deleted")?1:0);return v;
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
            String id=UUID.randomUUID().toString();ContentValues v=new ContentValues();v.put("id",id);v.put("name",name);stamp(db,v);
            db.insertOrThrow("users",null,v);db.execSQL("UPDATE meta SET currentUser=?",new Object[]{id});db.setTransactionSuccessful();
        }finally{db.endTransaction();}
    }
    public synchronized void renameUser(String id,String name){
        validUser(id);name=name.trim();if(name.isEmpty()||name.length()>24)throw new IllegalArgumentException("名字需为 1–24 个字");
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try{ContentValues v=new ContentValues();v.put("name",name);stamp(db,v);db.update("users",v,"id=?",new String[]{id});db.setTransactionSuccessful();}finally{db.endTransaction();}
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
        if(reply.getInt("protocol")!=2)throw new IllegalArgumentException("请升级电脑同步服务");
        JSONArray users=reply.getJSONArray("users"),records=reply.getJSONArray("records");
        if(users.length()<1||users.length()>1000)throw new IllegalArgumentException("无效用户数据");
        java.util.HashSet<String> seen=new java.util.HashSet<>();SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try{
            for(int i=0;i<users.length();i++){
                JSONObject u=users.getJSONObject(i);String id=u.getString("id"),name=u.getString("name");UUID.fromString(id);
                if(!seen.add(id)||name.trim().isEmpty()||name.length()>24)throw new IllegalArgumentException("无效用户数据");
                if(newer(db,"users",u)){ContentValues v=new ContentValues();v.put("name",name);v.put("version",u.getLong("version"));v.put("actor",u.getString("actor"));v.put("id",id);db.insertWithOnConflict("users",null,v,SQLiteDatabase.CONFLICT_REPLACE);}
            }
            seen.clear();
            for(int i=0;i<records.length();i++){
                JSONObject e=records.getJSONObject(i);ContentValues v=entryValues(e);
                if(!seen.add(e.getString("id")))throw new IllegalArgumentException("重复账单");
                if(newer(db,"entries",e))db.insertWithOnConflict("entries",null,v,SQLiteDatabase.CONFLICT_REPLACE);
            }
            db.setTransactionSuccessful();
        }finally{db.endTransaction();}
    }
}
