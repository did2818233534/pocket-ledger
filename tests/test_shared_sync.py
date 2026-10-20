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
        self.users=[dict(id=uid,name=name,version=1,actor=TEST_USERS[0]) for uid,name in zip(TEST_USERS,('用户一','用户二'))]
    def tearDown(self):self.tmp.cleanup()
    def packet(self,device,records,revision=1,users=None):
        return dict(protocol=2,device=device,revision=revision,records=records,users=users or copy.deepcopy(self.users))
    def row(self,actor,owner=None,version=3,**kw):
        return dict(id=str(uuid.uuid4()),amount=123,at='2026-10-20T12:00',category='daily',note='测试',owner=owner or TEST_USERS[0],version=version,actor=actor,deleted=False,**kw)
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
                self.assertEqual(store.export()['entries'],[expected])
    def test_rename_users_syncs_independently_of_entries(self):
        users=copy.deepcopy(self.users);users[1].update(name='小明',version=2,actor=self.b)
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
        uid=str(uuid.uuid4());third=dict(id=uid,name='第三位用户',version=4,actor=self.a)
        profiles=self.users+[third];row=self.row(self.a,uid)
        self.store.accept(self.packet(self.a,[row],users=profiles))
        reply=self.store.accept(self.packet(self.b,[]))
        self.assertEqual(len(reply['users']),3)
        self.assertEqual(reply['records'][0]['owner'],uid)
        uid4=str(uuid.uuid4());fourth=dict(id=uid4,name='第四位用户',version=5,actor=self.b)
        # Two phones add people offline; neither may drop the other's profile.
        reply=self.store.accept(self.packet(self.b,[],users=self.users+[fourth]))
        self.assertEqual({u['id'] for u in reply['users']},set(TEST_USERS)|{uid,uid4})
        with self.assertRaises(ValueError):self.store.accept(self.packet(self.a,[],users=profiles+[third]))

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
