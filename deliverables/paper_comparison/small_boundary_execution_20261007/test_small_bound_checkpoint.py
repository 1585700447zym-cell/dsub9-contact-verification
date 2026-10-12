"""Outer checkpoint protocol, no torch serialization or learner construction."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest
from small_bound_profile import outer_contract, profile_digest, canonical, sha
from small_bound_learning import (read_outer_checkpoint, package_outer_checkpoint,
    SmallBoundChain, read_small_bound_checkpoint)


def package(tmp_path):
    inner=tmp_path/'old_core';inner.mkdir()
    (inner/'state.pt').write_bytes(b'opaque protocol fixture; never deserialized')
    (inner/'manifest.json').write_text(canonical(dict(version='v4_checkpoint_manifest_v1',state_sha256=sha(inner/'state.pt'))),encoding='utf8')
    c=outer_contract();binding=dict(mode='F50',purpose='synthetic_qualification',
        qualification_sha256='a'*64,config_sha256=c['engine_config_sha256'])
    output=tmp_path/'outer'
    pin=package_outer_checkpoint(inner,output,contract=c,engine_binding=binding,archives={})
    return output,pin,c


def test_complete_envelope_validated_without_core_import(tmp_path):
    path,pin,c=package(tmp_path)
    result=read_outer_checkpoint(path,expected_digest=pin,expected_profile_digest=profile_digest(c))
    assert result['contract']==c and result['engine_binding']['mode']=='F50'
    assert 'tools.learning.v4_checkpoint' not in sys.modules


def test_naked_old_checkpoint_rejected_before_runtime_import(tmp_path):
    path,pin,c=package(tmp_path)
    with pytest.raises(ValueError):
        read_outer_checkpoint(path/'engine',expected_digest=sha(path/'engine/manifest.json'),expected_profile_digest=profile_digest(c))


@pytest.mark.parametrize('mutation',['profile','scale','missing','payload','witness_path'])
def test_wrong_profile_scale_or_payload_rejected(tmp_path,mutation):
    path,pin,c=package(tmp_path);manifest=path/'manifest.json';m=json.loads(manifest.read_text(encoding='utf8'))
    if mutation=='profile':m['profile_sha256']='0'*64
    elif mutation=='scale':m['contract']['physical_scale_SI'][3]=.0005
    elif mutation=='missing':del m['contract']
    elif mutation=='payload':(path/'engine/state.pt').write_bytes(b'wrong')
    else:m['files']['../escaped.json.gz']={'sha256':'0'*64,'bytes':0}
    manifest.write_text(canonical(m),encoding='utf8')
    with pytest.raises(ValueError):
        read_outer_checkpoint(path,expected_digest=sha(manifest),expected_profile_digest=profile_digest(c))


class Denied:
    def verify(self,*args):raise PermissionError('No new numerical/physical authorization')


def test_construction_and_load_reject_absent_admission_before_import(tmp_path):
    path,pin,c=package(tmp_path)
    with pytest.raises(PermissionError):SmallBoundChain(c,output=tmp_path/'chain',admission=Denied())
    with pytest.raises(PermissionError):
        read_small_bound_checkpoint(path,expected_profile_digest=profile_digest(c),expected_digest=pin,admission=Denied())
    assert 'tools.learning.v4_checkpoint' not in sys.modules
    assert 'tools.learning.v4_pilot_chain' not in sys.modules


def test_profile_change_or_guard_blocks_update_before_core_call():
    chain=object.__new__(SmallBoundChain);chain.contract=outer_contract();chain.pin=profile_digest(chain.contract)
    chain.admission=Denied();chain.binding={};chain.inner=type('Core',(),{'stop_reason':'CONTACT_GUARD'})()
    with pytest.raises(RuntimeError):chain.update(500)
    chain.inner.stop_reason=None;chain.contract['physical_scale_SI'][0]=.00005
    with pytest.raises(ValueError):chain.begin('warmup',0)


def test_evaluation_rejected_before_inner_publication():
    chain=object.__new__(SmallBoundChain);chain.contract=outer_contract();chain.pin=profile_digest(chain.contract)
    chain.admission=Denied();chain.binding={}
    with pytest.raises(ValueError):chain.publish({'stage':'final','scope':'frozen_development_evaluation'})


def test_update_callback_matches_existing_core_signature_without_numeric_work():
    chain=object.__new__(SmallBoundChain);calls=[];chain.verify=lambda operation:calls.append(operation)
    class Core:
        stop_reason=None
        def update(self,n,*,before_update,after_update):
            before_update(self)
            if after_update:after_update(self,{'fixture':True})
            return 'protocol fixture only'
    chain.inner=Core()
    before=[];after=[]
    result=chain.update(1,before_update=lambda c:before.append(c),after_update=lambda c,s:after.append((c,s)))
    assert result=='protocol fixture only' and before==[chain] and after==[(chain,{'fixture':True})]
    assert calls==['update','update']


@pytest.mark.parametrize('operation',['read','load'])
def test_inner_witness_mismatch_rejected_before_any_core_restore(tmp_path,monkeypatch,operation):
    import types
    import small_bound_learning as module
    from tools.learning.v4_pilot_contract import learning_config
    path,pin,c=package(tmp_path);m=json.loads((path/'manifest.json').read_text(encoding='utf8'))
    payload=dict(version='v4_pilot_checkpoint_v1',config=learning_config('F50'),
        binding=m['engine_binding'],archives={'injected_F50_physical_archive':b'unregistered'})
    monkeypatch.setattr(module,'_read_inner_payload',lambda *args:payload,raising=False)
    reached=[]
    def core(**kwargs):reached.append(True);raise ValueError('fixture must never reach core')
    fake=types.ModuleType('tools.learning.v4_checkpoint')
    fake.read_checkpoint=lambda *args,**kwargs:core(**kwargs)
    fake.load_checkpoint=lambda *args,**kwargs:core(**kwargs)
    monkeypatch.setitem(sys.modules,'tools.learning.v4_checkpoint',fake)
    admitted=types.SimpleNamespace(verify=lambda *args:m['engine_binding'])
    kwargs=dict(expected_profile_digest=profile_digest(c),expected_digest=pin,admission=admitted)
    if operation=='load':kwargs['output']=tmp_path/'restored'
    function=module.read_small_bound_checkpoint if operation=='read' else module.load_small_bound_checkpoint
    with pytest.raises(ValueError):function(path,**kwargs)
    assert reached==[] and not (tmp_path/'restored').exists()
