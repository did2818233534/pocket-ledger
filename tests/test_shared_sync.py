"""Two offline replicas, migration and durable deletion regression tests."""
import copy
import json
import tempfile
import unittest
import uuid
from test_server import s

TEST_USERS = (s.USER_IDS[0], "00000000-0000-4000-8000-000000000002")

class SharedSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=s.Store(self.tmp.name)
        self.a,self.b=str(uuid.uuid4()),str(uuid.uuid4())
        self.users=[dict(id=uid,name=name,nameAt=1,avatar='',avatarAt=0) for uid,name in zip(TEST_USERS,('用户一','用户二'))]
    def tearDown(self):self.tmp.cleanup()
    def packet(self,device,records,revision=1,users=None):
        profiles=users or copy.deepcopy(self.users)
        return dict(protocol=4,device=device,revision=revision,subscriptions=[u["id"] for u in profiles],records=records,users=profiles)
    def row(self,actor,owner=None,version=3,**kw):
        return dict(id=str(uuid.uuid4()),amount=123,at='2026-10-20T12:00',category='daily',note='测试',owner=owner or TEST_USERS[0],version=version,actor=actor,deleted=False,**kw)
    def test_primary_note_round_trip_and_legacy_edit(self):
        row=self.row(self.a,primaryNote='吃饭')
        self.store.accept(self.packet(self.a,[row]))
        other=s.Store(self.tmp.name)
        reply=other.accept(self.packet(self.b,[]))
        self.assertEqual(reply['records'][0]['primaryNote'],'吃饭')
        self.assertEqual(reply['records'][0]['note'],'测试')
        old_edit={**row,'actor':self.b,'version':4,'note':'牛肉面'}
        del old_edit['primaryNote']
        self.assertEqual(other.accept(self.packet(self.b,[old_edit],2))['records'][0]['primaryNote'],'吃饭')
        cleared={**old_edit,'primaryNote':'','version':5}
        self.assertEqual(other.accept(self.packet(self.b,[cleared],3))['records'][0]['primaryNote'],'')
        with self.assertRaises(ValueError):other.accept(self.packet(self.b,[{**cleared,'primaryNote':'x'*61,'version':6}],4))

    def test_two_devices_both_users_cross_edit_delete_and_stale_replay(self):
        a,b=self.row(self.a),self.row(self.b,TEST_USERS[1])
        self.store.accept(self.packet(self.a,[a]));reply=self.store.accept(self.packet(self.b,[b]))
        self.assertEqual({e['id'] for e in reply['records']},{a['id'],b['id']})
        # Second phone edits the first user's entry and moves it to another month.
        edited={**a,'amount':999,'at':'2026-11-01T08:00','actor':self.b,'version':4}
        reply=self.store.accept(self.packet(self.b,[edited,b],2))
        self.assertEqual(next(e for e in reply['records'] if e['id']==a['id'])['amount'],999)
        deleted={**edited,'deleted':True,'actor':self.a,'version':5}
        self.store.accept(self.packet(self.a,[deleted,b],2))
        reply=self.store.accept(self.packet(self.b,[edited,b],2))
        self.assertTrue(next(e for e in reply['records'] if e['id']==a['id'])['deleted'])
        restarted=s.Store(self.tmp.name)
        self.assertEqual(restarted.export(),self.store.export())
        self.assertTrue((restarted.directory/'2026-11.json').exists())
    def test_concurrent_edits_converge_independent_of_delivery_order(self):
        base=self.row(self.a);x={**base,'version':4,'actor':self.a,'amount':100};y={**base,'version':4,'actor':self.b,'amount':200}
        expected=max((x,y),key=s.Store.stamp)
        for rows in ([x,y],[y,x]):
            with tempfile.TemporaryDirectory() as tmp:
                store=s.Store(tmp)
                for e in rows:store.accept(self.packet(e['actor'],[e]))
                self.assertEqual(store.export()['entries'],[{**expected,'primaryNote':''}])
    def test_rename_users_syncs_independently_of_entries(self):
        users=copy.deepcopy(self.users);users[1].update(name='小明',nameAt=2)
        self.store.accept(self.packet(self.b,[],users=users))
        reply=self.store.accept(self.packet(self.a,[]))
        self.assertEqual(reply['users'][1]['name'],'小明')
    def test_legacy_upgrade_keeps_unsynced_edits_and_deletions(self):
        a,b=self.row(self.a),self.row(self.a)
        fields=('id','amount','at','category','note')
        self.store.accept(dict(device=self.a,revision=7,entries=[{k:r[k] for k in fields} for r in (a,b)]))
        a.update(version=9,amount=999)
        reply=self.store.accept(self.packet(self.a,[a],8))
        self.assertEqual(next(e for e in reply['records'] if e['id']==a['id'])['amount'],999)
        self.assertTrue(next(e for e in reply['records'] if e['id']==b['id'])['deleted'])
        with self.assertRaises(ValueError):self.store.accept(dict(device=self.a,revision=9,entries=[]))
        self.assertEqual(len(self.store.export()['entries']),2)
    def test_add_more_users_and_sync_arbitrary_owner(self):
        uid=str(uuid.uuid4());third=dict(id=uid,name='第三位用户',nameAt=4,avatar='',avatarAt=0)
        profiles=self.users+[third];row=self.row(self.a,uid)
        self.store.accept(self.packet(self.a,[row],users=profiles))
        reply=self.store.accept(self.selective(self.b,list(TEST_USERS)+[uid]))
        self.assertEqual(len(reply['users']),3)
        self.assertEqual(reply['records'][0]['owner'],uid)
        uid4=str(uuid.uuid4());fourth=dict(id=uid4,name='第四位用户',nameAt=5,avatar='',avatarAt=0)
        # Two phones add people offline; neither may drop the other's profile.
        reply=self.store.accept(self.packet(self.b,[],users=self.users+[fourth]))
        self.assertEqual({u['id'] for u in self.store.export()['users']},set(TEST_USERS)|{uid,uid4})
        with self.assertRaises(ValueError):self.store.accept(self.packet(self.a,[],users=profiles+[third]))

    def selective(self, device, subscriptions, records=None, profiles=None):
        return dict(protocol=4,device=device,revision=1,subscriptions=subscriptions,users=profiles or [],records=records or [])
    def test_scoped_join_rename_missing_id_and_same_name_different_identity(self):
        x,y=self.row(self.a),self.row(self.b,TEST_USERS[1])
        self.store.accept(self.packet(self.a,[x,y]))
        before=self.store.export()
        only=self.store.accept(self.selective(self.b,[TEST_USERS[0]]))
        self.assertEqual([u['id'] for u in only['users']],[TEST_USERS[0]])
        self.assertEqual([e['id'] for e in only['records']],[x['id']])
        renamed=copy.deepcopy(self.users);renamed[0].update(name='改名后',nameAt=5)
        self.store.accept(self.selective(self.a,[TEST_USERS[0]],[x],[renamed[0]]))
        again=self.store.accept(self.selective(self.b,[TEST_USERS[0]]))
        self.assertEqual(again['users'][0]['name'],'改名后')
        self.assertEqual(again['users'][0]['id'],TEST_USERS[0])
        unknown=str(uuid.uuid4());missing=self.store.accept(self.selective(self.b,[unknown]))
        self.assertEqual(missing['missingUsers'],[unknown]);self.assertEqual(missing['users'],[]);self.assertEqual(missing['records'],[])
        self.assertNotIn(unknown,[u['id'] for u in self.store.export()['users']])
        all_users=self.store.accept(self.selective(self.b,list(TEST_USERS)))
        self.assertEqual(len(all_users['records']),2)
        self.assertEqual(len(before['entries']),len(self.store.export()['entries']))
    def test_scoped_owner_change_does_not_leak_other_users_data(self):
        row=self.row(self.a);self.store.accept(self.packet(self.a,[row]))
        moved={**row,'owner':TEST_USERS[1],'version':4,'actor':self.b}
        self.store.accept(self.packet(self.b,[moved]))
        reply=self.store.accept(self.selective(self.a,[TEST_USERS[0]],[row],[self.users[0]]))
        self.assertEqual(reply['records'],[])
        self.assertEqual(reply['outOfScope'],[{k:moved[k] for k in ('id','version','actor')}])
        with self.assertRaises(ValueError):self.store.accept(self.selective(self.a,[TEST_USERS[0]],[moved],self.users))
        self.assertEqual(self.store.export()['entries'][0]['owner'],TEST_USERS[1])

    def test_avatar_latest_only_independent_of_name_and_scoped_download(self):
        import base64
        old_image=base64.b64encode(b'\xff\xd8old\xff\xd9').decode()
        new_image=base64.b64encode(b'\xff\xd8new\xff\xd9').decode()
        profile={**self.users[0],'avatar':old_image,'avatarAt':100}
        self.store.accept(self.selective(self.a,[profile['id']],profiles=[profile]))
        newer={**profile,'avatar':new_image,'avatarAt':200}
        self.store.accept(self.selective(self.b,[profile['id']],profiles=[newer]))
        # A concurrent rename carries an older avatar: merge each independently.
        renamed={**profile,'name':'新名字','nameAt':4}
        reply=self.store.accept(self.selective(self.a,[profile['id']],profiles=[renamed]))
        self.assertEqual(reply['users'][0]['avatar'],new_image);self.assertEqual(reply['users'][0]['name'],'新名字')
        self.assertNotIn(old_image,self.store.path.read_text())
        self.assertEqual(self.store.accept(self.selective(self.b,[TEST_USERS[1]]))['users'],[])
        cleared={**renamed,'avatar':'','avatarAt':300}
        self.store.accept(self.selective(self.a,[profile['id']],profiles=[cleared]))
        reply=self.store.accept(self.selective(self.b,[profile['id']],profiles=[newer]))
        self.assertEqual(reply['users'][0]['avatar'],'');self.assertEqual(reply['users'][0]['avatarAt'],300)
        self.assertNotIn(new_image,self.store.path.read_text())
        with self.assertRaises(ValueError):self.store.accept(self.selective(self.a,[profile['id']],profiles=[{**cleared,'avatar':'not-jpeg'}]))

    def test_identity_uses_current_value_and_timestamp_only(self):
        newer={**self.users[0],'name':'最新名字','nameAt':500}
        older={**self.users[0],'name':'旧名字','nameAt':100}
        self.store.accept(self.selective(self.a,[newer['id']],profiles=[newer]))
        reply=self.store.accept(self.selective(self.b,[older['id']],profiles=[older]))
        self.assertEqual(reply['users'][0]['name'],'最新名字')
        self.assertEqual(set(reply['users'][0]),{'id','name','nameAt','avatar','avatarAt'})
        self.assertNotIn('旧名字',self.store.path.read_text())
        self.assertFalse(self.store.pending.exists())

    def test_equal_name_timestamp_uses_android_utf16_order(self):
        first={**self.users[0],'name':'😀','nameAt':500}
        second={**self.users[0],'name':'\ue000','nameAt':500}
        for profile in (first,second,first):
            self.store.accept(self.selective(self.a,[profile['id']],profiles=[profile]))
        self.assertEqual(self.store.export()['users'][0]['name'],'\ue000')

    def test_bad_user_or_mutation_is_atomic(self):
        row=self.row(self.a);self.store.accept(self.packet(self.a,[row]));before=self.store.export()
        for bad in ({**row,'owner':self.b},{**row,'deleted':'false'},{**row,'version':0},{**row,'amount':999}):
            with self.assertRaises(ValueError):self.store.accept(self.packet(self.a,[bad]))
            self.assertEqual(self.store.export(),before)
    def test_shared_transaction_recovery_preserves_profiles_and_tombstones(self):
        from unittest.mock import patch
        row=self.row(self.a);self.store.accept(self.packet(self.a,[row]))
        row.update(version=5,deleted=True,at='2026-11-01T10:00')
        write=self.store._atomic_write
        def fail(path,value):
            if path==self.store.path:raise OSError('interrupted')
            write(path,value)
        with patch.object(self.store,'_atomic_write',side_effect=fail):
            with self.assertRaises(OSError):self.store.accept(self.packet(self.a,[row],2))
        restored=s.Store(self.tmp.name)
        self.assertTrue(restored.export()['entries'][0]['deleted'])
        self.assertEqual(restored.export()['users'],self.users)

if __name__=='__main__':unittest.main()
