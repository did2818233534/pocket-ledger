package dev.guga.updates;
public final class ReleaseUpdaterTest {
 public static void main(String[] args)throws Exception{
  String repo="https://github.com/did2818233534/pocket-ledger";
  String manifest="{\"schema\":1,\"versionCode\":6,\"versionName\":\"next\",\"assets\":{\"arm64-v8a\":{\"url\":\""+repo+"/releases/download/vnext/app.apk\",\"sha256\":\""+"a".repeat(64)+"\",\"size\":123}}}";
  if(AppUpdates.parse(manifest,5,new String[]{"arm64-v8a"},repo).version!=6)throw new AssertionError();
  if(AppUpdates.parse(manifest,6,new String[]{"arm64-v8a"},repo)!=null)throw new AssertionError("downgrade");
  for(String invalid:new String[]{manifest.replace(repo,"https://example.com/wrong"),manifest.replace("123","209715201"),manifest.replace("a".repeat(64),"bad")}){
   try{AppUpdates.parse(invalid,5,new String[]{"arm64-v8a"},repo);throw new AssertionError("accepted invalid release");}catch(java.io.IOException expected){}
  }
  if(AppUpdates.due("today","today",false,true)||!AppUpdates.due("today","today",true,false))throw new AssertionError("daily gate");
  ReleaseUpdater.resume();
  java.io.File cache=java.io.File.createTempFile("ledger-update-", ".apk",new java.io.File("/data/local/tmp"));
  try{
   byte[] bytes={1,2,3};try(java.io.FileOutputStream out=new java.io.FileOutputStream(cache)){out.write(bytes);}
   String sha=AppUpdates.hex(java.security.MessageDigest.getInstance("SHA-256").digest(bytes));
   AppUpdates.Release release=new AppUpdates.Release(6,3,"",sha,"next");
   AppUpdates.cancelled=false;
   if(!AppUpdates.matchesRelease(cache,release))throw new AssertionError("valid cache rejected");
   try(java.io.FileOutputStream out=new java.io.FileOutputStream(cache)){out.write(new byte[]{3,2,1});}
   if(AppUpdates.matchesRelease(cache,release))throw new AssertionError("changed cache accepted");
  }finally{cache.delete();}
  ReleaseUpdater.resume();if(!AppUpdates.foreground)throw new AssertionError();ReleaseUpdater.suspend();if(AppUpdates.foreground||!AppUpdates.cancelled)throw new AssertionError("background");
  System.out.println("Release updater validation and lifecycle checks passed");
 }
}
