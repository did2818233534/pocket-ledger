package cn.guga.ledger;

import android.content.*;
import android.database.Cursor;
import android.database.sqlite.*;
import org.json.*;
import java.util.UUID;
import java.time.LocalDateTime;

public final class LedgerDb extends SQLiteOpenHelper {
    private static LedgerDb instance;
    public static synchronized LedgerDb get(Context c) {
        if (instance == null) instance = new LedgerDb(c.getApplicationContext());
        return instance;
    }
    private LedgerDb(Context c) { super(c, "ledger.db", null, 1); }
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE entries(id TEXT PRIMARY KEY, amount INTEGER NOT NULL, at TEXT NOT NULL, category TEXT NOT NULL, note TEXT NOT NULL)");
        db.execSQL("CREATE TABLE meta(device TEXT NOT NULL, revision INTEGER NOT NULL)");
        db.execSQL("INSERT INTO meta VALUES(?,0)", new Object[]{UUID.randomUUID().toString()});
    }
    public void onUpgrade(SQLiteDatabase db, int a, int b) {}
    public synchronized JSONObject snapshot() throws JSONException {
        JSONObject result = new JSONObject();
        SQLiteDatabase db = getReadableDatabase();
        try (Cursor c = db.rawQuery("SELECT device,revision FROM meta", null)) {
            c.moveToFirst(); result.put("device", c.getString(0)); result.put("revision", c.getLong(1));
        }
        JSONArray entries = new JSONArray();
        try (Cursor c = db.rawQuery("SELECT id,amount,at,category,note FROM entries ORDER BY at DESC,id", null)) {
            while (c.moveToNext()) entries.put(new JSONObject().put("id",c.getString(0)).put("amount",c.getLong(1))
                .put("at",c.getString(2)).put("category",c.getString(3)).put("note",c.getString(4)));
        }
        return result.put("entries", entries);
    }
    public synchronized void save(String raw) throws Exception {
        JSONObject e = new JSONObject(raw);
        long amount = e.getLong("amount");
        String category = e.getString("category"), at = e.getString("at"), note = e.optString("note");
        LocalDateTime.parse(at);
        if (amount < 1 || amount > 99999999999L || !category.matches("daily|extra|claim") || note.length() > 200)
            throw new IllegalArgumentException("请检查金额、分类和备注");
        String id = e.optString("id");
        if (id.isEmpty()) id = UUID.randomUUID().toString();
        UUID.fromString(id);
        ContentValues v = new ContentValues();
        v.put("id",id); v.put("amount",amount); v.put("at",at); v.put("category",category); v.put("note",note);
        SQLiteDatabase db = getWritableDatabase(); db.beginTransaction();
        try {
            db.insertWithOnConflict("entries",null,v,SQLiteDatabase.CONFLICT_REPLACE);
            db.execSQL("UPDATE meta SET revision=revision+1");
            db.setTransactionSuccessful();
        } finally { db.endTransaction(); }
    }
    public synchronized void delete(String id) {
        SQLiteDatabase db = getWritableDatabase(); db.beginTransaction();
        try {
            if (db.delete("entries","id=?",new String[]{id}) > 0) db.execSQL("UPDATE meta SET revision=revision+1");
            db.setTransactionSuccessful();
        } finally { db.endTransaction(); }
    }
}
