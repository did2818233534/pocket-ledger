#!/usr/bin/env python3
"""Generate the manifest beside the signed APK; publish both to the matching release."""
import hashlib,json,sys
from pathlib import Path
apk=Path(sys.argv[1] if len(sys.argv)>1 else 'dist/小账-1.4.3.apk')
content=apk.read_bytes()
from urllib.parse import quote
manifest={'schema':1,'versionCode':8,'versionName':'1.4.3','prerelease':False,'assets':{'arm64-v8a':{'url':'https://github.com/did2818233534/pocket-ledger/releases/download/v1.4.3/'+quote(apk.name),'sha256':hashlib.sha256(content).hexdigest(),'size':len(content)}}}
path=apk.parent/'latest.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(path)
