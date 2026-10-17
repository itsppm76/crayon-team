"""Disposable LOCAL Postgres acceptance. Refuses any non-loopback database host.
No Discord/model/OAuth/provider network calls. Does not take real credentials.
"""
import concurrent.futures
import os
import pathlib
import sys
from urllib.parse import urlsplit
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'integrated'/'private'))
if urlsplit(os.getenv('DATABASE_URL','')).hostname not in ('localhost','127.0.0.1'):
    raise SystemExit('Refusing non-local database; use a disposable local Postgres only')
from cryptography.fernet import Fernet
os.environ.update(CRAYON_DISCORD_ENABLED='on',DISCORD_BOT_TOKEN='synthetic-never-used',
    CRAYON_DISCORD_ALLOWED_USERS='123456789012345678,123456789012345679',
    CRAYON_WEB_ENCRYPTION_KEY=Fernet.generate_key().decode())
import cr_db as db,cr_discord as D,cr_web_app,cr_google,cr_connections,cr_memory,cr_work
checks=[]
def check(name,value):
    if not value:raise AssertionError(name)
    checks.append(name);print('PASS',name)
class Transport:
    def __init__(self):self.sent=[];self.n=0
    def message(self,channel,text='',components=None,item=None):
        self.n+=1;mid=str(323456789012345678+self.n)
        self.sent.append({'id':mid,'channel':channel,'text':text,'components':components,'item':item});return mid
    def request(self,*args,**kwargs):return {}

def main():
    db.init();cr_google.init();cr_connections.init();cr_web_app.init();cr_work.init();D.init()
    subject='123456789012345678';channel='223456789012345678'
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        ids=list(pool.map(lambda _:D.account(subject,channel,'Synthetic Discord test'),range(8)))
    uid=ids[0]
    check('concurrent identity allocation returns exactly one canonical account',len(set(ids))==1 and uid>=10**15 and uid!=int(subject))
    other=D.account('123456789012345679','223456789012345679','Other synthetic user')
    check('different Discord subjects have isolated canonical accounts',other!=uid)
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        claims=list(pool.map(lambda _:D.claim('423456789012345678',uid),range(8)))
    check('duplicate Gateway request claims exactly once',sum(claims)==1)
    transport=Transport();out=D.Out(uid,channel,transport)
    out.send(uid,'Exact synthetic review',{'inline_keyboard':[[{'text':'Keep','callback_data':'ux:keep'}]]})
    control=transport.sent[-1];custom=control['components'][0]['components'][0]['custom_id']
    check('raw action hashes are absent from Discord custom ID','ux:keep' not in custom)
    check('wrong owner cannot consume review',not D.callback(other,channel,control['id'],custom,out))
    check('wrong channel cannot consume review',not D.callback(uid,'223456789012345679',control['id'],custom,out))
    check('wrong message cannot consume review',not D.callback(uid,channel,'323456789012345670',custom,out))
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        accepted=list(pool.map(lambda _:D.callback(uid,channel,control['id'],custom,out),range(8)))
    check('concurrent double-click executes one reviewed control',sum(accepted)==1)
    check('kept-data result emitted once',sum(x['text']=='Kept your data unchanged.' for x in transport.sent)==1)
    check('consumed review payload is erased',db.q('SELECT encrypted FROM discord_controls WHERE id=%s',(custom[7:],),'one')['encrypted']=='')
    out.send(uid,'Expired review',{'inline_keyboard':[[{'text':'Keep','callback_data':'ux:keep'}]]})
    control=transport.sent[-1];custom=control['components'][0]['components'][0]['custom_id']
    db.q('UPDATE discord_controls SET expires_at=now() WHERE id=%s',(custom[7:],),'none')
    check('review is rejected at the database expiry boundary',not D.callback(uid,channel,control['id'],custom,out))
    D.dispatch_text(uid,'Synthetic Discord test','/proactive on','523456789012345678',out)
    settings=db.q('SELECT settings FROM users WHERE user_id=%s',(uid,),'one')['settings']
    check('opt-in delivery is Discord not Telegram',settings.get('delivery')=='discord' and settings.get('chat_id')==uid)
    db.q("INSERT INTO reminders(user_id,chat_id,text,due_at) VALUES(%s,%s,'Synthetic due reminder',now()-interval '1 second')",(uid,uid),'none')
    import cr_sched,cr_proactive
    from unittest.mock import Mock,patch
    non_discord=Mock();non_discord.channel_name='telegram'
    reminder_id=db.q("SELECT id FROM reminders WHERE user_id=%s AND status='pending'",(uid,),'one')['id']
    cr_sched.tick(non_discord)
    check('non-Discord reminder consumer does not claim Discord reminder',db.q('SELECT status FROM reminders WHERE id=%s',(reminder_id,),'one')['status']=='pending' and not non_discord.send.called)
    result=cr_sched.tick(out,only_user=uid)
    check('scheduled reminder goes through Discord output, not web notification',bool(result) and any(x['text']=='Reminder: Synthetic due reminder' for x in transport.sent))
    check('delivery destination resolves only this verified Discord subject',D.destination(uid)['subject']==subject)
    for module in (cr_sched,cr_proactive,cr_work):
        try:module.tick(out)
        except ValueError:guarded=True
        else:guarded=False
        check(module.__name__+' refuses unscoped Discord background invocation',guarded)
    job=cr_work.create(uid,uid,'Synthetic calculation | calculate 1 + 1')
    cr_work.tick(non_discord)
    check('non-Discord work consumer leaves Discord job queued',cr_work.get(uid,job['id'])['status']=='queued')
    with patch.object(cr_proactive.T,'now_local') as local:
        from datetime import datetime,timezone
        local.return_value=datetime(2026,10,17,12,tzinfo=timezone.utc)
        cr_work.tick(out,only_user=uid)
    check('Discord consumer completes and privately notifies queued calculation',cr_work.get(uid,job['id'])['status']=='done' and cr_work.get(uid,job['id'])['delivery_state']=='sent')
    db.q("UPDATE users SET settings=settings || '{\"proactive\":true,\"quiet_start\":0,\"quiet_end\":0}'::jsonb WHERE user_id=%s",(uid,),'none')
    db.q("INSERT INTO tasks(user_id,chat_id,title,updated_at) VALUES(%s,%s,'Synthetic stale task',now()-interval '25 hours')",(uid,uid),'none')
    cr_proactive.tick(non_discord)
    check('non-Discord proactive consumer does not emit or mark Discord check-in',not non_discord.send.called and not cr_proactive.settings(uid).get('proactive_date'))
    sent=cr_proactive.tick(out,only_user=uid)
    check('Discord proactive consumer delivers exact owner check-in',bool(sent) and any('Synthetic stale task' in x['text'] for x in transport.sent))
    D.maintenance()
    check('expired review payload removed by routine maintenance',db.q('SELECT count(*) AS n FROM discord_controls WHERE expires_at<=now()',fetch='one')['n']==0)

    D.claim('623456789012345678',uid)
    D.init()
    check('restart recovery marks work uncertain, never replayable',db.q('SELECT state FROM discord_inbox WHERE id=%s',('623456789012345678',),'one')['state']=='uncertain')
    D.cleanup(uid)
    check('Discord account erasure clears controls/inbox/routing',all(db.q('SELECT count(*) AS n FROM '+t+' WHERE user_id=%s',(uid,),'one')['n']==0 for t in ('discord_controls','discord_inbox','discord_accounts')))
    print(str(len(checks))+' local Postgres checks passed. No real Discord/provider call occurred.')
if __name__=='__main__':main()
