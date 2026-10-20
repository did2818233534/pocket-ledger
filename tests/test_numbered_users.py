import copy
import unittest
import uuid
from test_shared_sync import SharedSyncTests
from test_server import s

class NumberedUserTests(SharedSyncTests):
    def numbered(self,device,users,records=(),subscriptions=None,revision=1):
        return dict(protocol=5,device=device,revision=revision,users=users,records=list(records),subscriptions=subscriptions if subscriptions is not None else [u['id'] for u in users])
    def test_existing_user_becomes_one_and_persists(self):
        user=self.users[0];row=self.row(self.a)
        self.store.accept(self.packet(self.a,[row],users=[user]))
        reply=self.store.accept(self.numbered(self.a,[user],[row]))
        self.assertEqual(reply['idMap'],{user['id']:'1'})
        self.assertEqual(reply['records'][0]['owner'],'1')
        self.assertEqual(reply['users'][0]['id'],'1')
        other=s.Store(self.tmp.name)
        joined=other.accept(self.numbered(self.b,[],subscriptions=['1']))
        self.assertEqual(joined['records'],reply['records'])
        renamed={**reply['users'][0],'name':'新名字','nameAt':100}
        self.assertEqual(other.accept(self.numbered(self.b,[renamed],subscriptions=['1']))['users'][0]['name'],'新名字')
        with self.assertRaises(ValueError):other.accept(self.packet(self.a,[row],users=[user]))
    def test_offline_users_receive_distinct_sequential_ids(self):
        a={**self.users[0],'id':str(uuid.uuid4())};b={**self.users[0],'id':str(uuid.uuid4())}
        first=self.store.accept(self.numbered(self.a,[a]));second=self.store.accept(self.numbered(self.b,[b]))
        self.assertEqual(first['users'][0]['id'],'1');self.assertEqual(second['users'][0]['id'],'2')
        self.assertEqual(self.store.accept(self.numbered(self.a,[a]))['idMap'][a['id']],'1')
        self.assertEqual(self.store.accept(self.numbered(self.b,[],subscriptions=['1']))['users'][0]['id'],'1')
        missing=self.store.accept(self.numbered(self.b,[],subscriptions=['3']))
        self.assertEqual(missing['missingUsers'],['3']);self.assertEqual(missing['users'],[])
    def test_invalid_request_does_not_migrate_or_allocate(self):
        before=copy.deepcopy(self.store.export());u=self.users[0]
        with self.assertRaises(ValueError):self.store.accept(self.numbered(self.a,[{**u,'name':''}]))
        self.assertEqual(self.store.export(),before)
