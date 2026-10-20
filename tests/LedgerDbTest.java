package cn.guga.ledger;
import android.content.*;
import android.database.*;
import android.database.sqlite.*;
import java.io.File;
import java.lang.reflect.*;
import java.util.UUID;
import org.json.*;

/** Standalone app_process test; never opens the installed application's ledger.db. */
public final class LedgerDbTest {
    static final String PATH="/data/local/tmp/pocket-ledger-isolated-test.db";
    static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    static LedgerDb open() throws Exception {
        Context context=new ContextWrapper(null){
            public String getPackageName(){return "cn.guga.ledger.dbtest";}
            public android.content.pm.ApplicationInfo getApplicationInfo(){android.content.pm.ApplicationInfo info=new android.content.pm.ApplicationInfo();info.targetSdkVersion=36;return info;}
            public File getDatabasePath(String name){return new File(PATH);}
            public SQLiteDatabase openOrCreateDatabase(String name,int mode,SQLiteDatabase.CursorFactory factory,DatabaseErrorHandler handler){return SQLiteDatabase.openDatabase(PATH,factory,SQLiteDatabase.CREATE_IF_NECESSARY,handler);}
            public SQLiteDatabase openOrCreateDatabase(String name,int mode,SQLiteDatabase.CursorFactory factory){return SQLiteDatabase.openOrCreateDatabase(PATH,factory);}
        };
        Constructor<LedgerDb> ctor=LedgerDb.class.getDeclaredConstructor(Context.class);ctor.setAccessible(true);return ctor.newInstance(context);
    }
    static void clean(){for(String suffix:new String[]{"","-wal","-shm","-journal"})new File(PATH+suffix).delete();}
    static JSONObject entry(String owner)throws Exception{return new JSONObject().put("id",UUID.randomUUID().toString()).put("owner",owner).put("amount",123).put("at","2026-10-20T12:00").put("category","daily").put("note","isolated test");}
    public static void main(String[] args)throws Exception {
        clean();LedgerDb db=null;
        try {
            db=open();check(db.snapshot().getJSONArray("users").length()==1,"new ledger starts with one user");db.addUser("第二位用户");db.addUser("第三位用户");JSONObject state=db.snapshot();String owner=state.getString("currentUser");
            check(state.getJSONArray("users").length()==3,"third user created");
            JSONObject row=entry(owner);db.save(row.toString());JSONObject packet=db.syncSnapshot();
            JSONObject remote=new JSONObject(packet.toString());JSONObject r=remote.getJSONArray("records").getJSONObject(0);
            long remoteVersion=r.getLong("version")+10;r.put("amount",456).put("version",remoteVersion).put("actor",UUID.randomUUID().toString());
            String fourth=UUID.randomUUID().toString();remote.getJSONArray("users").put(new JSONObject().put("id",fourth).put("name","第四位用户").put("version",remoteVersion).put("actor",fourth));
            r.put("owner",fourth);db.merge(remote);
            check(db.snapshot().getJSONArray("users").length()==4,"fourth user downloaded");
            check(db.snapshot().getJSONArray("entries").getJSONObject(0).getLong("amount")==456,"remote edit downloaded");
            row.put("amount",789);db.save(row.toString());db.merge(remote);
            check(db.snapshot().getJSONArray("entries").getJSONObject(0).getLong("amount")==789,"in-flight old response must not overwrite newer local edit");
            check(db.syncSnapshot().getJSONArray("records").getJSONObject(0).getLong("version")>remoteVersion,"logical clock advances after download");
            db.delete(row.getString("id"));db.merge(remote);
            check(db.snapshot().getJSONArray("entries").length()==0,"stale remote edit must not resurrect deletion");
            check(db.syncSnapshot().getJSONArray("records").getJSONObject(0).getBoolean("deleted"),"durable tombstone included in exchange");
            db.renameUser(owner,"改名成功");db.merge(remote);
            boolean renamed=false;JSONArray profiles=db.snapshot().getJSONArray("users");for(int i=0;i<profiles.length();i++)if(profiles.getJSONObject(i).getString("id").equals(owner))renamed=profiles.getJSONObject(i).getString("name").equals("改名成功");
            check(renamed,"stale profile cannot undo rename");
            String before=db.syncSnapshot().toString();JSONObject invalid=new JSONObject(remote.toString());invalid.getJSONArray("records").getJSONObject(0).put("owner",UUID.randomUUID().toString());
            boolean rejected=false;try{db.merge(invalid);}catch(Exception expected){rejected=true;}
            check(rejected&&before.equals(db.syncSnapshot().toString()),"invalid owner must roll back exchange");
            db.close();db=null;clean();
            SQLiteDatabase legacy=SQLiteDatabase.openOrCreateDatabase(PATH,null);
            legacy.execSQL("CREATE TABLE entries(id TEXT PRIMARY KEY,amount INTEGER NOT NULL,at TEXT NOT NULL,category TEXT NOT NULL,note TEXT NOT NULL)");
            legacy.execSQL("CREATE TABLE meta(device TEXT NOT NULL,revision INTEGER NOT NULL)");
            String device=UUID.randomUUID().toString(),id=UUID.randomUUID().toString();
            legacy.execSQL("INSERT INTO meta VALUES(?,7)",new Object[]{device});
            legacy.execSQL("INSERT INTO entries VALUES(?,123,'2026-10-20T12:00','daily','legacy')",new Object[]{id});legacy.setVersion(1);legacy.close();
            db=open();state=db.snapshot();JSONObject migrated=state.getJSONArray("entries").getJSONObject(0);
            check(migrated.getString("id").equals(id)&&migrated.getLong("amount")==123&&migrated.getString("owner").equals(LedgerDb.USER_ONE),"legacy entry preserved with initial owner");
            check(state.getLong("revision")==7&&state.getString("device").equals(device),"migration preserves revision and device");
            System.out.println("PASS: isolated Android database migration, 4 users, cross-user editing, stale replies, clock, deletion, rename and atomic rejection");
        }finally{if(db!=null)db.close();clean();}
        System.exit(0);
    }
}
