package cn.guga.ledger;
import android.content.Context;
import android.os.Build;

/** Produces a single 192px JPEG in memory; never caches the original photo. */
final class AvatarCodec {
    static String read(Context context,android.net.Uri uri)throws Exception {
        android.graphics.Bitmap source;
        if(Build.VERSION.SDK_INT>=28){
            source=android.graphics.ImageDecoder.decodeBitmap(android.graphics.ImageDecoder.createSource(context.getContentResolver(),uri),(decoder,info,src)->{
                int width=info.getSize().getWidth(),height=info.getSize().getHeight();float scale=Math.min(1f,384f/Math.max(width,height));
                decoder.setTargetSize(Math.max(1,Math.round(width*scale)),Math.max(1,Math.round(height*scale)));decoder.setAllocator(android.graphics.ImageDecoder.ALLOCATOR_SOFTWARE);
            });
        }else{
            android.graphics.BitmapFactory.Options options=new android.graphics.BitmapFactory.Options();options.inJustDecodeBounds=true;
            try(java.io.InputStream in=context.getContentResolver().openInputStream(uri)){android.graphics.BitmapFactory.decodeStream(in,null,options);}
            options.inSampleSize=1;while(Math.max(options.outWidth,options.outHeight)/options.inSampleSize>384)options.inSampleSize*=2;
            options.inJustDecodeBounds=false;try(java.io.InputStream in=context.getContentResolver().openInputStream(uri)){source=android.graphics.BitmapFactory.decodeStream(in,null,options);}
            if(source!=null)try(java.io.InputStream in=context.getContentResolver().openInputStream(uri)){
                int orientation=new android.media.ExifInterface(in).getAttributeInt(android.media.ExifInterface.TAG_ORIENTATION,1);
                android.graphics.Matrix transform=new android.graphics.Matrix();
                if(orientation==3||orientation==4)transform.postRotate(180);else if(orientation==5||orientation==6)transform.postRotate(90);else if(orientation==7||orientation==8)transform.postRotate(270);
                if(orientation==2||orientation==4||orientation==5||orientation==7)transform.postScale(-1,1);
                android.graphics.Bitmap rotated=android.graphics.Bitmap.createBitmap(source,0,0,source.getWidth(),source.getHeight(),transform,true);if(rotated!=source){source.recycle();source=rotated;}
            }catch(java.io.IOException ignored){}
        }
        return encode(source);
    }
    static String encode(android.graphics.Bitmap source)throws Exception {
        if(source==null)throw new java.io.IOException("not an image");
        android.graphics.Bitmap square=android.graphics.Bitmap.createBitmap(192,192,android.graphics.Bitmap.Config.ARGB_8888);
        try{
            android.graphics.Canvas canvas=new android.graphics.Canvas(square);canvas.drawColor(android.graphics.Color.WHITE);
            int side=Math.min(source.getWidth(),source.getHeight()),left=(source.getWidth()-side)/2,top=(source.getHeight()-side)/2;
            canvas.drawBitmap(source,new android.graphics.Rect(left,top,left+side,top+side),new android.graphics.Rect(0,0,192,192),new android.graphics.Paint(android.graphics.Paint.FILTER_BITMAP_FLAG));
            java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();square.compress(android.graphics.Bitmap.CompressFormat.JPEG,82,out);
            if(out.size()>65536)throw new java.io.IOException("image too large");
            return android.util.Base64.encodeToString(out.toByteArray(),android.util.Base64.NO_WRAP);
        }finally{source.recycle();square.recycle();}
    }
}
