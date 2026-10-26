import { test } from 'node:test'
import assert from 'node:assert/strict'
import { snapshotDraft, isDirty, createInitialState, hasUnsavedContent, saveSessionDraft, loadSessionDraft, clearSessionDraft, shouldWarnOnLeave } from '../src/lib/record-draft.js'

test('createInitialState: maps initial + preselect to draft state with separate date/time', ()=>{
  const s = createInitialState({ initial: { person_id: 5, type_key:'meeting', title:'hi', body:'b', tags:'a,b', location:'家', hours:2, overnight:true, person_ids:[5,9], event_date:'2026-10-12', event_time:'14:03:21' }, initialType:'text', preselect:[7] })
  assert.equal(s.personId, 5)
  assert.equal(s.type, 'meeting')
  assert.equal(s.title,'hi')
  assert.equal(s.location,'家')
  assert.equal(s.hours,'2')
  assert.equal(s.overnight,true)
  assert.deepEqual(s.extraIds,[9])
  assert.equal(s.eventDate,'2026-10-12')
  assert.equal(s.eventTime,'14:03:21')
  assert.ok(s.picked.some(p=>p.item_id===7))
})

test('createInitialState: handles outfit_items alias and sensitivity', ()=>{
  const s = createInitialState({ initial:{ person_id:2, type_key:'outfit', outfit_items:[{ item_id:3, name:'裤子' }], sensitivity:'sensitive', note:'n', manual_text:true, title:'t', event_date:'2026-10-10' } })
  assert.equal(s.picked[0].item_id,3)
  assert.equal(s.sensitivity,'sensitive')
  assert.equal(s.note,'n')
  assert.equal(s.manualText,true)
  assert.equal(s.title,'t')
})

test('createInitialState: event_time 00:00:00 treated as empty (only date)', ()=>{
  const s = createInitialState({ initial:{ event_date:'2026-10-12', event_time:'00:00:00' } })
  assert.equal(s.eventDate,'2026-10-12')
  assert.equal(s.eventTime,'')
})

test('createInitialState: meeting span comes from meeting.ended_on (or legacy top-level)', ()=>{
  const fromMeeting = createInitialState({ initial:{ type_key:'meeting', event_date:'2026-08-20', meeting:{ ended_on:'2026-08-22', location:'家', hours:null, overnight:true } } })
  assert.equal(fromMeeting.endedOn,'2026-08-22')
  assert.equal(fromMeeting.location,'家')
  const legacy = createInitialState({ initial:{ type_key:'meeting', event_date:'2026-08-20', ended_on:'2026-08-21' } })
  assert.equal(legacy.endedOn,'2026-08-21')
  const single = createInitialState({ initial:{ type_key:'meeting', event_date:'2026-08-20', meeting:{ ended_on:null } } })
  assert.equal(single.endedOn,'')
})

test('snapshotDraft: ending date change marks the draft dirty', ()=>{
  const base = createInitialState({ initial:{ type_key:'meeting', event_date:'2026-08-20', meeting:{ ended_on:null } } })
  const snap = snapshotDraft(base)
  assert.equal(isDirty(base, snap), false)
  assert.equal(isDirty({ ...base, endedOn: '2026-08-21' }, snap), true)
})

test('createInitialState: explicit all not guessed, empty initial respects initialType', ()=>{
  const s = createInitialState({ initial: null, initialType:'period', preselect:[] })
  assert.equal(s.type,'period')
  assert.equal(s.personId, null)
})

test('snapshotDraft / isDirty: detects change in separate date/time', ()=>{
  const base = { personId:1, type:'text', eventDate:'2026-10-12', eventTime:'10:00:00', title:'a', body:'', tags:'', location:'', hours:'', overnight:false, manualText:false, note:'', extraIds:[], picked:[], fileTasks:[], sensitivity:'normal' }
  const snap = snapshotDraft(base)
  assert.equal(isDirty(base, snap), false)
  assert.equal(isDirty({ ...base, eventTime:'11:00:00' }, snap), true)
  assert.equal(isDirty({ ...base, eventDate:'2026-10-13' }, snap), true)
  assert.equal(isDirty({ ...base, title:'b' }, snap), true)
})

test('isDirty: detects picked change and fileTasks change', ()=>{
  const base = { personId:1, type:'outfit', eventDate:'2026-10-12', eventTime:'', title:'', body:'', tags:'', location:'', hours:'', overnight:false, manualText:false, note:'', extraIds:[], picked:[{ item_id:1 }], fileTasks:[], sensitivity:'normal' }
  const snap = snapshotDraft(base)
  const withExtraPick = { ...base, picked:[{ item_id:1 },{ item_id:2 }] }
  assert.equal(isDirty(withExtraPick, snap), true)
  const withFile = { ...base, fileTasks:[{ name:'a.jpg', file:{ name:'a.jpg' } }] }
  assert.equal(isDirty(withFile, snap), true)
})

test('hasUnsavedContent: true when any field filled', ()=>{
  assert.equal(hasUnsavedContent({ title:'x', picked:[], fileTasks:[] }), true)
  assert.equal(hasUnsavedContent({ title:'', picked:[{ item_id:1 }], fileTasks:[] }), true)
  assert.equal(hasUnsavedContent({ title:'', picked:[], fileTasks:[{ name:'a.jpg' }] }), true)
  assert.equal(hasUnsavedContent({ title:'', picked:[], fileTasks:[], manualText:false }), false)
})

test('session draft in-memory: save/load/clear isolated and wired', ()=>{
  const key='test-key-1'
  const state={ personId:2, type:'text', eventDate:'2026-10-12', eventTime:'', title:'draft', body:'', tags:'', location:'', hours:'', overnight:false, manualText:false, note:'', extraIds:[], picked:[], fileTasks:[], sensitivity:'normal' }
  saveSessionDraft(key, state)
  const loaded=loadSessionDraft(key)
  assert.equal(loaded.title,'draft')
  loaded.title='mutated'
  const reloaded=loadSessionDraft(key)
  assert.equal(reloaded.title,'draft', 'clone isolation')
  clearSessionDraft(key)
  assert.equal(loadSessionDraft(key), null)
})

test('shouldWarnOnLeave true when dirty', ()=>{
  const state={ personId:1, type:'text', eventDate:'2026-10-10', eventTime:'', title:'a', body:'', tags:'', location:'', hours:'', overnight:false, manualText:false, note:'', extraIds:[], picked:[], fileTasks:[], sensitivity:'normal' }
  const snap = snapshotDraft({ ...state, title:'' })
  assert.equal(shouldWarnOnLeave(state, snap), true)
  assert.equal(shouldWarnOnLeave({ ...state, title:'' }, snapshotDraft({ ...state, title:'' })), false)
})

test('createInitialState includes fileTasks empty and supports preselect', ()=>{
  const s = createInitialState({ initial:{ person_id:1, type_key:'text' }, preselect:[99] })
  assert.ok(s.picked.some(p=>p.item_id===99))
  assert.deepEqual(s.fileTasks, [])
})
