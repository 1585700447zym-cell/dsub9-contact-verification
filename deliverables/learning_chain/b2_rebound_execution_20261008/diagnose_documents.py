"""Dry-run diagnostic: block all writes and expose the failing document/header."""
import importlib.util
import json
from pathlib import Path
import re

OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('doc_updater',OUT/'update_documents.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original_subn=re.subn
def trace(pattern,replacement,text,*args,**kwargs):
    result=original_subn(pattern,replacement,text,*args,**kwargs)
    if pattern.startswith(('统计截至','<!-- b2-scope-current')):
        print(json.dumps(dict(pattern=pattern,matches=result[1],title=text.splitlines()[0],
                              before_length=len(text),after_length=len(result[0]),
                              before_header='统计截至' in text,after_header='统计截至' in result[0],
                              header=[line for line in text.splitlines() if '统计截至' in line]),ensure_ascii=False))
    return result
re.subn=trace
original_open=Path.open
def readonly_open(self,mode='r',*args,**kwargs):
    if any(c in mode for c in 'wxa+'):raise RuntimeError('Dry-run blocks writes: '+str(self))
    return original_open(self,mode,*args,**kwargs)
Path.open=readonly_open
try:module.main()
except BaseException as exc:print(type(exc).__name__+': '+str(exc))
